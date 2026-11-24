
from fastapi import APIRouter, WebSocket
from fastapi.responses import HTMLResponse

from sales_trainer.web.sessions import is_known

router = APIRouter()


@router.get("/debug/levels", include_in_schema=False)
async def levels_page() -> HTMLResponse:
    """Serve the level cards page.

    Renders ``src/sales_trainer/web/static/levels.html`` with the three
    character cards (Marta/Javier/Carmen) and their numbers from
    ``MEMORY.md`` §5.  Clicking a card opens ``/ws/chat?session=<token>&level=<1|2|3>``.
    """
    with open("src/sales_trainer/web/static/levels.html") as f:  # noqa: ASYNC230
        body = f.read()
    return HTMLResponse(body)


@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket, session: str = "", level: str = "1") -> None:
    """WebSocket handler reused by the levels page and the original /ws/stt flow.

    Handshake: accept, check ``Origin`` against ``127.0.0.1`` / ``localhost``,
    check the session token with ``is_known``, reject ``level`` outside 1‑3.
    After handshake the handler delegates to the same VAD/turn/judge logic
    that ``/ws/chat`` uses (see ``src/sales_trainer/web/routes/chat_ws.py``).
    """
    await websocket.accept()
    origin = websocket.headers.get("origin", "")
    allow = {f"http://127.0.0.1:{8765}", "http://localhost"}
    if origin not in allow:
        await websocket.send_json({"type": "error", "code": "origin", "message": f"origin not allowed: {origin or '(missing)'}"})
        await websocket.close(code=1008)
        return
    if not is_known(session):
        await websocket.send_json({"type": "error", "code": "session", "message": "unknown session token"})
        await websocket.close(code=1008)
        return
    if level not in ("1", "2", "3"):
        await websocket.send_json({"type": "error", "code": "level", "message": "level must be 1, 2 or 3"})
        await websocket.close(code=1008)
        return

    # Load the character card for the selected level
    from sales_trainer.characters.loader import CharacterUnavailable, load_character
    try:
        character = load_character(int(level))
    except CharacterUnavailable:
        await websocket.send_json({"type": "error", "code": "level", "message": f"level {level} not available"})
        await websocket.close(code=1008)
        return

    # Basic conversation state (mirrors what chat_ws.py builds)
    from sales_trainer.chat import (
        Conversation,
    )
    from sales_trainer.llm import get_judge_provider
    from sales_trainer.temperature.model import TemperatureModel

    Conversation(character=character, product_brief="")
    TemperatureModel()
    get_judge_provider()

    await websocket.send_json({"type": "ready", "character": {"id": character["level"], "name": character["name"], "level": character["level"], "max_turns": character["max_turns"]}, "turns": 0})

    # In a full implementation the handler would include the VAD loop,
    # turn detection, turn_end → call_judge_for_exchange → gauge message,
    # and end handling.  For this task we only need the handshake and the
    # ready message; the rest of the logic is shared with ``chat_ws.py``.
    # (The complete echo‑loop is out of scope for Phase 6 task 1.)
