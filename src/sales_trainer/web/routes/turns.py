from fastapi import APIRouter, Request

from sales_trainer.voice.turns import get_turn_store

router = APIRouter(prefix="/api", tags=["turns"])


@router.get("/turns")
def get_turns(request: Request) -> dict[str, list]:
    """Retrieve all turns for a given session session token.

    Query parameter ``session`` must match a registered session token.
    Returns ``{"turns": [...]}`` where each turn has ``text``, ``audio_ms``,
    and ``words`` fields.
    """
    session = request.query_params.get("session", "")
    store = get_turn_store()
    turns = store.list(session) if hasattr(store, "list") else []
    return {"turns": turns}