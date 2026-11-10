from pathlib import Path

import numpy as np
import onnxruntime as ort

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 512
CHUNK_BYTES = CHUNK_SAMPLES * 2
MODEL_PATH = Path(__file__).parent / "models" / "silero_vad.onnx"


def decode_pcm16(data: bytes) -> np.ndarray:
    """PCM16 little endian to float32 in [-1, 1]."""
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


class SileroVAD:
    """Silero VAD v5: one speech probability per 512-sample 16 kHz chunk."""

    def __init__(self, model_path: Path = MODEL_PATH) -> None:
        self._session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._sr = np.array(SAMPLE_RATE, dtype=np.int64)

    def probability(self, chunk: bytes) -> float:
        samples = decode_pcm16(chunk)
        if samples.shape[0] != CHUNK_SAMPLES:
            raise ValueError(f"expected {CHUNK_SAMPLES} samples, got {samples.shape[0]}")
        # The recurrent state is the whole model memory: it must be carried across chunks.
        output, self._state = self._session.run(
            None,
            {"input": samples.reshape(1, CHUNK_SAMPLES), "state": self._state, "sr": self._sr},
        )
        return float(output.reshape(-1)[0])
