# Design — Phase 2: TTS with a synchronized viseme timeline

- **Date:** 2026-11-03
- **Topic:** fase2-tts-visemes
- **Status:** Approved by the user (design)

## Context

Phase 1 shipped a procedural head with 15 Oculus viseme morph targets (`sil, PP, FF, TH, DD, kk, CH, SS, nn, RR, aa, E, I, O, U`), an idle loop in `src/sales_trainer/web/static/js/scene.js` and a `/debug/visemes` panel that applies one viseme at a time by setting `avatar.group.userData.targetViseme`. The suite is at 11 green tests, `ruff` is clean, and the frontend has no audio code at all.

`MEMORY.md` fixes the Phase 2 criterion: a Spanish sentence must be spoken with coherent lips and an offset of at most 40 ms. It also states two hard rules this phase cannot bend:

- Visemes are derived from the **real phonemes with their real timings**; animating from audio amplitude or randomly is forbidden.
- The browser uses **`AudioContext.currentTime` as the master clock** for lip sync.

The project memory allows two TTS providers. The user chose Azure for this phase (exact viseme events with native audio offsets) plus a mock provider, because the suite must pass with no keys and no network.

Verified before writing this spec (`azure-cognitiveservices-speech` 1.53.0 installed and introspected):

- `SpeechSynthesizer.viseme_received` exists (added in SDK 1.16.0) and delivers `SpeechSynthesisVisemeEventArgs` with `viseme_id`, `audio_offset` and `animation`.
- `audio_offset` is documented as "Audio offset in ticks. A single tick represents one hundred nanoseconds".
- `SpeechSynthesisResult.audio_data` returns the synthesized audio, and `SpeechConfig.set_speech_synthesis_output_format(SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm)` selects a WAV container, which the browser can decode.

## Goal

Turn text into audio plus a viseme timeline whose timings come from the TTS engine, serve it to the browser over HTTP, and play it there driving the Phase 1 mouth morph targets from `AudioContext.currentTime` against that timeline, so a Spanish sentence is spoken with lips that follow the real phoneme timings.

## Acceptance Criteria

1. `POST /api/tts` with `{"text": "..."}` returns `{"audio_base64", "mime", "visemes"}`, where every viseme entry is `{"t_ms", "viseme", "weight"}`.
2. The viseme names returned are always members of the 15-name set; unmapped engine IDs degrade to `sil`.
3. The timeline is non-decreasing in `t_ms`, starts at or after 0 and never exceeds the audio duration.
4. `/debug/tts` takes a sentence, requests the audio, plays it and animates the mouth; `window.ttsDebug` exposes `{ ready, speaking, activeViseme, timelineLength }`.
5. Lip sync uses `AudioContext.currentTime` as the master clock, not `setTimeout` accumulation.
6. The suite passes with no Azure key and no network, using the mock provider.
7. `uv run ruff check .` stays clean and the existing 11 tests stay green.

## Non-Goals

- Speech recognition, microphone capture, VAD and turn segmentation (Phase 3).
- Characters, LLM, evaluation and the gauge (Phases 4-5).
- The offline local provider (Piper/Kokoro plus forced alignment). It is out of scope for this phase and recorded as a pending decision.
- Coarticulation beyond the smoothing described below; no phoneme-level blending of two simultaneous visemes.
- Persisting audio. Nothing is written to disk.
- Streaming synthesis: the whole sentence is synthesized before playback.

## Proposed Architecture

**Provider interface.** `src/sales_trainer/voice/tts/base.py` defines a `TTSProvider` protocol with `synthesize(text: str, voice: str | None = None) -> TTSResult` and the pydantic models `VisemeEvent {t_ms: int, viseme: str, weight: float}` and `TTSResult {audio: bytes, mime: str, visemes: list[VisemeEvent]}`. Reason: Phase 4 needs a second provider (a character speaking short lines) and the tests need a substitute without Azure.

**Viseme mapping.** `src/sales_trainer/voice/visemes.py` holds `VISEMES` (the same 15 names as `visemes.js`), `AZURE_VISEME_TO_VISEME` (Azure IDs 0-21 to our names, with any unmapped ID falling back to `sil`) and `smooth(events)` which applies the coarticulation pass: it keeps the timeline monotonic, merges consecutive identical visemes inside 60 ms and clamps weights into `[0, 1]`. Reason: the Azure ID set does not map one-to-one onto the Oculus set for Spanish, so the mapping must be explicit and testable instead of a lookup buried in the provider.

**Azure provider.** `src/sales_trainer/voice/tts/azure.py` builds `SpeechConfig` from `AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION`, sets `es-ES-ElviraNeural` as the default voice, requests `Riff24Khz16BitMonoPcm`, subscribes `viseme_received` (converting ticks to milliseconds with `ticks / 10_000`), synthesizes with `speak_text_async`, and raises a `TTSUnavailable` error with the cancellation reason when synthesis fails. Reason: it is the only provider that yields true per-viseme offsets anchored to the audio it just produced.

**Mock provider.** `src/sales_trainer/voice/tts/mock.py` returns a real silent WAV (built with the `wave` standard module) plus a fixed, deterministic viseme timeline. It never derives visemes from the audio and it is only reachable by explicit configuration (`SALES_TRAINER_TTS=mock`), never as a silent fallback. Reason: the suite must exercise the full HTTP and playback path without keys, and a fake WAV keeps `decodeAudioData` honest.

**HTTP surface.** `src/sales_trainer/web/routes/tts.py` exposes `POST /api/tts` with a pydantic body `{text: str}` limited to 400 characters, returning the base64 audio inline. Reason: no file storage, no orphan files, one round trip, and Phase 2 has no session store yet.

**Playback and lip sync.** `src/sales_trainer/web/static/js/speak.js` exports `speak(text)` and `visemeAt(timeline, tMs)`. `speak` fetches the endpoint, decodes with `AudioContext.decodeAudioData`, schedules an `AudioBufferSourceNode`, and on each animation frame computes `t = (audioContext.currentTime - startedAt) * 1000` and applies the weights of `visemeAt`. `visemeAt` is a pure function: the last event with `t_ms <= t`, `sil` before the first event and when the timeline is empty. Shape transitions are smoothed by the existing morph-target lerp in `scene.js`, so the player never blends weights itself. Reason: a pure function is testable in node without a browser, and using `AudioContext.currentTime` is the memory's requirement.

**Debug page.** `/debug/tts` serves `static/debug/tts.html` plus `static/js/tts-debug.js`, which mounts the Phase 1 scene, adds a text input and a speak button, and exposes `window.ttsDebug`.

**Configuration.** `SALES_TRAINER_TTS` selects `azure` (default) or `mock`; `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` and `AZURE_SPEECH_VOICE` configure the Azure provider. Documented in the phase report and later in `.env.example`.

## Files To Change

**New:**
- `src/sales_trainer/voice/__init__.py`
- `src/sales_trainer/voice/visemes.py` — the 15 names, the Azure ID map and `smooth`.
- `src/sales_trainer/voice/tts/__init__.py` — provider factory honouring `SALES_TRAINER_TTS`.
- `src/sales_trainer/voice/tts/base.py` — protocol and pydantic models.
- `src/sales_trainer/voice/tts/azure.py` — Azure implementation.
- `src/sales_trainer/voice/tts/mock.py` — deterministic provider with a real silent WAV.
- `src/sales_trainer/web/routes/__init__.py`
- `src/sales_trainer/web/routes/tts.py` — `POST /api/tts`.
- `src/sales_trainer/web/static/js/speak.js` — `speak` and `visemeAt`.
- `src/sales_trainer/web/static/js/tts-debug.js` — page wiring and `window.ttsDebug`.
- `src/sales_trainer/web/static/debug/tts.html`
- `tests/unit/test_visemes.py` — mapping coverage, `smooth` invariants, and the Python/JS name-list cross-check.
- `tests/unit/test_tts_mock.py` — structure, monotonic timeline and duration bound.
- `tests/unit/test_tts_route.py` — endpoint contract with the mock provider injected.
- `tests/js/viseme_timeline.mjs` — node test of `visemeAt` boundaries and hold-until-end.
- `tests/unit/test_viseme_timeline_js.py` — runs the node test inside pytest.
- `tests/e2e/test_tts_page.py` — Playwright: mock provider, speak, assert audio plays and the active viseme advances.

**Modified:**
- `src/sales_trainer/web/app.py` — include the TTS router and serve `/debug/tts`.
- `pyproject.toml` — `azure-cognitiveservices-speech>=1.53.0` (already added during verification), marker unchanged.
- `tests/unit/test_debug_visemes_route.py` — unchanged; it asserts `/static/js/debug.js` on the visemes page, which stays.
- `docs/decisions.md` — Azure-as-Phase-2-provider decision, the local-provider deferral and the tick conversion.
- `AGENTS.md` — status when closing the phase.

## Testing Strategy

- **Unit (Python):** every Azure ID in 0-21 maps to one of the 15 names; `smooth` keeps the timeline monotonic, clamps weights and does not invent events; the mock result decodes as a valid WAV whose duration bounds the timeline; the endpoint returns the documented schema for the mock provider and a 4xx for empty or oversized text.
- **Unit (node, via pytest):** `visemeAt` returns `sil` before the first event, the exact event from its timestamp on, and holds the last event until the end.
- **Cross-language contract:** a Python test parses `VISEMES` out of `static/js/visemes.js` and asserts it equals the Python list, so the two can never drift.
- **e2e (Playwright, mock provider):** open `/debug/tts`, type a sentence, click speak, wait for `window.ttsDebug.speaking`, sample `window.ttsDebug.activeViseme` over time and assert it changes and that playback ends. Runs with `SALES_TRAINER_TTS=mock`, so no key and no network.
- **Manual, with an Azure key:** speak a Spanish sentence in `/debug/tts` and confirm lips match the audio by ear and eye; this is the only step that validates the real engine.
- **Commands:** `uv run pytest`, `uv run pytest -m e2e`, `uv run ruff check .`, `node tests/js/viseme_timeline.mjs`.

## Risks And Mitigations

1. **No Azure key in the development environment.** Mitigation: all automated checks run against the mock provider; the real provider is covered by unit tests that inject a fake `SpeechSynthesizer`-like double, and the ear-and-eye check is documented as a manual step in the phase report.
2. **Azure viseme IDs do not cover every Spanish phoneme.** Mitigation: the mapping table is explicit and total over 0-21, unmapped IDs fall back to `sil`, and the limitation is recorded in `docs/decisions.md` so Phase 5's delivery scoring never assumes lip closure implies a real consonant.
3. **Drift between the Python viseme list and `visemes.js`.** Mitigation: the cross-language test parses the JS array and fails on any mismatch.
4. **Sync drift caused by `setTimeout` accumulation.** Mitigation: the player never schedules visemes on timers; it samples `AudioContext.currentTime` every frame, and `visemeAt` is a pure function with its own tests.
5. **Base64 audio inflating the response.** Mitigation: 400-character cap on the request and a single sentence per call in this phase; streaming arrives with the conversation loop in Phase 4.

## Decision Summary

- Azure is the real provider for Phase 2 because it delivers native per-viseme audio offsets; the offline provider is deferred to its own phase.
- The mock provider is a first-class, explicitly selected provider, never a silent fallback, and it returns a genuine WAV.
- Visemes are served as `{t_ms, viseme, weight}` with timings converted from Azure ticks to milliseconds.
- Lip sync is driven by `AudioContext.currentTime` and a pure `visemeAt` function.
- Audio travels inline as base64: no files, no storage, one request.
- Sync accuracy is guaranteed by construction (offsets come from the engine, anchored to the audio start) and protected by node and e2e tests rather than by a measured 40 ms number in CI.
- The 15 viseme names have one source of truth per language, kept honest by a cross-language test.

## Open Questions

None blocking. Two deferred items: which offline engine to evaluate when the local provider phase arrives, and whether Phase 4 needs streaming synthesis for the latency target (it will, but it is out of this phase's scope).
