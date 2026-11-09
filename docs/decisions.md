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
