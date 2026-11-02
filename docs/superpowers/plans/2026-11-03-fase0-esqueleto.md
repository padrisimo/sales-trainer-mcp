# Fase 0: Esqueleto del MCP + FastAPI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-subagent-driven-development (recommended) or superpowers-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Desde una sesión de opencode o Claude Code, invocar la herramienta MCP `sales_trainer_start` arranque el servidor web local, abra el navegador en `http://127.0.0.1:PORT/?session=<token>` y devuelva `{ url, session_id }`, con las herramientas `sales_trainer_status` y `sales_trainer_stop` operables como mínimo.

**Architecture:** El servidor MCP (SDK `mcp`, clase `MCPServer`, transporte stdio) corre en el proceso de la host (opencode / Claude Code); un thread daemon arranca uvicorn sobre la aplicación FastAPI definida en `src/sales_trainer/web/app.py`, con un event loop dedicado en ese thread, sobre `127.0.0.1` con el puerto configurable por variable de entorno (default `8765`). El placeholder HTML se sirve en `GET /` y el token de sesión es un UUID incluido en el query string de la URL.

**Tech Stack:** Python 3.11+, SDK `mcp` (>=2.3.0, clase `MCPServer`), FastAPI, uvicorn[standard], pydantic v2, httpx; pytest, pytest-asyncio y ruff; uv como gestor de entorno. El transporte MCP es stdio (stdout reservado al protocolo, logs a stderr); el servidor web se publica solo en `127.0.0.1`.

---

## Scope note

- The approved spec assumed the repository already contained `pyproject.toml` and `src/`; because it did not, Tasks 1-3 bootstrap the minimal packaging and package structure needed by the rest of the plan.
- Out of scope (per approved spec): avatar, audio, STT/TTS, LLM, evaluation, database, final UI and functional WebSocket.

## Tasks

### Task 1: Scaffold the uv project packaging

**Files:**
- Create: `pyproject.toml`
- Create: `src/sales_trainer/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

Full content of `pyproject.toml`:

```toml
[project]
name = "sales-trainer-mcp"
version = "0.1.0"
description = "Entrenador de ventas por voz con avatar 3D, STT/TTS, LLM y evaluación"
requires-python = ">=3.11"
dependencies = [
    "mcp[cli]>=2.3.0",
    "fastapi>=0.162.0",
    "uvicorn[standard]>=0.54.0",
    "pydantic>=2.14.2",
    "httpx>=0.28.1",
]

[project.scripts]
sales-trainer-mcp = "sales_trainer.mcp_server:main"

[build-system]
requires = ["uv_build>=0.12.24,<0.13.0"]
build-backend = "uv_build"

[dependency-groups]
dev = [
    "pytest>=9.2.0",
    "pytest-asyncio>=1.4.1.post1",
    "ruff>=0.17.3",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "e2e: end-to-end tests that boot real server processes",
]
```

- [ ] **Step 2: Create `src/sales_trainer/__init__.py`**

Full content of `src/sales_trainer/__init__.py`:

```python
"""Sales Trainer MCP package."""
```

- [ ] **Step 3: Install dependencies**

Run: `uv sync`

Expected: exit code 0; the command resolves and installs the locked dependencies and exits without errors.

- [ ] **Step 4: Verify the package imports**

Run: `uv run python -c "import sales_trainer"`

Expected: exit code 0, no output.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/sales_trainer/__init__.py
git commit -m "chore: scaffold uv project for sales-trainer-mcp"
```

### Task 2: Write failing tests for the web placeholder page

**Files:**
- Create: `tests/unit/test_web_app.py`

- [ ] **Step 1: Write the failing tests**

Full content of `tests/unit/test_web_app.py`:

```python
from fastapi.testclient import TestClient

from sales_trainer.web.app import app

client = TestClient(app)


def test_root_returns_placeholder_html() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Sales Trainer" in response.text


def test_root_echoes_session_token() -> None:
    response = client.get("/?session=token-123")
    assert response.status_code == 200
    assert "token-123" in response.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_web_app.py -v`

Expected: FAIL — exit code 1; key output line: `ModuleNotFoundError: No module named 'sales_trainer.web.app'`.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_web_app.py
git commit -m "test: add failing tests for web placeholder"
```

### Task 3: Create the FastAPI placeholder app

**Files:**
- Create: `src/sales_trainer/web/__init__.py`
- Create: `src/sales_trainer/web/app.py`

- [ ] **Step 1: Create the web package init and the FastAPI app**

Full content of `src/sales_trainer/web/__init__.py`:

```python
"""Web module for the Sales Trainer MCP."""
```

Full content of `src/sales_trainer/web/app.py`:

```python
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Sales Trainer")


PLACEHOLDER_HTML = """<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <title>Sales Trainer</title>
  </head>
  <body>
    <h1>Sales Trainer</h1>
    <p>Placeholder page. The conversational UI arrives in a later phase.</p>
    <p>session: __SESSION_TOKEN__</p>
  </body>
</html>
"""


@app.get("/")
async def root(session: str = "") -> HTMLResponse:
    html = PLACEHOLDER_HTML.replace("__SESSION_TOKEN__", session)
    return HTMLResponse(content=html, media_type="text/html")
```

- [ ] **Step 2: Run the web tests to verify they pass**

Run: `uv run pytest tests/unit/test_web_app.py -v`

Expected: exit code 0; key output line: `tests/unit/test_web_app.py . [100%] 2 passed`.

- [ ] **Step 3: Commit**

```bash
git add src/sales_trainer/web/__init__.py src/sales_trainer/web/app.py
git commit -m "feat: add FastAPI placeholder web app"
```

### Task 4: Write failing tests for the MCP server tools and helpers

**Files:**
- Create: `tests/unit/test_mcp_server.py`

- [ ] **Step 1: Write the failing tests**

Full content of `tests/unit/test_mcp_server.py`:

```python
import pytest

from sales_trainer import mcp_server


def test_build_url_uses_local_host_and_token() -> None:
    url = mcp_server.build_url(port=8765, token="token-123")
    assert url == "http://127.0.0.1:8765/?session=token-123"


def test_start_returns_url_and_session_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "_ensure_server", lambda: None)
    monkeypatch.setattr(mcp_server.webbrowser, "open", lambda url: True)

    result = mcp_server.start(level=1, product_brief=None, language="es")

    assert set(result) == {"url", "session_id"}
    assert result["url"] == f"http://127.0.0.1:8765/?session={result['session_id']}"
    assert result["session_id"]


def test_status_returns_not_running_when_server_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "_server", None)
    monkeypatch.setattr(mcp_server, "_thread", None)
    assert mcp_server.status() == {"running": False}


def test_stop_is_safe_when_server_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "_server", None)
    monkeypatch.setattr(mcp_server, "_thread", None)
    assert mcp_server.stop() == {"running": False}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_mcp_server.py -v`

Expected: FAIL — exit code 1; key output line: `ModuleNotFoundError: No module named 'sales_trainer.mcp_server'`.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_mcp_server.py
git commit -m "test: add failing tests for MCP server skeleton"
```

### Task 5: Create the MCP server module with the uvicorn bootstrap

**Files:**
- Create: `src/sales_trainer/mcp_server.py`

- [ ] **Step 1: Create `src/sales_trainer/mcp_server.py`**

Full content of `src/sales_trainer/mcp_server.py`:

```python
import os
import threading
import time
import uuid
import webbrowser

import uvicorn
from mcp.server.mcpserver import MCPServer

from sales_trainer.web.app import app

mcp = MCPServer(name="sales-trainer")

PORT = int(os.environ.get("SALES_TRAINER_PORT", "8765"))

_server: uvicorn.Server | None = None
_thread: threading.Thread | None = None


def build_url(port: int = PORT, token: str = "") -> str:
    return f"http://127.0.0.1:{port}/?session={token}"


def _ensure_server() -> uvicorn.Server:
    global _server, _thread
    if _server is not None and _thread is not None and _thread.is_alive():
        return _server
    server = uvicorn.Server(uvicorn.Config(app=app, host="127.0.0.1", port=PORT, log_level="info"))
    _server = server
    _thread = threading.Thread(target=server.run, daemon=True, name="uvicorn-sales-trainer")
    _thread.start()
    while not server.started:
        time.sleep(0.05)
    return server


@mcp.tool(name="sales_trainer_start", description="Arranca el servidor web local y abre el navegador")
def start(level: int = 1, product_brief: str | None = None, language: str = "es") -> dict[str, str]:
    token = str(uuid.uuid4())
    url = build_url(port=PORT, token=token)
    _ensure_server()
    webbrowser.open(url)
    return {"url": url, "session_id": token}


@mcp.tool(name="sales_trainer_status", description="Estado del servidor web local")
def status() -> dict[str, bool]:
    running = _server is not None and _thread is not None and _thread.is_alive()
    return {"running": running}


@mcp.tool(name="sales_trainer_stop", description="Detener el servidor web local")
def stop() -> dict[str, bool]:
    global _server, _thread
    if _server is not None and _thread is not None and _thread.is_alive():
        _server.should_exit = True
        _thread.join(timeout=10)
    _server = None
    _thread = None
    return {"running": False}


def main() -> None:
    mcp.run(transport="stdio")
```

- [ ] **Step 2: Verify the MCP server module imports**

Run: `uv run python -c "from sales_trainer import mcp_server; print(mcp_server.mcp.name)"`

Expected: exit code 0; key output line: `sales-trainer`.

- [ ] **Step 3: Run the MCP server tests**

Run: `uv run pytest tests/unit/test_mcp_server.py -v`

Expected: exit code 0; key output line: `tests/unit/test_mcp_server.py .... [100%] 4 passed`.

- [ ] **Step 4: Run the linter**

Run: `uv run ruff check .`

Expected: exit code 0; key output line: `All checks passed!`.

- [ ] **Step 5: Commit**

```bash
git add src/sales_trainer/mcp_server.py
git commit -m "feat: add MCP server with uvicorn bootstrap"
```

### Task 6: Run the unit test suite and the linter

- [ ] **Step 1: Run the full unit test suite**

Run: `uv run pytest -v`

Expected: exit code 0; summary line: `6 passed`.

- [ ] **Step 2: Run the linter**

Run: `uv run ruff check .`

Expected: exit code 0; key output line: `All checks passed!`.

### Task 7: Add the end-to-end smoke test for the web server

**Files:**
- Create: `tests/e2e/test_web_server.py`

- [ ] **Step 1: Create the end-to-end smoke test**

Full content of `tests/e2e/test_web_server.py`:

```python
import subprocess
import time
import urllib.request

PORT = 8123
BASE_URL = f"http://127.0.0.1:{PORT}"


def _wait_for_server(timeout_seconds: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = urllib.request.urlopen(f"{BASE_URL}/?session=smoke", timeout=2)
            try:
                if response.status == 200:
                    return
            finally:
                response.close()
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("web server did not become ready in time")


def test_web_server_serves_placeholder() -> None:
    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "sales_trainer.web.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_server()
        response = urllib.request.urlopen(f"{BASE_URL}/?session=smoke-token", timeout=10)
        try:
            assert response.status == 200
            assert "text/html" in response.headers["Content-Type"]
            assert "smoke-token" in response.read().decode()
        finally:
            response.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
```

- [ ] **Step 2: Run the end-to-end smoke test**

Run: `uv run pytest -m e2e -v`

Expected: exit code 0; key output line: `tests/e2e/test_web_server.py . [100%] 1 passed`.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_web_server.py
git commit -m "test: add e2e smoke test for web server"
```

### Task 8: Run the full test suite and the linter

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -v`

Expected: exit code 0; summary line: `7 passed`.

- [ ] **Step 2: Run the linter**

Run: `uv run ruff check .`

Expected: exit code 0; key output line: `All checks passed!`.

### Task 9: Close out phase 0 documentation status

- [ ] **Step 1: Update the phase status in `AGENTS.md`**

Edit `AGENTS.md`:

Before:

```
- Fase actual: 0 (esqueleto). En curso: esqueleto del MCP + FastAPI + navegador (spec aprobado, plan en preparación).
- Actualizar aquí al cerrar cada fase.
```

After:

```
- Fase actual: 1 (avatar 3D). En curso: avatar 3D con idle y panel `/debug/visemes`.
- Actualizar aquí al cerrar cada fase.
```

- [ ] **Step 2: Create `docs/decisions.md`**

Full content of `docs/decisions.md`:

```markdown
# Decisiones del proyecto

## 2026-11-03 — Fase 0: arranque del servidor web (esqueleto)

- **Decisión:** el servidor web (FastAPI + uvicorn) arranca en un thread daemon dentro del proceso MCP (SDK `mcp`, clase `MCPServer`, transporte stdio).
- **Alternativa descartada:** proceso hijo del MCP.
- **Motivo:** menor complejidad de gestión en Fase 0; la memoria del proyecto contempla «arranca en un hilo o proceso hijo».
- **Consecuencias:** el thread daemon construye la app FastAPI desde `src/sales_trainer/web/app.py` y arranca uvicorn sobre ella; bind `127.0.0.1`, puerto por defecto `8765` configurable con `SALES_TRAINER_PORT`.
```

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md docs/decisions.md
git commit -m "docs: close out fase 0"
```

---

## Spec coverage

- Acceptance criterion 1 (`sales_trainer_start(level, product_brief, language)` arranca el servidor web si no está activo): created in Task 5 (`start` + `_ensure_server`).
- Acceptance criterion 2 (abre el navegador en `http://127.0.0.1:PORT/?session=<token>`): created in Task 5 (`webbrowser.open` with `build_url`).
- Acceptance criterion 3 (devuelve `{ url, session_id }`): created in Task 5, covered by tests in Task 4 and verified in Task 5.
- Acceptance criterion 4 (`sales_trainer_status` / `sales_trainer_stop` operables como mínimo): created in Task 5, covered by tests in Task 4.
- Bind `127.0.0.1`, puerto configurable por variable de entorno (default `8765`), UUID de sesión, transporte stdio con logs a stderr, placeholder en `GET /`: created in Tasks 3-5.

## Execution order

Tasks are ordered so each task's tests are red before the implementation task and green afterwards:

1. Task 1: scaffold packaging (no tests yet).
- Task 2: write failing web tests.
- Task 3: create web app (web tests turn green).
- Task 4: write failing MCP server tests.
- Task 5: create MCP server (MCP tests turn green).
- Task 6: run unit suite and linter.
- Task 7: add e2e smoke test and run it.
- Task 8: run full suite and linter.
- Task 9: close out documentation status.
