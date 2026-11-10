from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from sales_trainer.web.routes import stt as stt_routes
from sales_trainer.web.routes import stt_ws as stt_ws_routes
from sales_trainer.web.routes import tts as tts_routes
from sales_trainer.web.sessions import register

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Sales Trainer")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(tts_routes.router)
app.include_router(stt_routes.router)
app.include_router(stt_ws_routes.router)


def _page(relative: str, session: str) -> HTMLResponse:
    register(session)
    html = (STATIC_DIR / relative).read_text(encoding="utf-8")
    return HTMLResponse(content=html.replace("__SESSION_TOKEN__", session), media_type="text/html")


@app.get("/")
async def root(session: str = "") -> HTMLResponse:
    return _page("index.html", session)


@app.get("/debug/visemes")
async def debug_visemes(session: str = "") -> HTMLResponse:
    return _page("debug/visemes.html", session)


@app.get("/debug/tts")
async def debug_tts(session: str = "") -> HTMLResponse:
    return _page("debug/tts.html", session)


@app.get("/debug/stt")
async def debug_stt(session: str = "") -> HTMLResponse:
    return _page("debug/stt.html", session)
