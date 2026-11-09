# Design — Phase 0: MCP skeleton + FastAPI + browser

- **Date:** 2026-11-03
- **Topic:** fase0-esqueleto
- **Status:** Approved by the user

## Context

The `sales-trainer-mcp` repository is at the initial materialization stage: it still contains no source code (no `src/`, `pyproject.toml`, `tests/`), only the project documentation (`MEMORY.md`, `AGENTS.md`), the license and this spec.

`MEMORY.md` defines the product and the planned architecture:

- Product: voice sales trainer with a 3D avatar, STT/TTS, LLM, evaluation and a temperature gauge.
- Planned architecture:

```
opencode / Claude Code --stdio--> sales_trainer MCP server (FastMCP)
                                   | starts in a thread or child process
                                   v
                        FastAPI + uvicorn (127.0.0.1:PORT)
                                   | static HTTP + WebSocket
                                   v
                 Browser: Three.js + AudioWorklet + UI
```

- Critical rule: with the stdio transport, **stdout is reserved for the MCP protocol**; all logs go to stderr or a file.

## Goal

Provide the Phase 0 skeleton: an MCP server over stdio that, when the `sales_trainer_start` tool is invoked, starts a local FastAPI web server if it is not already running, opens the browser at `http://127.0.0.1:PORT/?session=<token>` and returns the URL and the session identifier.

## Acceptance Criteria

1. `sales_trainer_start(level, product_brief, language)` starts the web server if it is not active.
2. It opens the browser at `http://127.0.0.1:PORT/?session=<token>`.
3. It returns `{ url, session_id }`.
4. `sales_trainer_status` and `sales_trainer_stop` are usable at a minimum level.
5. The port is configurable through `SALES_TRAINER_PORT` (default `8765`) and the bind address is `127.0.0.1`.

## Non-Goals

- 3D avatar, audio, STT/TTS, LLM, evaluation, database, final UI and a working WebSocket. All of it arrives in later phases.
- Session persistence: the session token is generated per call and is not stored.
- Authentication beyond the random session token in the URL.

## Proposed Architecture

- **MCP layer:** `src/sales_trainer/mcp_server.py` uses the `mcp` SDK (`MCPServer`, transport stdio) and exposes `sales_trainer_start`, `sales_trainer_status` and `sales_trainer_stop`. `main()` runs `mcp.run(transport="stdio")`.
- **Web layer:** `src/sales_trainer/web/app.py` holds the FastAPI `app`. In this phase it serves a single `GET /` that returns a minimal HTML placeholder and echoes the `session` query parameter.
- **Bootstrap:** `_ensure_server()` builds a `uvicorn.Server` over the FastAPI app and runs it in a daemon thread named `uvicorn-sales-trainer`, waiting until `server.started` is true. Reused if the thread is alive.
- **Rationale for the daemon thread (Option A):** it is the smallest mechanism that meets the criterion, and the project memory explicitly allows "a thread or a child process". A child process would be cleaner long term but adds lifecycle and IPC work that Phase 0 does not need.
- **Shutdown:** `sales_trainer_stop` sets `should_exit` on the uvicorn server and joins the thread with a timeout.
- **Browser:** `webbrowser.open(url)`.
- **Package layout:** `pyproject.toml` with `module-name = "sales_trainer"` for `uv_build`, so the code lives in `src/sales_trainer/`.

## Files To Change

**New:**
- `pyproject.toml` — project metadata, pinned dependencies, `sales-trainer-mcp` script, `uv_build` backend, pytest config (`testpaths = ["tests"]`, marker `e2e`).
- `src/sales_trainer/__init__.py`
- `src/sales_trainer/mcp_server.py` — `MCPServer`, `build_url`, `_ensure_server`, the three tools and `main`.
- `src/sales_trainer/web/__init__.py`
- `src/sales_trainer/web/app.py` — FastAPI app with the placeholder `GET /`.
- `tests/unit/test_web_app.py` — placeholder returns 200 text/html and echoes the token.
- `tests/unit/test_mcp_server.py` — `build_url`, `start`, `status` and `stop` behaviour.
- `tests/e2e/test_web_server.py` — boots uvicorn through the CLI and asserts the page.

**Modified:** none (the repository had no code).

## Testing Strategy

- **Unit:** `TestClient` against the FastAPI app for the placeholder page; direct calls to the MCP module functions with `monkeypatch` for the server bootstrap and `webbrowser.open`, so no browser and no real server are needed.
- **E2E:** a subprocess runs `uv run uvicorn sales_trainer.web.app:app` on a test port, waits for readiness and asserts `200`, `text/html` and the echoed token. Marked `e2e`.
- **Commands:** `uv run pytest`, `uv run pytest -m e2e`, `uv run ruff check .`.

## Risks And Mitigations

1. **asyncio loop management when starting uvicorn in a thread.** Mitigation: let `uvicorn.Server.run()` create and own its loop inside the thread; the MCP side never touches that loop and only polls the `started` flag.
2. **Accidental writes to stdout breaking the MCP protocol.** Mitigation: uvicorn's logs go to stderr through its logging config, and the code never uses `print`.
3. **Port already in use.** Mitigation: `SALES_TRAINER_PORT` lets the user move the port; the error surfaces through uvicorn's log in the MCP client.

## Decision Summary

- uvicorn in a daemon thread inside the MCP process (not a child process).
- Bind `127.0.0.1`; port `8765` by default, `SALES_TRAINER_PORT` to override.
- Session token: a UUID per `sales_trainer_start` call, carried in the query string.
- Browser opened with `webbrowser.open`.
- Placeholder HTML on `GET /` until the UI phase.
- MCP transport stdio; stdout reserved for the protocol.

## Open Questions

None. The design was closed with user approval.
