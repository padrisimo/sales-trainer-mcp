import json
import os
from typing import Any

import azure.cognitiveservices.speech as speechsdk

from sales_trainer.voice.stt.base import STTResult, STTUnavailable, Word

LANGUAGE = "es"
SPEECH_LANGUAGE = "es-ES"
TICKS_PER_MS = 10_000


def words_from_json(payload: dict[str, Any]) -> list[Word]:
    """Azure returns word offsets and durations in ticks of 100 ns."""
    best = (payload.get("NBest") or [{}])[0]
    words: list[Word] = []
    for item in best.get("Words", []):
        offset = int(item.get("Offset", 0))
        start_ms = offset // TICKS_PER_MS
        end_ms = max(start_ms, (offset + int(item.get("Duration", 0))) // TICKS_PER_MS)
        words.append(
            Word(
                word=str(item.get("Word", "")),
                start_ms=start_ms,
                end_ms=end_ms,
                probability=min(1.0, max(0.0, float(item.get("Confidence", 0.0)))),
            )
        )
    return words


class AzureSTTProvider:
    def __init__(self, key: str | None = None, region: str | None = None) -> None:
        self._key = key or os.environ.get("AZURE_SPEECH_KEY", "")
        self._region = region or os.environ.get("AZURE_SPEECH_REGION", "")
        if not self._key or not self._region:
            raise STTUnavailable("AZURE_SPEECH_KEY and AZURE_SPEECH_REGION are required")

    def transcribe(self, pcm16: bytes) -> STTResult:
        config = speechsdk.SpeechConfig(subscription=self._key, region=self._region)
        config.speech_recognition_language = SPEECH_LANGUAGE
        config.request_word_level_timestamps()

        # PushAudioInputStream takes raw frames, so the format is declared here and
        # the turn travels as PCM16 with no WAV header.
        stream = speechsdk.audio.PushAudioInputStream(
            speechsdk.audio.AudioStreamFormat(samples_per_second=16000, bits_per_sample=16, channels=1)
        )
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=config,
            audio_config=speechsdk.audio.AudioConfig(stream=stream),
        )
        stream.write(pcm16)
        stream.close()

        result = recognizer.recognize_once_async().get()
        if result.reason != speechsdk.ResultReason.RecognizedSpeech:
            details = result.cancellation_details
            raise STTUnavailable(f"azure recognition failed: {result.reason} {details.error_details}")

        payload = json.loads(result.properties[speechsdk.PropertyId.SpeechServiceResponse_JsonResult])
        return STTResult(
            text=str(payload.get("DisplayText") or result.text or ""),
            language=LANGUAGE,
            words=words_from_json(payload),
        )
