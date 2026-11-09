import os

from sales_trainer.voice.tts.base import (
    TTSProvider,
    TTSResult,
    TTSUnavailable,
    VisemeEvent,
)
from sales_trainer.voice.tts.mock import MockTTSProvider

__all__ = ["TTSProvider", "TTSResult", "TTSUnavailable", "VisemeEvent", "get_provider"]


def get_provider() -> TTSProvider:
    name = os.environ.get("SALES_TRAINER_TTS", "azure").lower()
    if name == "mock":
        return MockTTSProvider()
    if name == "azure":
        # Imported lazily so the mock path never imports the Azure SDK.
        from sales_trainer.voice.tts.azure import AzureTTSProvider

        return AzureTTSProvider()
    raise TTSUnavailable(f"unknown SALES_TRAINER_TTS value: {name}")
