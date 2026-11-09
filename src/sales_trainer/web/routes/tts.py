import base64

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sales_trainer.voice.tts import get_provider
from sales_trainer.voice.tts.base import TTSUnavailable

router = APIRouter(prefix="/api", tags=["tts"])

MAX_TEXT_LENGTH = 400


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)


@router.post("/tts")
def synthesize(request: TTSRequest) -> dict[str, object]:
    try:
        result = get_provider().synthesize(request.text)
    except TTSUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return {
        "audio_base64": base64.b64encode(result.audio).decode("ascii"),
        "mime": result.mime,
        "visemes": [event.model_dump() for event in result.visemes],
    }
