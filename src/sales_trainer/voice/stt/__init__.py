"""Speech to text providers: faster-whisper (default), azure and mock."""

import os

from sales_trainer.voice.stt.base import STTProvider, STTResult, STTUnavailable, Word

__all__ = [
    "STTProvider",
    "STTResult",
    "STTUnavailable",
    "Word",
    "get_stt_provider",
    "provider_name",
]

DEFAULT_PROVIDER = "faster-whisper"


def provider_name() -> str:
    return os.environ.get("SALES_TRAINER_STT", DEFAULT_PROVIDER).strip().lower()


def get_stt_provider() -> STTProvider:
    name = provider_name()
    if name == "mock":
        from sales_trainer.voice.stt.mock import MockSTTProvider

        return MockSTTProvider()
    if name == "faster-whisper":
        from sales_trainer.voice.stt.whisper import WhisperSTTProvider

        return WhisperSTTProvider()
    if name == "azure":
        from sales_trainer.voice.stt.azure import AzureSTTProvider

        return AzureSTTProvider()
    raise STTUnavailable(f"unknown SALES_TRAINER_STT value: {name}")
