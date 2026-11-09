import os
from typing import Any

import azure.cognitiveservices.speech as speechsdk

from sales_trainer.voice.tts.base import TTSResult, TTSUnavailable, VisemeEvent
from sales_trainer.voice.visemes import azure_to_viseme, smooth

DEFAULT_VOICE = "es-ES-ElviraNeural"
TICKS_PER_MS = 10_000


class AzureTTSProvider:
    def __init__(
        self,
        key: str | None = None,
        region: str | None = None,
        voice: str | None = None,
    ) -> None:
        self._key = key or os.environ.get("AZURE_SPEECH_KEY", "")
        self._region = region or os.environ.get("AZURE_SPEECH_REGION", "")
        self._voice = voice or os.environ.get("AZURE_SPEECH_VOICE", DEFAULT_VOICE)
        if not self._key or not self._region:
            raise TTSUnavailable("AZURE_SPEECH_KEY and AZURE_SPEECH_REGION are required")

    def _events_from(self, args: Any) -> VisemeEvent:
        return VisemeEvent(
            t_ms=int(args.audio_offset / TICKS_PER_MS),
            viseme=azure_to_viseme(args.viseme_id),
            weight=1.0,
        )

    def synthesize(self, text: str, voice: str | None = None) -> TTSResult:
        config = speechsdk.SpeechConfig(subscription=self._key, region=self._region)
        config.speech_synthesis_voice_name = voice or self._voice
        config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm
        )
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=config, audio_config=None)

        events: list[VisemeEvent] = []
        synthesizer.viseme_received.connect(lambda args: events.append(self._events_from(args)))

        result = synthesizer.speak_text_async(text).get()
        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            details = result.cancellation_details
            raise TTSUnavailable(f"azure synthesis failed: {details.reason} {details.error_details}")

        return TTSResult(audio=bytes(result.audio_data), visemes=smooth(events))
