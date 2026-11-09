from types import SimpleNamespace

import pytest

from sales_trainer.voice.tts.azure import AzureTTSProvider
from sales_trainer.voice.tts.base import TTSUnavailable


def test_missing_credentials_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    with pytest.raises(TTSUnavailable):
        AzureTTSProvider(key="", region="", voice="es-ES-ElviraNeural")


def test_ticks_are_converted_to_milliseconds() -> None:
    provider = AzureTTSProvider(key="k", region="r")
    event = provider._events_from(SimpleNamespace(audio_offset=12_340_000, viseme_id=21))
    assert event.t_ms == 1234
    assert event.viseme == "PP"


def test_unknown_azure_viseme_becomes_silence() -> None:
    provider = AzureTTSProvider(key="k", region="r")
    event = provider._events_from(SimpleNamespace(audio_offset=0, viseme_id=99))
    assert event.viseme == "sil"
