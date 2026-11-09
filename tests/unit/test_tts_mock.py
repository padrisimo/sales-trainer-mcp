import io
import wave

from sales_trainer.voice.tts.mock import DURATION_MS, SAMPLE_RATE, MockTTSProvider
from sales_trainer.voice.visemes import VISEMES


def test_mock_returns_a_playable_wav() -> None:
    result = MockTTSProvider().synthesize("Hola, soy Marta.")
    with wave.open(io.BytesIO(result.audio), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == SAMPLE_RATE
        duration_ms = 1000 * wav.getnframes() / wav.getframerate()
    assert round(duration_ms) == DURATION_MS
    assert result.mime == "audio/wav"


def test_mock_timeline_is_ordered_and_inside_the_audio() -> None:
    result = MockTTSProvider().synthesize("Hola.")
    times = [event.t_ms for event in result.visemes]
    assert times == sorted(times)
    assert max(times) < DURATION_MS


def test_mock_timeline_uses_known_visemes() -> None:
    result = MockTTSProvider().synthesize("Hola.")
    assert {event.viseme for event in result.visemes} <= set(VISEMES)
    assert all(event.weight == 1.0 for event in result.visemes)
