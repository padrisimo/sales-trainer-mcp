# Project decisions

## 2026-11-03 — Phase 0: starting the web server (skeleton)

- **Decision:** the web server (FastAPI + uvicorn) starts in a daemon thread inside the MCP process (`mcp` SDK, `MCPServer` class, stdio transport).
- **Discarded alternative:** child process of the MCP server.
- **Reason:** less management complexity in Phase 0; the project memory already states "starts in a thread or child process".
- **Consequences:** the daemon thread builds the FastAPI app from `src/sales_trainer/web/app.py` and runs uvicorn on it; bind `127.0.0.1`, default port `8765` configurable with `SALES_TRAINER_PORT`.
- **Deviation from the plan:** `uv_build` derives the module name from the project name (`sales_trainer_mcp`); `[tool.uv.build-backend] module-name = "sales_trainer"` is pinned in `pyproject.toml` to keep the `src/sales_trainer/` layout from the memory file.
- **Known limit:** `sales_trainer_start` does not validate `Origin` yet because there is no WebSocket; that arrives with the audio phase.

## 2026-11-03 — Phase 1: procedural avatar and vendored Three.js

- **Decision:** the Phase 1 avatar is built in code (Three.js primitives) with 15 viseme morph targets; no GLB/VRM models are used.
- **Discarded alternative:** shipping a CC0 model with Oculus morph targets or VRM expressions.
- **Reason:** zero licensing risk, zero runtime downloads, and the morph target names are ours, which is the contract Phase 2 needs.
- **Three.js:** `0.187.0` versioned in `src/sales_trainer/web/static/js/vendor/` (`three.module.js` + `three.core.js`, the first imports the second). Served with `StaticFiles`; `node_modules/` is gitignored.
- **Spherical mouth:** the mouth mesh recomputes its `z` from the skull surface at the already-deformed position. Without that, open visemes sank into the head and only the mouth corners showed.
- **Known limit:** the avatar is a stylized low-poly head with no teeth or tongue; `FF` and `TH` differ by aperture, not by labiodental or dental contact. To be revisited if the Phase 2 visual criterion demands it.
- **Known limit:** the Playwright e2e does get WebGL working headless with `--use-angle=swiftshader`; it checks DOM, state and absence of console errors, not aesthetics.
- **Environment:** the workflow subagents were denied in the session, so spec, plan and implementation were executed inline instead of one implementer per task.

## 2026-11-03 — Phase 2: Azure as the TTS provider

- **Decision:** Phase 2 uses Azure Speech as the real TTS provider (native `viseme_received` events with audio offsets in ticks) plus an explicit mock provider for tests.
- **Discarded alternative:** local Piper/Kokoro in this phase, which would need forced alignment with torch to obtain real phoneme timings.
- **Reason:** Azure is the only source of true per-viseme offsets anchored to the audio it just produced, which is exactly what the 40 ms criterion needs; the offline provider gets its own phase.
- **Consequences:** `SALES_TRAINER_TTS=azure|mock` selects the provider; the mock is never a silent fallback. Ticks are converted with `ticks / 10_000`. Audio travels inline as base64, capped at 400 characters per request.
- **Known limit:** Azure viseme IDs 0-21 do not cover every Spanish phoneme; `h`, `l` and `r` land on the closest shape and the mapping is explicit in `voice/visemes.py`.
- **Verified (2026-11-09, real Azure key):** real synthesis with `es-ES-ElviraNeural` returned a 24 kHz 16-bit mono WAV, 4.68 s of audio for a Spanish sentence, 35 viseme events on a monotonic timeline whose last event falls inside the audio duration. A headless Chromium run of `/debug/tts` against the real provider produced 32 visemes over 11 distinct shapes in an order consistent with the sentence, playback ended on its own, and there were no console errors.
- **Known limit:** the ear-and-eye judgement of mouth coherence is still a manual check, and the automated suite itself keeps running on the mock provider (no key, no network).

## 2026-11-09 — Phase 3: Silero VAD on ONNX, faster-whisper as the default STT

- **Decision:** Phase 3 captures with `getUserMedia` + an `AudioWorklet` that emits 512-sample PCM16 chunks at 16 kHz (32 ms) over `/ws/stt`; the server segments turns with Silero VAD v5 (vendored ONNX, `onnxruntime`) and a pure `TurnDetector` (2 chunks to start, 700 ms of silence to close, 250 ms minimum of speech, 30 s maximum); only finished turns are transcribed, by faster-whisper `small` int8 by default, with Azure Speech as the alternative and a mock for the suite.
- **Discarded alternative:** the `silero-vad` PyPI package, which hard-requires `torch>=1.12` (≈2.5 GB) for a 2.2 MB model.
- **Discarded alternative:** amplitude- or energy-based VAD; the probabilities come from a real model.
- **Reason:** the ONNX session costs 0.09 ms per 32 ms chunk on this machine, the model is MIT and 2.2 MB, and `onnxruntime` already ships with `faster-whisper`.
- **Deviations from the design:** Azure receives raw PCM16 through `PushAudioInputStream` with an explicit `AudioStreamFormat(16000, 16, 1)` instead of a WAV, because that stream pushes sample frames and a RIFF header would be transcribed as a click. The 250 ms minimum counts **speech**, not turn duration: a turn cannot close before 700 ms of silence, so a duration minimum would never reject anything. faster-whisper receives the turn as a float32 array from `decode_pcm16`, so no file or temporary WAV is written and PyAV/ffmpeg is never used.
- **Consequences:** `SALES_TRAINER_STT=faster-whisper|azure|mock`, `SALES_TRAINER_WHISPER_MODEL` (default `small`), `SALES_TRAINER_SILENCE_MS` (default 700). `/ws/stt` validates `Origin` against `http://127.0.0.1:PORT` and `http://localhost:PORT` and the session token against `web/sessions.py`, which closes the Phase 0 known limit. Turns live in memory per session and are readable at `GET /api/turns?session=`.
- **Verified (2026-11-09):** the vendored model (SHA-256 `2623a295…`) scores digital silence below 0.001 and real Spanish speech above 0.99, and the 67-test suite plus the 4 e2e tests pass on the mock provider with no key and no network. The e2e run feeds `tests/fixtures/hola-marta-16k.wav` to the fake microphone and gets one transcript out of the real worklet, socket, VAD and turn detector.
- **Verified (2026-11-09, real faster-whisper):** `small` int8 transcribed the committed fixture as "Hola, soy Marta. ¿En qué puedo ayudarte?" with 7 words and word timings in 1.45 s for 3.91 s of audio on this machine.
- **Verified (2026-11-09, real Azure STT):** `AzureSTTProvider` over `PushAudioInputStream` returned "¿Hola, soy Marta, en qué puedo ayudarte?" with 7 words and word timings that start at the 500 ms silence prefix, in 3.45 s for 3.91 s of audio.
- **Configuration:** `.env` at the repository root is loaded once when `sales_trainer` is imported (`override=False`, so a real environment variable always wins). Without that, `os.environ` never saw `AZURE_SPEECH_KEY` and both Azure providers looked unconfigured.
- **Known limit:** the first faster-whisper run downloads the model (250-480 MB) and fails offline with `STTUnavailable`, which the socket forwards as `{"type":"error","code":"stt"}`; the automated suite never touches whisper.
- **Known limit:** the fixture was synthesized with the macOS `say` voice Mónica and converted to 16 kHz mono by `afconvert` instead of Azure TTS, because no Azure key was configured in this session; it is still real Spanish speech, and no key or network is needed to run the suite.
- **Known limit:** the fake microphone e2e runs only the mock transcriber; both real engines were checked on the committed fixture, but real room noise and microphone levels are still a manual check.
- **Known limit:** no audio touches the disk and `SAVE_AUDIO` stays unimplemented until the configuration phase; the only committed audio is `tests/fixtures/hola-marta-16k.wav`.
