# Design — Phase 3: microphone, VAD and STT

- **Date:** 2026-11-09
- **Topic:** fase3-microfono-vad-stt
- **Status:** Approved by the user (design)

## Context

Phase 2 left a working TTS path: `POST /api/tts` returns base64 audio plus a viseme timeline, `/debug/tts` plays it and drives the Phase 1 mouth from `AudioContext.currentTime`. The suite is at 30 green tests, `ruff` is clean, and there is no audio input anywhere in the project: no microphone, no WebSocket, no speech recognition.

`MEMORY.md` fixes the Phase 3 criterion — a correct Spanish transcription with well-segmented turns — and the rules this phase must respect:

- Audio capture with `getUserMedia` and an AudioWorklet that converts to PCM16 mono at 16 kHz and sends frames of 20-30 ms over a WebSocket.
- Server-side VAD segments turns; the turn ends after roughly 700 ms of silence.
- Word timestamps and per-word probabilities are stored per turn.
- Raw audio is not stored unless `SAVE_AUDIO=true`.
- Everything runs locally by default; the cloud is used only when the user configures keys.
- The server binds `127.0.0.1` only, with a session token and `Origin` validation. Phase 0 recorded the missing `Origin` validation as a known limit because there was no WebSocket; this phase creates one, so it closes the limit.

The user chose faster-whisper `small` in `int8` as the default engine and asked for Azure Speech as a second real provider, so the voice stack has a local default and a cloud option behind the same interface, exactly like TTS.

## Goal

Let the user speak into the microphone in `/debug/stt`; the server detects each turn with a real VAD, transcribes it with word-level timings and probabilities, and shows the result, so a Spanish utterance produces a correct transcript cut into turns without storing the audio.

## Acceptance Criteria

1. `/debug/stt` opens the microphone with `echoCancellation` and `noiseSuppression` and streams PCM16 mono 16 kHz frames of about 32 ms over `/ws/stt`.
2. The WebSocket rejects connections whose `Origin` header is not the local page and whose `session` token is not registered by `sales_trainer_start` or by loading a page with that token.
3. Speech followed by 700 ms of silence closes one turn and produces exactly one transcript message for that turn.
4. A transcript message carries `text`, `language` and `words`, each word with `word`, `start_ms`, `end_ms` and `probability` between 0 and 1.
5. Word timings are non-decreasing and stay inside the turn duration.
6. `GET /api/turns?session=<token>` returns the turns of that session in order.
7. The suite passes with no keys, no network and no whisper model download, using `SALES_TRAINER_STT=mock`.
8. `uv run ruff check .` is clean and the existing 30 tests stay green.

## Non-Goals

- Partial or streaming transcripts. Only the finished turn is transcribed.
- Barge-in, echo cancellation at the protocol level, push-to-talk and turn segmentation by the client.
- LLM, characters, evaluation, the temperature gauge, reports and history (Phases 4-8).
- Storing audio. `SAVE_AUDIO` stays unimplemented until the configuration phase.
- Speaker diarization, language auto-detection beyond pinning `es`.
- Streaming synthesis or the latency target of 2.5 s end to end; this phase measures transcription time and records it, nothing more.

## Proposed Architecture

**Capture.** `src/sales_trainer/web/static/js/pcm-worklet.js` is an `AudioWorkletProcessor` that keeps a 512-sample buffer at 16 kHz and posts an `Int16Array` every 32 ms. `src/sales_trainer/web/static/js/mic.js` opens `getUserMedia` with `echoCancellation`, `noiseSuppression` and `autoGainControl`, creates an `AudioContext`, loads the worklet, averages down to 16 kHz when the context rate is higher, and forwards the frames over the socket as binary. Reason: 512 samples is exactly the window Silero expects and 32 ms sits inside the 20-30 ms rule with headroom.

**VAD.** The `silero-vad` PyPI package hard-requires `torch>=1.12`, which would add roughly 2.5 GB for a detector whose model is 2.2 MB. Instead `src/sales_trainer/voice/models/silero_vad.onnx` is vendored (MIT, version 5) and run through `onnxruntime`, which `faster-whisper` already installs. Verified against the real file: inputs `input[1,512] float32`, `state[2,1,128] float32`, `sr` int64; outputs `output[1,1]` and `stateN`; 0.09 ms per 32 ms chunk on this machine. `src/sales_trainer/voice/vad.py` wraps that session in a small `SileroVAD` class that keeps the state tensor between calls and returns one probability per chunk.

**Turn detection.** `src/sales_trainer/voice/turns.py` holds `TurnDetector`, a pure state machine fed with `(chunk, probability)`: it starts a turn after two consecutive chunks above 0.5, accumulates the chunks, closes the turn after 700 ms below the threshold, discards turns shorter than 250 ms as noise, and force-closes at 30 s. Reason: a deterministic state machine is testable without audio, and the probabilities come from a real model rather than an energy heuristic.

**STT providers.** `src/sales_trainer/voice/stt/base.py` defines `Word {word, start_ms, end_ms, probability}`, `STTResult {text, language, words}`, `STTUnavailable` and the `STTProvider` protocol.

- `whisper.py`: `WhisperModel(model, device="cpu", compute_type="int8")` built once, `transcribe(audio, language="es", word_timestamps=True, vad_filter=False)`; the provider joins the segments and converts seconds to milliseconds. `vad_filter=False` because our VAD already cut the turn.
- `azure.py`: single-shot recognition over `PushAudioInputStream` with the turn encoded as a 16 kHz mono WAV; `speech_recognition_language = "es-ES"`, `request_word_level_timestamps()`; words are read from `SpeechServiceResponse_JsonResult` (offsets in ticks, divided by 10 000); `NoMatch` and cancellation raise `STTUnavailable`.
- `mock.py`: fixed text and words, no audio processing, selected only by `SALES_TRAINER_STT=mock`.
- `__init__.py`: `get_stt_provider()` reads `SALES_TRAINER_STT` (`faster-whisper` by default, `azure`, `mock`) and imports lazily so the mock path never pulls whisper or Azure.

**WebSocket.** `src/sales_trainer/web/routes/stt_ws.py` exposes `/ws/stt`. On connect it validates `Origin` against the local page and checks `session` against the session registry, then sends `{"type":"ready"}`. It then consumes binary frames, feeds the VAD and the detector, and emits `{"type":"turn_start","t_ms"}`, `{"type":"turn_end","t_ms","audio_ms"}` and `{"type":"transcript","text","language","words":[...]}`. Failures become `{"type":"error","code","message"}` instead of closing silently, because a closed socket with no reason is the worst possible debugging experience.

**Session registry.** Today the token is a UUID returned by `sales_trainer_start` and stored nowhere, so nothing can validate it. `src/sales_trainer/web/sessions.py` adds a process-wide set with `register(token)` and `is_known(token)`: `sales_trainer_start` registers the token it issues, and any page request carrying a non-empty `session` registers it too, which keeps the e2e and manual runs working when uvicorn is started without the MCP tool. The token stays a UUID delivered in the URL, so guessing it is not a realistic path; the registry only makes the socket refuse tokens nobody was given.

**Turn store.** `src/sales_trainer/voice/turns.py` also holds `TurnStore`, a per-session in-memory list with `add` and `list`. `GET /api/turns?session=` returns it. Reason: Phase 4 needs the conversation transcript and Phase 3 has no database yet; a dict keeps it honest and disposable.

**Debug page.** `/debug/stt` serves `static/debug/stt.html` and `static/js/stt-debug.js`: start and stop buttons, a level meter from the VAD probability, the connection state and the list of turns with their words, timings and probabilities. `window.sttDebug` exposes `{ready, listening, turns, lastError}` for the e2e.

**Configuration.** `SALES_TRAINER_STT` (`faster-whisper|azure|mock`), `SALES_TRAINER_WHISPER_MODEL` (default `small`), `SALES_TRAINER_SILENCE_MS` (default 700). Azure reuses `AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION` from Phase 2.

## Files To Change

**New:**
- `src/sales_trainer/voice/models/silero_vad.onnx` — vendored Silero VAD v5 model (MIT).
- `src/sales_trainer/voice/vad.py` — `SileroVAD` over `onnxruntime`, plus `decode_pcm16` to float32.
- `src/sales_trainer/voice/turns.py` — `TurnDetector`, `Turn`, `TurnStore`.
- `src/sales_trainer/voice/stt/__init__.py` — provider factory.
- `src/sales_trainer/voice/stt/base.py` — models and protocol.
- `src/sales_trainer/voice/stt/whisper.py` — faster-whisper provider.
- `src/sales_trainer/voice/stt/azure.py` — Azure provider.
- `src/sales_trainer/voice/stt/mock.py` — deterministic provider.
- `src/sales_trainer/web/sessions.py` — process-wide token registry (`register`, `is_known`).
- `src/sales_trainer/web/routes/stt.py` — `GET /api/turns`.
- `src/sales_trainer/web/routes/stt_ws.py` — `/ws/stt` with `Origin` and token validation.
- `src/sales_trainer/web/static/js/pcm-worklet.js` — capture worklet.
- `src/sales_trainer/web/static/js/mic.js` — microphone, resampling and socket.
- `src/sales_trainer/web/static/js/stt-debug.js` — page wiring and `window.sttDebug`.
- `src/sales_trainer/web/static/debug/stt.html` — the page.
- `tests/fixtures/hola-marta-16k.wav` — 16 kHz mono 16-bit Spanish speech, generated once with Azure TTS and committed, used by the VAD unit test and the fake microphone.
- `tests/unit/test_vad.py` — real ONNX on the fixture: speech detected inside, silence at the edges.
- `tests/unit/test_turns.py` — detector state machine against scripted probabilities.
- `tests/unit/test_stt_mock.py` — schema, ordering and bounds of the mock result.
- `tests/unit/test_stt_providers.py` — factory selection and Azure word parsing from a JSON double.
- `tests/unit/test_stt_ws.py` — `TestClient` websocket: bad origin rejected, bad token rejected, mock provider produces one turn and one transcript.
- `tests/unit/test_turns_route.py` — `GET /api/turns` shape and ordering.
- `tests/unit/test_sessions.py` — registry: unknown token rejected, registered token accepted, page load registers.
- `tests/js/pcm_downsample.mjs` + `tests/unit/test_pcm_downsample_js.py` — the resampling helper checked in node.

**Modified:**
- `src/sales_trainer/web/app.py` — mount the STT router and the websocket route, serve `/debug/stt`.
- `src/sales_trainer/mcp_server.py` — keep the issued session token available to the web app so the socket can validate it.
- `pyproject.toml` — `faster-whisper`, `onnxruntime`, `numpy`.
- `src/sales_trainer/web/static/LICENSES.md` — Silero VAD license and origin.
- `docs/decisions.md`, `AGENTS.md` — close-out.

## Testing Strategy

- **Unit (Python, no network, no model):** the detector against scripted probabilities (short blips discarded, 700 ms of silence closes, 30 s forced close); the mock provider's schema; the factory's selection and its error for an unknown value; Azure word parsing with a JSON double; the `TurnStore` ordering.
- **Unit (real ONNX, no network):** `SileroVAD` on the committed WAV fixture plus digital silence, asserting the speech region scores above 0.5 and the padded silence below it. This is the only test that exercises the real detector.
- **WebSocket (in-process):** `TestClient.websocket_connect` with an injected fake VAD probability stream and the mock provider, asserting `ready`, `turn_start`, `turn_end` and one `transcript`, plus 403-equivalent rejection for a foreign `Origin` and a wrong token.
- **Node, via pytest:** the Float32 to PCM16 and downsampling helper on known inputs.
- **e2e (Playwright):** Chromium with `--use-fake-device-for-media-stream`, `--use-fake-ui-for-media-stream` and `--use-file-for-fake-audio-capture=tests/fixtures/hola-marta-16k.wav`, `SALES_TRAINER_STT=mock`; opens `/debug/stt`, starts listening, waits for a turn and asserts the transcript appears and no console error is logged. This exercises the real worklet, the real socket, the real VAD and the real turn logic; only the transcription is a double.
- **Manual:** speak real Spanish into `/debug/stt` with `SALES_TRAINER_STT=faster-whisper` and again with `azure`, and compare accuracy and latency. This is the only step that validates the engines.
- **Commands:** `uv run pytest`, `uv run pytest -m e2e`, `uv run ruff check .`.

## Risks And Mitigations

1. **First run downloads the whisper model (~250-480 MB for `small` int8) and fails offline.** Mitigation: the automated suite never touches whisper; the provider raises `STTUnavailable` with the model name and the download failure, which the socket forwards as `{"type":"error"}`.
2. **CPU latency on a 3 s turn exceeds the 2.5 s target.** Mitigation: measure it in the manual step and record the number in `docs/decisions.md`; `SALES_TRAINER_WHISPER_MODEL` allows `base` if it is too slow, and Azure exists for the same reason.
3. **VAD threshold wrong for real microphones (fan noise, room echo).** Mitigation: threshold and silence duration are constants in one place with one test over the fixture; the debug page shows the live probability so it can be tuned by eye, not guessed.
4. **A vendored 2.2 MB binary model in git.** Mitigation: single file, MIT, documented in `LICENSES.md`; the alternative (the PyPI package) costs 2.5 GB of torch.
5. **The fake microphone needs a valid WAV or Chromium feeds silence, making the e2e pass vacuously.** Mitigation: the same fixture is asserted to contain speech by the VAD unit test, and the e2e fails if no `turn_end` arrives within the timeout.
6. **`Origin` validation breaking the real page.** Mitigation: the check accepts exactly the local origins the server serves (`http://127.0.0.1:PORT` and `http://localhost:PORT`), and the e2e plus the manual run cover both.

## Decision Summary

- Capture in an AudioWorklet at 512 samples / 32 ms, PCM16 mono 16 kHz, over `/ws/stt`.
- Silero VAD v5 vendored as ONNX and run with `onnxruntime`; the PyPI `silero-vad` package (torch) is discarded.
- Turn detection is a pure state machine: 700 ms of silence closes, 250 ms minimum, 30 s maximum.
- faster-whisper `small` int8 is the default provider; Azure Speech is a real alternative behind the same interface; `mock` exists only for tests.
- Only finished turns are transcribed; no partials in this phase.
- Turns live in memory per session and are exposed over `GET /api/turns`.
- No audio touches the disk.
- The e2e runs on the fake microphone with a committed Spanish WAV and a mock transcriber, so the suite needs no keys, no network and no model.

## Open Questions

None blocking. Deferred: whether Phase 4 needs partial transcripts for perceived latency, and whether `SAVE_AUDIO` belongs to the configuration phase or to the report phase.
