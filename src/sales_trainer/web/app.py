from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Sales Trainer")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _page(relative: str, session: str) -> HTMLResponse:
    html = (STATIC_DIR / relative).read_text(encoding="utf-8")
    return HTMLResponse(content=html.replace("__SESSION_TOKEN__", session), media_type="text/html")


@app.get("/")
async def root(session: str = "") -> HTMLResponse:
    return _page("index.html", session)


@app.get("/debug/visemes")
async def debug_visemes(session: str = "") -> HTMLResponse:
    return _page("debug/visemes.html", session)
