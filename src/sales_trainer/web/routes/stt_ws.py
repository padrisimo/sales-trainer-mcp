import asyncio
import os
from dataclasses import replace

from fastapi import APIRouter, WebSocket

from sales_trainer.voice.stt import get_stt_provider
from sales_trainer.voice.stt.base import STTUnavailable
from sales_trainer.voice.turns import CHUNK_MS, SILENCE_MS, TurnDetector, get_turn_store
from sales_trainer.voice.vad import CHUNK_BYTES, SileroVAD
from sales_trainer.web.sessions import is_known

router = APIRouter()

POLICY_VIOLATION = 1008
LEVEL_EVERY_CHUNKS = 3


def allowed_origins() -> set[str]:
    port = os.environ.get("SALES_TRAINER_PORT", "8765")
    return {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}


def _make_vad() -> SileroVAD:
    return SileroVAD()


async def _reject(websocket: WebSocket, code: str, message: str) -> None:
    await websocket.send_json({"type": "error", "code": code, "message": message})
    await websocket.close(code=POLICY_VIOLATION)


@router.websocket("/ws/stt")
async def stt_socket(websocket: WebSocket, session: str = "") -> None:
    await websocket.accept()
    origin = websocket.headers.get("origin", "")
    if origin not in allowed_origins():
        await _reject(websocket, "origin", f"origin not allowed: {origin or '(missing)'}")
        return
    if not is_known(session):
        await _reject(websocket, "session", "unknown session token")
        return
    try:
        provider = get_stt_provider()
    except STTUnavailable as error:
        await _reject(websocket, "stt", str(error))
        return
    try:
        vad = _make_vad()
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        await _reject(websocket, "vad", str(error))
        return

    silence_ms = int(os.environ.get("SALES_TRAINER_SILENCE_MS", str(SILENCE_MS)))
    detector = TurnDetector(silence_ms=silence_ms)
    store = get_turn_store()
    await websocket.send_json({"type": "ready"})

    elapsed_ms = 0
    peak = 0.0
    chunks_since_level = 0
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        chunk = message.get("bytes")
        if chunk is None or len(chunk) != CHUNK_BYTES:
            continue

        elapsed_ms += CHUNK_MS
        probability = vad.probability(chunk)
        peak = max(peak, probability)
        chunks_since_level += 1
        if chunks_since_level >= LEVEL_EVERY_CHUNKS:
            await websocket.send_json({"type": "level", "probability": round(peak, 3)})
            peak = 0.0
            chunks_since_level = 0

        update = detector.push(chunk, probability)
        if update.started:
            await websocket.send_json({"type": "turn_start", "t_ms": elapsed_ms})
        if update.ended is None:
            continue

        turn = update.ended
        await websocket.send_json({"type": "turn_end", "t_ms": elapsed_ms, "audio_ms": turn.audio_ms})
        if update.discarded:
            continue

        try:
            # whisper blocks for seconds; a worker thread keeps the socket responsive.
            result = await asyncio.to_thread(provider.transcribe, turn.audio)
        except STTUnavailable as error:
            await websocket.send_json({"type": "error", "code": "stt", "message": str(error)})
            continue

        turn = replace(turn, text=result.text, language=result.language, words=result.words)
        store.add(session, turn)
        await websocket.send_json(
            {
                "type": "transcript",
                "text": turn.text,
                "language": turn.language,
                "words": [word.model_dump() for word in turn.words],
            }
        )
