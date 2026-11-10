from typing import Protocol

from pydantic import BaseModel, Field


class Word(BaseModel):
    word: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    probability: float = Field(ge=0.0, le=1.0)


class STTResult(BaseModel):
    text: str
    language: str = "es"
    words: list[Word] = Field(default_factory=list)


class STTUnavailable(RuntimeError):
    """Raised when the configured provider cannot transcribe."""


class STTProvider(Protocol):
    def transcribe(self, pcm16: bytes) -> STTResult: ...
