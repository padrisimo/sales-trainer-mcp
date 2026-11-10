import asyncio
import json
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, WebSocket

from sales_trainer.characters.loader import load_character, CharacterUnavailable
from sales_trainer.chat import (
    split_sentences,
    begin,
    call_judge_for_exchange,
    Conversation,
    Exchange,
)
from sales_trainer.llm import get_judge_provider
from sales_trainer.temperature.model import TemperatureModel
from sales_trainer.web.sessions import is_known, register

from sales_trainer.voice.stt import get_stt_provider
from sales_trainer.voice.stt.base import STTUnavailable
from sales_trainer.voice.turns import TurnDetector, get_turn_store, CHUNK_MS, SILENCE_MS, THRESHOLD
from sales_trainer.voice.vad import CHUNK_BYTES, SileroVAD
from sales_trainer.voice.tts import get_provider as get_tts_provider
from sales_trainer.voice.tts.base import TTSProvider, TTSUnavailable

router = APIRouter()

POLICY_VIOLATION = 1008
MIN_LEVEL = 1
MAX_LEVEL = 3


def allowed_origins() -> set[str]:
    port = int(os.environ.get("SALES_TRAINER_PORT", "8765"))
    return {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}


@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket, session: str = "", level: str = "1") -> None:
    await websocket.accept()
    origin = websocket.headers.get("origin", "")
    if origin not in allowed_origins():
        await websocket.send_json({"type": "error", "code": "origin", "message": f"origin not allowed: {origin or '(missing)'}"})
        await websocket.close(code=POLICY_VIOLATION)
        return
    if not is_known(session):
        await websocket.send_json({"type": "error", "code": "session", "message": "unknown session token"})
        await websocket.close(code=POLICY_VIOLATION)
        return
    if level not in (str(i) for i in range(MIN_LEVEL, MAX_LEVEL + 1)):
        await websocket.send_json({"type": "error", "code": "level", "message": f"level must be between {MIN_LEVEL} and {MAX_LEVEL}"})
        await websocket.close(code=POLICY_VIOLATION)
        return

    try:
        character = load_character(int(level))
    except CharacterUnavailable:
        await websocket.send_json({"type": "error", "code": "level", "message": f"level {level} not available"})
        await websocket.close(code=POLICY_VIOLATION)
        return

    try:
        stt_provider = get_stt_provider()
    except STTUnavailable as error:
        await websocket.send_json({"type": "error", "code": "stt", "message": str(error)})
        await websocket.close(code=POLICY_VIOLATION)
        return

    try:
        vad = SileroVAD()
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        await websocket.send_json({"type": "error", "code": "vad", "message": str(error)})
        await websocket.close(code=POLICY_VIOLATION)
        return

    tts_provider = get_tts_provider()
    conversation = Conversation(character=character, product_brief="")
    temperature_model = TemperatureModel(
        sensitivity=float(os.environ.get("SALES_TRAINER_TEMP_SENSITIVITY", "1.0")),
        max_delta=int(os.environ.get("SALES_TRAINER_TEMP_MAX_DELTA", "15")),
        moving_average_window=int(os.environ.get("SALES_TRAINER_TEMP_WINDOW", "3")),
        min_delta=int(os.environ.get("SALES_TRAINER_TEMP_MIN_DELTA", "1")),
    )
    judge_provider = get_judge_provider()

    await websocket.send_json({"type": "ready", "character": {"id": character["level"], "name": character["name"], "level": character["level"], "max_turns": character["max_turns"]}, "turns": 0})

    # Handler loop (simplified): capture VAD chunks, detect turn boundaries,
    # on turn_end: call judge, update temperature, send gauge.
    # Mensaje gauge que se envía al cliente:
    #   await websocket.send_json({"type": "gauge", "temperature": tm.current_temp, "cause": conversation.last_cause})
