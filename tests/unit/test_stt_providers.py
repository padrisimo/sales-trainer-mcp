from types import SimpleNamespace

import pytest

from sales_trainer.voice.stt import get_stt_provider, provider_name
from sales_trainer.voice.stt.azure import AzureSTTProvider, words_from_json
from sales_trainer.voice.stt.base import STTUnavailable
from sales_trainer.voice.stt.mock import MockSTTProvider
from sales_trainer.voice.stt.whisper import WhisperSTTProvider, word_from_segment


class FakeWhisperModel:
    def __init__(self, segments: list) -> None:
        self._segments = segments
        self.kwargs: dict = {}

    def transcribe(self, audio, **kwargs):
        self.kwargs = kwargs
        return iter(self._segments), SimpleNamespace(language="es")


class FailingWhisperModel:
    def transcribe(self, audio, **kwargs):
        raise OSError("model not downloaded")


def test_whisper_word_converts_seconds_to_milliseconds() -> None:
    word = word_from_segment(SimpleNamespace(word=" Hola,", start=1.234, end=1.5, probability=0.91))
    assert word.word == "Hola,"
    assert word.start_ms == 1234
    assert word.end_ms == 1500
    assert word.probability == 0.91


def test_whisper_joins_segments_and_keeps_word_timings() -> None:
    segments = [
        SimpleNamespace(
            text=" Hola, soy Marta.",
            words=[
                SimpleNamespace(word=" Hola,", start=0.0, end=0.4, probability=0.98),
                SimpleNamespace(word=" soy", start=0.4, end=0.7, probability=0.9),
            ],
        ),
        SimpleNamespace(
            text=" ¿Qué tal?",
            words=[SimpleNamespace(word=" ¿Qué", start=0.8, end=1.0, probability=0.8)],
        ),
    ]
    model = FakeWhisperModel(segments)
    result = WhisperSTTProvider(model=model).transcribe(b"\x00\x00" * 16000)

    assert result.text == "Hola, soy Marta. ¿Qué tal?"
    assert result.language == "es"
    assert [word.word for word in result.words] == ["Hola,", "soy", "¿Qué"]
    assert [word.start_ms for word in result.words] == [0, 400, 800]
    assert model.kwargs["language"] == "es"
    assert model.kwargs["word_timestamps"] is True
    assert model.kwargs["vad_filter"] is False


def test_whisper_failure_raises_unavailable() -> None:
    provider = WhisperSTTProvider(model=FailingWhisperModel())
    with pytest.raises(STTUnavailable):
        provider.transcribe(b"\x00\x00" * 16000)


def test_azure_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    # An empty argument means "fall back to the environment", so clear it too.
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    with pytest.raises(STTUnavailable):
        AzureSTTProvider(key="", region="")


def test_azure_words_are_parsed_from_ticks() -> None:
    payload = {
        "DisplayText": "Hola, soy Marta.",
        "NBest": [
            {
                "Confidence": 0.92,
                "Words": [
                    {"Word": "hola", "Offset": 1_200_000, "Duration": 4_000_000, "Confidence": 0.98},
                    {"Word": "marta", "Offset": 5_500_000, "Duration": 3_000_000, "Confidence": 0.91},
                ],
            }
        ],
    }
    words = words_from_json(payload)
    spans = [(word.word, word.start_ms, word.end_ms) for word in words]
    assert spans == [("hola", 120, 520), ("marta", 550, 850)]
    assert [word.probability for word in words] == [0.98, 0.91]


def test_azure_word_probability_is_clamped() -> None:
    payload = {"NBest": [{"Words": [{"Word": "hola", "Offset": 0, "Duration": 10_000, "Confidence": 1.4}]}]}
    assert words_from_json(payload)[0].probability == 1.0


def test_the_default_provider_name_is_faster_whisper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SALES_TRAINER_STT", raising=False)
    assert provider_name() == "faster-whisper"


def test_mock_is_selected_by_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SALES_TRAINER_STT", "mock")
    assert isinstance(get_stt_provider(), MockSTTProvider)


def test_an_unknown_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SALES_TRAINER_STT", "carrier-pigeon")
    with pytest.raises(STTUnavailable):
        get_stt_provider()


def test_azure_without_credentials_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SALES_TRAINER_STT", "azure")
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    with pytest.raises(STTUnavailable):
        get_stt_provider()
