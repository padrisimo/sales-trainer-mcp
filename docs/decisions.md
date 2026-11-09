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
