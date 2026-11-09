from typing import Protocol

from pydantic import BaseModel, Field


class VisemeEvent(BaseModel):
    t_ms: int = Field(ge=0)
    viseme: str
    weight: float = Field(ge=0.0, le=1.0)


class TTSResult(BaseModel):
    audio: bytes
    mime: str = "audio/wav"
    visemes: list[VisemeEvent]


class TTSUnavailable(RuntimeError):
    """Raised when the configured provider cannot synthesize."""


class TTSProvider(Protocol):
    def synthesize(self, text: str, voice: str | None = None) -> TTSResult: ...
