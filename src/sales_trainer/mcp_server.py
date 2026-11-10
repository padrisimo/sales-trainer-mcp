import os
import threading
import time
import uuid
import webbrowser

import uvicorn
from mcp.server.mcpserver import MCPServer

from sales_trainer.web.app import app
from sales_trainer.web.sessions import register

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
    register(token)  # the socket only accepts tokens the server issued or served
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
