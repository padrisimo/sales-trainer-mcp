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
