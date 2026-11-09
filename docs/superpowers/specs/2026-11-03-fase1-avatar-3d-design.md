# Design — Phase 1: procedural 3D avatar + `/debug/visemes` panel

- **Date:** 2026-11-03
- **Topic:** fase1-avatar-3d
- **Status:** Approved by the user (design) and by the user (spec)

## Context

Phase 0 left the project skeleton working: the MCP server (`src/sales_trainer/mcp_server.py`, `mcp` SDK 2.x, `MCPServer` class, stdio transport) starts uvicorn in a daemon thread with the FastAPI app from `src/sales_trainer/web/app.py`, which today serves a single `GET /` with placeholder HTML that echoes the session token. The suite has 7 green tests (4 MCP, 2 web, 1 e2e marked `e2e`) and `ruff` is clean.

There is no static directory, no 3D asset and no JS dependency yet. `MEMORY.md` requires the mouth animation to derive from **real phonemes with their real timings** and explicitly forbids animating from audio amplitude or randomly; the internal viseme set is the 15 Oculus values. It also requires JS served locally, **no CDN at runtime**, so the app works offline, and avatars without dubious licensing.

Phase 1 builds the piece Phase 2's TTS will stand on: a mesh with the 15 viseme morph targets and a debug page that exercises them one by one. There is no audio in this phase: only geometry, mapping and the debug view.

## Goal

Serve a Three.js scene with a procedural 3D head exposing the 15 Oculus viseme morph targets, breathing, blinking and micro-moving its head in an idle loop, plus a `/debug/visemes` page with one button per viseme that applies that morph target and shows which one is active.

## Acceptance Criteria

1. `GET /debug/visemes` responds `200` with `content-type: text/html`.
2. The page draws a visible 3D avatar in a `<canvas>` and exposes the active viseme and the list of the 15 names in `window.avatarDebug`.
3. There are exactly 15 viseme buttons plus a reset button; pressing one applies its morph target and updates the active viseme shown on screen.
4. The morph target names are exactly `sil, PP, FF, TH, DD, kk, CH, SS, nn, RR, aa, E, I, O, U`.
5. In idle the avatar blinks, breathes and micro-moves its head with no user interaction.
6. No resource is loaded from a CDN: Three.js is served from `/static/js/vendor/`.
7. `uv run ruff check .` is clean and the existing suite stays green.

## Non-Goals

- TTS, audio, phonemes and viseme timelines (Phase 2).
- The Python viseme table in `src/sales_trainer/voice/visemes.py` and its tests: without phonemes to map it would be dead code.
- The three characters and their differentiated avatars, the gauge-driven expressions and the reaction animations.
- The final session UI (levels, gauge, subtitles) and the reports.
- Any mouth animation derived from amplitude or random movement, forbidden by `MEMORY.md`.

## Proposed Architecture

**Three.js vendoring.** `three` is installed with npm at a pinned version (`0.187.0`, checked against the registry) and the two files the ESM build needs are copied: `build/three.module.js` (which imports `./three.core.js`) and `build/three.core.js`, both into `src/sales_trainer/web/static/js/vendor/`. They are served by the FastAPI process itself through `app.mount("/static", StaticFiles(directory=...), name="static")` (verified: `fastapi.staticfiles.StaticFiles` is importable in fastapi `0.162.0`). Reason: it honours the "no CDN at runtime" rule, adds no build dependency to the Python project and keeps the file versioned in git. Installing Three.js as a dev dependency with a bundler (Vite/esbuild) is discarded: it would add a whole build toolchain for a single ESM file.

**Procedural avatar.** The head is built in code in `avatar.js` with no external models: skull and jaw from deformed Three.js geometries, eyes and brows as separate meshes, and a mouth mesh carrying the 15 morph targets. Each viseme defines mouth vertex positions (aperture, width, rounding) and the morph target is created with `geometry.morphAttributes.position`. Reason: zero licensing, zero runtime downloads and full control over the morph target names, which is exactly what Phase 2 needs to hook into. A CC0 GLB/VRM with Oculus morph targets is discarded because it forces license verification, mapping of foreign names and extra repository weight.

**Module split.** `scene.js` (renderer, camera, lights, render loop and clock), `avatar.js` (mesh and morph target construction), `visemes.js` (the 15 names and the function that applies weights with smoothing) and `debug.js` (buttons, active state and `<canvas>`). `index.html` mounts the normal scene; `debug/visemes.html` mounts the same scene with the panel. Reason: Phase 2 will need `visemes.js` and `avatar.js` without dragging the debug panel along.

**Idle.** The render loop advances a clock and applies three independent procedural animations: periodic blinking (vertical scale of the eye meshes), breathing (smooth vertical offset of the head group) and micro head rotation with two sines of different periods. It never touches the viseme morph targets, so the debug panel does not compete with the idle: the active viseme is applied on top.

**Spherical mouth.** The head is a scaled sphere, so a flat mouth disc ends up buried in the skull and only its corners show. The mouth mesh recomputes each vertex's `z` from the skull surface at the deformed position, which keeps every viseme in front of the head.

**Routes.** `/debug/visemes` is served with `HTMLResponse` reading the file from the package (same pattern as the Phase 0 placeholder for `/`, no template engine). `GET /` now serves `index.html`, replacing the Phase 0 placeholder, because the avatar is the natural application view and keeping two dead HTML files would be worse. The session token echo that Phase 0 verified is preserved in `index.html`.

## Files To Change

**New:**
- `src/sales_trainer/web/static/js/vendor/three.module.js` — Three.js `0.187.0` copied from npm (imports `./three.core.js`).
- `src/sales_trainer/web/static/js/vendor/three.core.js` — ESM core the former depends on.
- `src/sales_trainer/web/static/js/visemes.js` — the 15 names, shape parameters and `weightsFor(name)`.
- `src/sales_trainer/web/static/js/avatar.js` — procedural head and the 15 morph targets.
- `src/sales_trainer/web/static/js/scene.js` — renderer, camera, lights, idle and loop.
- `src/sales_trainer/web/static/js/debug.js` — button panel and active viseme state.
- `src/sales_trainer/web/static/index.html` — full-screen scene.
- `src/sales_trainer/web/static/debug/visemes.html` — scene + panel.
- `src/sales_trainer/web/static/LICENSES.md` — Three.js license and origin.
- `tests/unit/test_debug_visemes_route.py` — `/debug/visemes` responds 200 text/html and loads the debug panel.
- `tests/js/avatar_smoke.mjs` — node smoke test: the list is exactly the 15 visemes, `createAvatar()` exposes 15 morph targets with those names, and every mouth vertex stays in front of the skull.
- `tests/unit/test_avatar_js.py` — runs the node smoke test as a pytest test, so it runs with the rest of the suite.
- `tests/e2e/test_debug_visemes_page.py` — Playwright: 15 buttons + reset, click each one, active state changes, no console errors.
- `package.json` / `package-lock.json` — pinned `three` for vendoring (`node_modules/` is gitignored).

**Modified:**
- `src/sales_trainer/web/app.py` — mount `/static`, serve `index.html` at `/` and `debug/visemes.html` at `/debug/visemes`.
- `pyproject.toml` — `playwright` added to the dev dependency group.
- `docs/decisions.md` — procedural avatar and Three.js vendoring decisions, with their limits.
- `AGENTS.md` — status when closing the phase.

`tests/unit/test_web_app.py` does not change: `index.html` keeps the "Sales Trainer" title and the token echo, which is exactly what it asserts.

## Testing Strategy

- **Unit (Python):** `TestClient` checks that `/debug/visemes` responds 200 with `text/html` and that the HTML loads `debug.js`; the Phase 0 `/` test stays as is.
- **Unit (node, via pytest):** `tests/js/avatar_smoke.mjs` imports `visemes.js` and `avatar.js` without a DOM, checks that the list is exactly the 15 Oculus visemes, that the mouth mesh exposes 15 morph targets with those names, and that every vertex of every morph target sits in front of the skull surface. Reason: the names are the contract with Phase 2 and must break the suite if someone touches them; it is also the only geometry check that does not depend on WebGL.
- **e2e (Playwright, headless Chromium):** starts uvicorn through the CLI on a test port, opens `/debug/visemes`, waits for `window.avatarDebug.ready`, counts the viseme buttons (15 + reset), presses each one and verifies that `window.avatarDebug.active` matches, and fails on any console error. Reason: it is the only way to check that the canvas renders and that the mapping really works.
- **Manual:** `/debug/visemes` with a human looking at the mouth, which is the real "every viseme looks correct" criterion.
- **Commands:** `uv run pytest` (unit + e2e), `uv run pytest -m e2e` (e2e only), `uv run ruff check .`.

## Risks And Mitigations

1. **No WebGL in headless Chromium.** Mitigation: launch Chromium with SwiftShader (`--use-angle=swiftshader`); this was verified to work in this environment. If it ever stops working, the e2e falls back to DOM and JS state and the limit is documented in `docs/decisions.md`; the visual check stays as a manual step.
2. **Morph target names drifting away from Phase 2.** Mitigation: the 15 names live in a single place (`visemes.js`) and the node smoke test fails on any rename or removal.
3. **A procedural avatar so ugly that visemes cannot be judged.** Mitigation: the mouth mesh stays simple and legible (aperture, width, rounding) and the panel shows the active viseme in text, so the criterion does not depend on aesthetics alone.
4. **Repository growth from versioning the Three.js ESM build** (~2 MB across `three.module.js` and `three.core.js`). Mitigation: only those two files are versioned, no `node_modules` (gitignored), which is the price of the no-CDN rule.

## Decision Summary

- Procedural avatar built in code; no external GLB/VRM models.
- A single avatar in this phase; per-character variation arrives with the character cards.
- Three.js `0.187.0` vendored in `static/js/vendor/` (`three.module.js` + `three.core.js`), served by FastAPI with `StaticFiles`; no CDN at runtime.
- The 15 Oculus viseme names are defined once, in `visemes.js`.
- `/` now serves the avatar; `/debug/visemes` serves the same scene with the panel.
- Mouth vertices follow the skull curvature so no viseme sinks into the head.
- Idle (blink, breathing, micro head) is separate from viseme control.
- The Python viseme table and all audio are left for Phase 2.
- No mouth animation from amplitude or randomness, under any circumstance.

## Open Questions

None blocking. The only deferred decision is whether the visual verification of the 15 visemes needs reference screenshots as well; it will be resolved while running the phase criterion in front of a browser.
