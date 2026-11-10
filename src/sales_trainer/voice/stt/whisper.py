import os
from typing import Any

from sales_trainer.voice.stt.base import STTResult, STTUnavailable, Word
from sales_trainer.voice.vad import decode_pcm16

DEFAULT_MODEL = "small"
LANGUAGE = "es"


def word_from_segment(word: Any) -> Word:
    """faster-whisper words carry seconds and a probability in [0, 1]."""
    start_ms = round(float(word.start) * 1000)
    return Word(
        word=str(word.word).strip(),
        start_ms=start_ms,
        end_ms=max(start_ms, round(float(word.end) * 1000)),
        probability=min(1.0, max(0.0, float(word.probability))),
    )


class WhisperSTTProvider:
    def __init__(self, model_name: str | None = None, model: Any = None) -> None:
        self._model_name = model_name or os.environ.get("SALES_TRAINER_WHISPER_MODEL", DEFAULT_MODEL)
        if model is not None:
            self._model = model
            return
        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(self._model_name, device="cpu", compute_type="int8")
        except (OSError, RuntimeError, ValueError) as error:
            raise STTUnavailable(f"whisper model {self._model_name} is unavailable: {error}") from error

    def transcribe(self, pcm16: bytes) -> STTResult:
        try:
            # A float32 array bypasses ffmpeg decoding entirely: no file, no temp WAV.
            segments, _info = self._model.transcribe(
                decode_pcm16(pcm16),
                language=LANGUAGE,
                word_timestamps=True,
                vad_filter=False,  # our VAD already cut the turn
            )
            texts: list[str] = []
            words: list[Word] = []
            for segment in segments:
                texts.append(segment.text.strip())
                words.extend(word_from_segment(word) for word in segment.words or [])
        except (OSError, RuntimeError, ValueError) as error:
            raise STTUnavailable(f"whisper transcription failed: {error}") from error
        return STTResult(text=" ".join(text for text in texts if text), language=LANGUAGE, words=words)
