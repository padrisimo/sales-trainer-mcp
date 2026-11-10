from sales_trainer.voice.stt.base import STTResult, Word

BYTES_PER_MS = 32  # 16 kHz mono PCM16
TEXT = "Hola, soy Marta. ¿En qué puedo ayudarte?"
CONFIDENCES = [0.98, 0.95, 0.97, 0.93, 0.96, 0.94, 0.92]


class MockSTTProvider:
    """Deterministic double: fixed words spread over the turn it was given."""

    def transcribe(self, pcm16: bytes) -> STTResult:
        tokens = TEXT.split()
        step = (len(pcm16) // BYTES_PER_MS) // len(tokens)
        words = [
            Word(word=token, start_ms=index * step, end_ms=(index + 1) * step, probability=CONFIDENCES[index])
            for index, token in enumerate(tokens)
        ]
        return STTResult(text=TEXT, language="es", words=words)
