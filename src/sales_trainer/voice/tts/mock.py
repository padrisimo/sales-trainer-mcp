import io
import wave

from sales_trainer.voice.tts.base import TTSResult, VisemeEvent

SAMPLE_RATE = 24000
DURATION_MS = 1200

# Fixed test timeline. It never derives visemes from the audio: it is a double,
# not a fallback, and it is only reachable with SALES_TRAINER_TTS=mock.
TIMELINE = [
    (0, "sil"),
    (100, "aa"),
    (300, "PP"),
    (500, "E"),
    (800, "SS"),
    (1000, "sil"),
]


def silent_wav(duration_ms: int = DURATION_MS, sample_rate: int = SAMPLE_RATE) -> bytes:
    frames = int(sample_rate * duration_ms / 1000)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)
    return buffer.getvalue()


class MockTTSProvider:
    def synthesize(self, text: str, voice: str | None = None) -> TTSResult:
        visemes = [VisemeEvent(t_ms=t_ms, viseme=name, weight=1.0) for t_ms, name in TIMELINE]
        return TTSResult(audio=silent_wav(), visemes=visemes)
