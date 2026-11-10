import wave
from pathlib import Path

from sales_trainer.voice.vad import CHUNK_SAMPLES, SileroVAD, decode_pcm16

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "hola-marta-16k.wav"
CHUNK_BYTES = CHUNK_SAMPLES * 2


def read_fixture() -> bytes:
    with wave.open(str(FIXTURE), "rb") as wav:
        assert wav.getframerate() == 16000
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        return wav.readframes(wav.getnframes())


def test_decode_pcm16_maps_int16_to_unit_range() -> None:
    samples = decode_pcm16(b"\x00\x80\xff\x7f\x00\x00")
    assert samples[0] == -1.0
    assert abs(samples[1] - 0.99997) < 1e-4
    assert samples[2] == 0.0


def test_digital_silence_scores_below_the_threshold() -> None:
    vad = SileroVAD()
    scores = [vad.probability(b"\x00\x00" * CHUNK_SAMPLES) for _ in range(15)]
    assert max(scores) < 0.5


def test_speech_scores_above_the_threshold_on_the_fixture() -> None:
    audio = read_fixture()
    step = CHUNK_BYTES
    chunks = [audio[offset : offset + step] for offset in range(0, len(audio) - step + 1, step)]
    assert len(chunks) > 50

    silence = b"\x00\x00" * CHUNK_SAMPLES
    prefix = [silence] * 15
    suffix = [silence] * 20

    vad = SileroVAD()
    scores = [vad.probability(chunk) for chunk in prefix + chunks + suffix]

    speech_scores = scores[15 : 15 + len(chunks)]
    assert max(speech_scores) > 0.5
    assert max(scores[:15]) < 0.5
    assert max(scores[-10:]) < 0.5
