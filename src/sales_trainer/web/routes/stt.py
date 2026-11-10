from fastapi import APIRouter

from sales_trainer.voice.turns import get_turn_store

router = APIRouter(prefix="/api", tags=["stt"])


@router.get("/turns")
def list_turns(session: str = "") -> dict[str, list[dict[str, object]]]:
    return {
        "turns": [
            {
                "audio_ms": turn.audio_ms,
                "text": turn.text,
                "language": turn.language,
                "words": [word.model_dump() for word in turn.words],
            }
            for turn in get_turn_store().list(session)
        ]
    }
