# Phase 3: Microphone, VAD and STT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-subagent-driven-development (recommended) or superpowers-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user speak into the microphone in `/debug/stt`; the server cuts real turns with Silero VAD, transcribes each finished turn with word timings and probabilities (faster-whisper by default, Azure or mock by configuration), and shows the result without ever writing audio to disk.

**Architecture:** The browser opens `getUserMedia`, an `AudioWorklet` frames the stream into 512-sample / 32 ms PCM16 chunks at 16 kHz and `mic.js` sends them as binary over `/ws/stt` (Origin + session token validated against `web/sessions.py`). The server runs a vendored Silero VAD v5 ONNX model through `onnxruntime`, feeds the probability into the pure `TurnDetector` state machine, and only when a turn closes does it call the configured `STTProvider` in a worker thread, store the turn in memory and emit `transcript`.

**Tech Stack:** Python 3.12 (`.venv`), FastAPI 0.162 + Starlette WebSockets, pydantic v2, `onnxruntime`, `numpy`, `faster-whisper` 1.2.1 (`ctranslate2`, int8, no torch), `azure-cognitiveservices-speech` 1.53 (already installed), Silero VAD v5 ONNX (2.2 MB, MIT, vendored), pytest + Playwright, Node for the pure-JS checks.

**Repository:** `/Users/adrian/Documents/Projects/sales-trainer-mcp`, branch `main`. Starting point: **30 green tests**, `uv run ruff check .` clean, Python 3.12.15 in `.venv` (the system `python3` is 3.9, always use `uv run`), macOS arm64. `src/sales_trainer/web/app.py` has `_page(relative, session)`, `/debug/visemes` and `/debug/tts`; `web/routes/tts.py` is the only existing router; `mcp_server.start()` mints a `uuid4` token and stores it nowhere.

**Verified facts (do not re-derive):**

- `silero-vad` (PyPI) hard-requires `torch>=1.12` → discarded. The v5 ONNX model works standalone under `onnxruntime`: inputs `input[1,512] float32`, `state[2,1,128] float32`, `sr` scalar `int64`; outputs `output[1,1]`, `stateN[2,1,128]`; 0.09 ms per 32 ms chunk on this machine.
- The 2 327 524-byte model sits at `silero_vad/data/silero_vad.onnx` inside the `silero-vad==5.1.2` wheel; it can be extracted with `curl` + `unzip -p`, no torch and no install. Wheel URL and SHA-256 are in Task 2.
- `faster-whisper` 1.2.1 depends on `ctranslate2>=4`, `huggingface-hub`, `tokenizers`, `onnxruntime<2`, `av`, `tqdm` — **no torch**. `WhisperModel(size, device="cpu", compute_type="int8")`; `transcribe(audio, language="es", word_timestamps=True, vad_filter=False)` returns `(segments, info)` where `segments` is a generator and each segment has `.text` and `.words` of `.word` (str), `.start`, `.end` (seconds), `.probability` (0-1).
- Azure SDK 1.53.0: `SpeechConfig.request_word_level_timestamps()` exists; `speech_recognition_language` is settable; `SpeechRecognizer.recognize_once_async()` exists; `audio.PushAudioInputStream(stream_format)` with `audio.AudioStreamFormat(samples_per_second=16000, bits_per_sample=16, channels=1)`; `PropertyId.SpeechServiceResponse_JsonResult`; `ResultReason.RecognizedSpeech` / `.NoMatch` / `.Canceled` (American spelling). Word `Offset`/`Duration` are in ticks → divide by 10 000 for ms.
- The repo `.env` has a working `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION`. It is used **only** to generate the committed fixture; the suite never reads it.
- Starlette 1.10 `TestClient.websocket_connect(url, headers={...})` accepts a custom `Origin`, and a handler that calls `accept()`, `send_json(...)` and `close(code=1008)` lets the client read the error frame before `WebSocketDisconnect` (probed in this session).
- `ruff` has **no** configuration file in this repo (default rules E4/E7/E9/F), but every code block below is also clean under `BLE001` (never `except Exception`), `PLW1510` (`subprocess.run` needs `check=`), `FURB167` (`re.DOTALL`, not `re.S`), `I001` and `E501` (120 columns), so the plan survives a future `[tool.ruff]`.

**Design deviations from the spec, decided here (both are recorded in Task 20):**

1. Azure receives **raw PCM16** through `PushAudioInputStream` with an explicit `AudioStreamFormat(16000, 16, 1)`, not a WAV: `PushAudioInputStream` pushes sample frames, so a 44-byte RIFF header would be transcribed as a click. Same audio, correct API, still zero disk writes.
2. The 250 ms minimum applies to **speech** inside the turn, not to the turn duration. A turn can only close after 700 ms of silence, so a duration-based minimum is unreachable (every turn would be ≥ 732 ms) and would never filter a blip.

---

## Task 1: Add the STT dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [x] **Step 1: Add the three dependencies**

Run:

```bash
uv add faster-whisper onnxruntime numpy
```

Expected: exit code 0; `uv` prints `Resolved N packages` and `Installed N packages`, and `pyproject.toml` gains three `>=` entries under `dependencies`.

- [x] **Step 2: Verify the versions and that torch stayed out**

Run:

```bash
uv run python -c "
import faster_whisper, numpy, onnxruntime
print('faster-whisper', faster_whisper.__version__)
print('numpy', numpy.__version__)
print('onnxruntime', onnxruntime.__version__)
"
uv pip list | grep -iE '^(torch|silero-vad)' || echo "no torch, no silero-vad"
```

Expected: exit code 0; `faster-whisper 1.2.1`, `numpy 2.x.y`, `onnxruntime 1.x.y`, then `no torch, no silero-vad`.

- [x] **Step 3: Confirm the existing suite still passes**

Run: `uv run pytest -q`

Expected: exit code 0; `30 passed`.

- [x] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add faster-whisper, onnxruntime and numpy"
```

---

## Task 2: Vendor the Silero VAD v5 ONNX model

**Files:**
- Create: `src/sales_trainer/voice/models/silero_vad.onnx`
- Modify: `src/sales_trainer/web/static/LICENSES.md`

- [x] **Step 1: Create the directory and extract the model from the wheel**

Run:

```bash
mkdir -p src/sales_trainer/voice/models
curl -sL -o /tmp/silero_vad-5.1.2.whl \
  https://files.pythonhosted.org/packages/98/f7/5ae11d13fbb733cd3bfd7ff1c3a3902e6f55437df4b72307c1f168146268/silero_vad-5.1.2-py3-none-any.whl
unzip -p /tmp/silero_vad-5.1.2.whl silero_vad/data/silero_vad.onnx > src/sales_trainer/voice/models/silero_vad.onnx
ls -l src/sales_trainer/voice/models/silero_vad.onnx
shasum -a 256 src/sales_trainer/voice/models/silero_vad.onnx
```

Expected: `2327524` bytes and SHA-256 `2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f`.

- [x] **Step 2: Verify the graph signature with the real runtime**

Run:

```bash
uv run python -c "
import onnxruntime as ort
session = ort.InferenceSession('src/sales_trainer/voice/models/silero_vad.onnx', providers=['CPUExecutionProvider'])
print([(i.name, i.shape, i.type) for i in session.get_inputs()])
print([(o.name, o.shape) for o in session.get_outputs()])
"
```

Expected: exit code 0; the inputs are `input` `[1, 512]` `tensor(float)`, `state` `[2, 1, 128]` `tensor(float)` and `sr` with an empty shape `tensor(int64)`; the outputs are `output` `[1, 1]` and `stateN` `[2, 1, 128]` (ONNX prints the scalar shape as `[]`).

- [x] **Step 3: Document the license**

Append to `src/sales_trainer/web/static/LICENSES.md`:

```markdown
## Silero VAD v5 (ONNX)

- Origen: `silero_vad/data/silero_vad.onnx` del wheel PyPI `silero-vad==5.1.2` (proyecto `snakers4/silero-vad`).
- Licencia: MIT (incluida en el wheel como `silero_vad-5.1.2.dist-info/licenses/LICENSE`).
- No se sirve al navegador: lo carga `sales_trainer.voice.vad` desde `src/sales_trainer/voice/models/silero_vad.onnx`.
- Reason for versioning it: the `silero-vad` package would pull `torch` (~2.5 GB) for a 2.2 MB model; `onnxruntime` is already installed by `faster-whisper`.
```

- [x] **Step 4: Commit**

```bash
git add src/sales_trainer/voice/models/silero_vad.onnx src/sales_trainer/web/static/LICENSES.md
git commit -m "feat: vendor silero vad v5 onnx model"
```

---

## Task 3: Generate and commit the 16 kHz Spanish fixture

**Files:**
- Create: `tests/fixtures/hola-marta-16k.wav`

- [x] **Step 1: Synthesize it once with Azure, padded so a turn can close**

The fixture is padded with 500 ms of digital silence in front and 1 s at the end, so the VAD test has clean edges and the fake microphone always produces a closeable turn. This command is a one-off; nothing is added to the repo.

Run:

```bash
set -a && source .env && set +a
uv run python -c "
import wave
from pathlib import Path
import azure.cognitiveservices.speech as speechsdk

path = Path('tests/fixtures/hola-marta-16k.wav')
path.parent.mkdir(parents=True, exist_ok=True)
config = speechsdk.SpeechConfig(
    subscription=__import__('os').environ['AZURE_SPEECH_KEY'],
    region=__import__('os').environ['AZURE_SPEECH_REGION'],
)
config.speech_synthesis_voice_name = 'es-ES-ElviraNeural'
config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm)
result = speechsdk.SpeechSynthesizer(speech_config=config, audio_config=None).speak_text_async(
    'Hola, soy Marta. ¿En qué puedo ayudarte?'
).get()
path.write_bytes(result.audio_data)
with wave.open(str(path), 'rb') as wav:
    params = wav.getparams()
    frames = wav.readframes(wav.getnframes())
with wave.open(str(path), 'wb') as wav:
    wav.setparams(params)
    wav.writeframes(b'\x00\x00' * 8000 + frames + b'\x00\x00' * 16000)
print('wrote', path, path.stat().st_size)
"
```

Expected: exit code 0; `wrote tests/fixtures/hola-marta-16k.wav <size>` with a size between 90 000 and 250 000 bytes.

- [x] **Step 2: Verify the format a reader depends on**

Run:

```bash
uv run python -c "
import wave
with wave.open('tests/fixtures/hola-marta-16k.wav', 'rb') as wav:
    print(wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes())
    print(round(wav.getnframes() / wav.getframerate(), 2), 'seconds')
"
```

Expected: `16000 1 2 <frames>` and a duration between 2.5 and 6.0 seconds.

- [x] **Step 3: Commit**

```bash
git add tests/fixtures/hola-marta-16k.wav
git commit -m "test: add 16 khz spanish speech fixture"
```

---

## Task 4: `SileroVAD` — real ONNX probabilities over the fixture

**Files:**
- Create: `src/sales_trainer/voice/vad.py`
- Test: `tests/unit/test_vad.py`

- [x] **Step 1: Write the failing test**

`tests/unit/test_vad.py`:

```python
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
```

- [x] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_vad.py -v`

Expected: FAIL — exit code 1, `ModuleNotFoundError: No module named 'sales_trainer.voice.vad'`.

- [x] **Step 3: Create `src/sales_trainer/voice/vad.py`**

```python
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
```

- [x] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_vad.py -v`

Expected: exit code 0; `3 passed`.

- [x] **Step 5: Lint**

Run: `uv run ruff check src/sales_trainer/voice/vad.py tests/unit/test_vad.py`

Expected: exit code 0; `All checks passed!`.

- [x] **Step 6: Commit**

```bash
git add src/sales_trainer/voice/vad.py tests/unit/test_vad.py
git commit -m "feat: add silero vad over onnxruntime"
```

---

## Task 5: `TurnDetector`, `Turn` and `TurnStore`

**Files:**
- Create: `src/sales_trainer/voice/stt/__init__.py`
- Create: `src/sales_trainer/voice/stt/base.py`
- Create: `src/sales_trainer/voice/turns.py`
- Test: `tests/unit/test_turns.py`

- [x] **Step 1: Write the failing test**

`tests/unit/test_turns.py`:

```python
from sales_trainer.voice.turns import Turn, TurnDetector, TurnStore

CHUNK = b"\x00\x00" * 512


def start(detector: TurnDetector) -> None:
    detector.push(CHUNK, 0.9)
    assert detector.push(CHUNK, 0.9).started is True


def test_a_single_high_chunk_does_not_start_a_turn() -> None:
    detector = TurnDetector()
    assert detector.push(CHUNK, 0.9).started is False
    assert detector.active is False


def test_two_consecutive_high_chunks_start_a_turn() -> None:
    detector = TurnDetector()
    start(detector)
    assert detector.active is True


def test_a_low_chunk_resets_the_start_counter() -> None:
    detector = TurnDetector()
    detector.push(CHUNK, 0.9)
    detector.push(CHUNK, 0.1)
    assert detector.push(CHUNK, 0.9).started is False
    assert detector.push(CHUNK, 0.9).started is True


def test_700_ms_of_silence_closes_the_turn() -> None:
    detector = TurnDetector()
    start(detector)
    for _ in range(21):
        assert detector.push(CHUNK, 0.1).ended is None
    update = detector.push(CHUNK, 0.1)
    assert update.ended is not None
    assert update.ended.audio_ms == 24 * 32
    assert detector.active is False


def test_a_blip_shorter_than_250_ms_of_speech_is_discarded() -> None:
    detector = TurnDetector()
    start(detector)
    update = detector.push(CHUNK, 0.1)
    for _ in range(21):
        update = detector.push(CHUNK, 0.1)
    assert update.ended is not None
    assert update.discarded is True


def test_the_turn_force_closes_at_30_seconds() -> None:
    detector = TurnDetector()
    start(detector)
    update = detector.push(CHUNK, 0.9)
    for _ in range(935):
        update = detector.push(CHUNK, 0.9)
    assert update.ended is not None
    assert update.ended.audio_ms >= 30_000


def test_the_turn_keeps_every_chunk() -> None:
    detector = TurnDetector()
    start(detector)
    update = detector.push(CHUNK, 0.1)
    for _ in range(21):
        update = detector.push(CHUNK, 0.1)
    assert update.ended is not None
    assert len(update.ended.audio) == 24 * len(CHUNK)


def test_store_returns_a_copy_and_keeps_order() -> None:
    store = TurnStore()
    store.add("s", Turn(audio=b"", audio_ms=320, text="uno", language="es"))
    store.add("s", Turn(audio=b"", audio_ms=640, text="dos", language="es"))
    turns = store.list("s")
    assert [turn.text for turn in turns] == ["uno", "dos"]
    turns.clear()
    assert len(store.list("s")) == 2
```

- [x] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_turns.py -v`

Expected: FAIL — exit code 1, `ModuleNotFoundError: No module named 'sales_trainer.voice.turns'`.

- [x] **Step 3: Create the STT package with its base models**

`src/sales_trainer/voice/stt/__init__.py` (Task 9 turns it into the factory):

```python
"""Speech to text providers: faster-whisper (default), azure and mock."""
```

`src/sales_trainer/voice/stt/base.py`:

```python
from typing import Protocol

from pydantic import BaseModel, Field


class Word(BaseModel):
    word: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    probability: float = Field(ge=0.0, le=1.0)


class STTResult(BaseModel):
    text: str
    language: str = "es"
    words: list[Word] = Field(default_factory=list)


class STTUnavailable(RuntimeError):
    """Raised when the configured provider cannot transcribe."""


class STTProvider(Protocol):
    def transcribe(self, pcm16: bytes) -> STTResult: ...
```

- [x] **Step 4: Create `src/sales_trainer/voice/turns.py`**

```python
from dataclasses import dataclass, field

from sales_trainer.voice.stt.base import Word

CHUNK_MS = 32  # 512 samples at 16 kHz: the window Silero VAD expects.
SILENCE_MS = 700
MIN_SPEECH_MS = 250
MAX_TURN_MS = 30_000
START_CHUNKS = 2
THRESHOLD = 0.5


@dataclass
class Turn:
    audio: bytes
    audio_ms: int
    text: str = ""
    language: str = ""
    words: list[Word] = field(default_factory=list)


@dataclass
class TurnUpdate:
    started: bool = False
    ended: Turn | None = None
    discarded: bool = False


class TurnDetector:
    """Pure state machine: onset, end of turn, noise rejection. No audio analysis."""

    def __init__(
        self,
        silence_ms: int = SILENCE_MS,
        min_speech_ms: int = MIN_SPEECH_MS,
        max_turn_ms: int = MAX_TURN_MS,
    ) -> None:
        self._silence_ms = silence_ms
        self._min_speech_ms = min_speech_ms
        self._max_turn_ms = max_turn_ms
        self._chunks: list[bytes] = []
        self._speech_chunks = 0
        self._speech_run = 0
        self._silence_run = 0
        self.active = False

    def push(self, chunk: bytes, probability: float) -> TurnUpdate:
        speech = probability > THRESHOLD
        if not self.active:
            if not speech:
                self._chunks.clear()
                self._speech_chunks = 0
                self._speech_run = 0
                return TurnUpdate()
            self._chunks.append(chunk)
            self._speech_chunks += 1
            self._speech_run += 1
            if self._speech_run < START_CHUNKS:
                return TurnUpdate()
            self.active = True
            return TurnUpdate(started=True)

        self._chunks.append(chunk)
        if speech:
            self._speech_chunks += 1
            self._silence_run = 0
        else:
            self._silence_run += CHUNK_MS
        if self._silence_run >= self._silence_ms or len(self._chunks) * CHUNK_MS >= self._max_turn_ms:
            return self._close()
        return TurnUpdate()

    def _close(self) -> TurnUpdate:
        turn = Turn(audio=b"".join(self._chunks), audio_ms=len(self._chunks) * CHUNK_MS)
        # A turn can only close after the silence window, so the minimum must count
        # speech, not duration, or it would never reject anything.
        discarded = self._speech_chunks * CHUNK_MS < self._min_speech_ms
        self._chunks = []
        self._speech_chunks = 0
        self._speech_run = 0
        self._silence_run = 0
        self.active = False
        return TurnUpdate(ended=turn, discarded=discarded)


class TurnStore:
    """In-memory turns per session. Phase 3 has no database and Phase 4 will need them."""

    def __init__(self) -> None:
        self._turns: dict[str, list[Turn]] = {}

    def add(self, session: str, turn: Turn) -> None:
        self._turns.setdefault(session, []).append(turn)

    def list(self, session: str) -> list[Turn]:
        return list(self._turns.get(session, []))


_STORE = TurnStore()


def get_turn_store() -> TurnStore:
    return _STORE
```

- [x] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_turns.py -v`

Expected: exit code 0; `8 passed`.

- [x] **Step 6: Commit**

```bash
git add src/sales_trainer/voice/stt src/sales_trainer/voice/turns.py tests/unit/test_turns.py
git commit -m "feat: add pure turn detector and in-memory turn store"
```

---

## Task 6: Mock STT provider

**Files:**
- Create: `src/sales_trainer/voice/stt/mock.py`
- Test: `tests/unit/test_stt_mock.py`

- [x] **Step 1: Write the failing test**

`tests/unit/test_stt_mock.py`:

```python
from sales_trainer.voice.stt.mock import CONFIDENCES, TEXT, MockSTTProvider

BYTES_PER_MS = 32


def test_mock_returns_text_language_and_words() -> None:
    result = MockSTTProvider().transcribe(b"\x00\x00" * (BYTES_PER_MS * 1600))
    assert result.text == TEXT
    assert result.language == "es"
    assert len(result.words) == len(TEXT.split())
    first = result.words[0]
    assert set(first.model_dump()) == {"word", "start_ms", "end_ms", "probability"}


def test_mock_timings_are_ordered_and_inside_the_turn() -> None:
    audio_ms = 1600
    result = MockSTTProvider().transcribe(b"\x00\x00" * (BYTES_PER_MS * audio_ms))
    starts = [word.start_ms for word in result.words]
    assert starts == sorted(starts)
    assert all(0 <= word.start_ms <= word.end_ms <= audio_ms for word in result.words)


def test_mock_probabilities_are_bounded_and_fixed() -> None:
    result = MockSTTProvider().transcribe(b"\x00\x00" * (BYTES_PER_MS * 1600))
    assert [word.probability for word in result.words] == CONFIDENCES
    assert all(0.0 <= value <= 1.0 for value in CONFIDENCES)
```

- [x] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_stt_mock.py -v`

Expected: FAIL — exit code 1, `ModuleNotFoundError: No module named 'sales_trainer.voice.stt.mock'`.

- [x] **Step 3: Create `src/sales_trainer/voice/stt/mock.py`**

```python
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
```

- [x] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_stt_mock.py -v`

Expected: exit code 0; `3 passed`.

- [x] **Step 5: Commit**

```bash
git add src/sales_trainer/voice/stt/mock.py tests/unit/test_stt_mock.py
git commit -m "feat: add mock stt provider"
```

---

## Task 7: faster-whisper provider

**Files:**
- Create: `src/sales_trainer/voice/stt/whisper.py`
- Test: `tests/unit/test_stt_providers.py`

- [x] **Step 1: Write the failing tests**

`tests/unit/test_stt_providers.py`:

```python
from types import SimpleNamespace

import pytest

from sales_trainer.voice.stt.base import STTUnavailable
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
```

- [x] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_stt_providers.py -v`

Expected: FAIL — exit code 1, `ModuleNotFoundError: No module named 'sales_trainer.voice.stt.whisper'`.

- [x] **Step 3: Create `src/sales_trainer/voice/stt/whisper.py`**

```python
import os
from typing import Any

from sales_trainer.voice.stt.base import STTResult, STTUnavailable, Word
from sales_trainer.voice.vad import decode_pcm16

DEFAULT_MODEL = "small"
LANGUAGE = "es"


def word_from_segment(word: Any) -> Word:
    """faster-whisper words carry seconds and a probability in [0, 1]."""
    start_ms = int(round(float(word.start) * 1000))
    return Word(
        word=str(word.word).strip(),
        start_ms=start_ms,
        end_ms=max(start_ms, int(round(float(word.end) * 1000))),
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
```

- [x] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_stt_providers.py -v`

Expected: exit code 0; `3 passed`.

- [x] **Step 5: Commit**

```bash
git add src/sales_trainer/voice/stt/whisper.py tests/unit/test_stt_providers.py
git commit -m "feat: add faster-whisper stt provider"
```

---

## Task 8: Azure STT provider

**Files:**
- Create: `src/sales_trainer/voice/stt/azure.py`
- Test: `tests/unit/test_stt_providers.py`

- [x] **Step 1: Add the imports and the failing tests**

In `tests/unit/test_stt_providers.py`, replace the import block with:

```python
from types import SimpleNamespace

import pytest

from sales_trainer.voice.stt.azure import AzureSTTProvider, words_from_json
from sales_trainer.voice.stt.base import STTUnavailable
from sales_trainer.voice.stt.whisper import WhisperSTTProvider, word_from_segment
```

Then append these tests to the end of the file:

```python
def test_azure_requires_credentials() -> None:
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
```

- [x] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_stt_providers.py -v`

Expected: FAIL — exit code 1, `ModuleNotFoundError: No module named 'sales_trainer.voice.stt.azure'`.

- [x] **Step 3: Create `src/sales_trainer/voice/stt/azure.py`**

```python
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
```

- [x] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_stt_providers.py -v`

Expected: exit code 0; `6 passed`.

- [x] **Step 5: Commit**

```bash
git add src/sales_trainer/voice/stt/azure.py tests/unit/test_stt_providers.py
git commit -m "feat: add azure stt provider with word level timestamps"
```

---

## Task 9: Provider factory

**Files:**
- Modify: `src/sales_trainer/voice/stt/__init__.py`
- Test: `tests/unit/test_stt_providers.py`

- [x] **Step 1: Add the imports and the failing tests**

In `tests/unit/test_stt_providers.py`, replace the import block with:

```python
from types import SimpleNamespace

import pytest

from sales_trainer.voice.stt import get_stt_provider, provider_name
from sales_trainer.voice.stt.azure import AzureSTTProvider, words_from_json
from sales_trainer.voice.stt.base import STTUnavailable
from sales_trainer.voice.stt.mock import MockSTTProvider
from sales_trainer.voice.stt.whisper import WhisperSTTProvider, word_from_segment
```

Then append these tests to the end of the file:

```python
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
```

- [x] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_stt_providers.py -v`

Expected: FAIL — exit code 1, `ImportError: cannot import name 'get_stt_provider'`.

- [x] **Step 3: Replace `src/sales_trainer/voice/stt/__init__.py`**

```python
"""Speech to text providers: faster-whisper (default), azure and mock."""

import os

from sales_trainer.voice.stt.base import STTProvider, STTResult, STTUnavailable, Word

__all__ = [
    "STTProvider",
    "STTResult",
    "STTUnavailable",
    "Word",
    "get_stt_provider",
    "provider_name",
]

DEFAULT_PROVIDER = "faster-whisper"


def provider_name() -> str:
    return os.environ.get("SALES_TRAINER_STT", DEFAULT_PROVIDER).strip().lower()


def get_stt_provider() -> STTProvider:
    name = provider_name()
    if name == "mock":
        from sales_trainer.voice.stt.mock import MockSTTProvider

        return MockSTTProvider()
    if name == "faster-whisper":
        from sales_trainer.voice.stt.whisper import WhisperSTTProvider

        return WhisperSTTProvider()
    if name == "azure":
        from sales_trainer.voice.stt.azure import AzureSTTProvider

        return AzureSTTProvider()
    raise STTUnavailable(f"unknown SALES_TRAINER_STT value: {name}")
```

- [x] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_stt_providers.py -v`

Expected: exit code 0; `10 passed`.

- [x] **Step 5: Verify the default path never imports Azure or whisper for the mock**

Run:

```bash
SALES_TRAINER_STT=mock uv run python -c "
import sys
from sales_trainer.voice.stt import get_stt_provider
print(type(get_stt_provider()).__name__)
print('whisper imported:', 'sales_trainer.voice.stt.whisper' in sys.modules)
print('azure imported:', 'sales_trainer.voice.stt.azure' in sys.modules)
"
```

Expected: `MockSTTProvider`, `whisper imported: False`, `azure imported: False`.

- [x] **Step 6: Commit**

```bash
git add src/sales_trainer/voice/stt/__init__.py tests/unit/test_stt_providers.py
git commit -m "feat: add stt provider factory"
```

---

## Task 10: Session token registry

**Files:**
- Create: `src/sales_trainer/web/sessions.py`
- Test: `tests/unit/test_sessions.py`

- [x] **Step 1: Write the failing test**

`tests/unit/test_sessions.py`:

```python
import uuid

from sales_trainer.web import sessions


def test_an_unknown_token_is_not_known() -> None:
    assert sessions.is_known(f"unknown-{uuid.uuid4()}") is False


def test_a_registered_token_is_known() -> None:
    token = f"known-{uuid.uuid4()}"
    sessions.register(token)
    assert sessions.is_known(token) is True


def test_an_empty_token_is_never_known() -> None:
    assert sessions.is_known("") is False
```

- [x] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_sessions.py -v`

Expected: FAIL — exit code 1, `ModuleNotFoundError: No module named 'sales_trainer.web.sessions'`.

- [x] **Step 3: Create `src/sales_trainer/web/sessions.py`**

```python
"""Session tokens this server has issued or served, for the WebSocket handshake."""

_TOKENS: set[str] = set()


def register(token: str) -> None:
    # shortcut: one process, one set, no lock; revisit when uvicorn runs several workers.
    if token:
        _TOKENS.add(token)


def is_known(token: str) -> bool:
    return bool(token) and token in _TOKENS
```

- [x] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_sessions.py -v`

Expected: exit code 0; `3 passed`.

- [x] **Step 5: Commit**

```bash
git add src/sales_trainer/web/sessions.py tests/unit/test_sessions.py
git commit -m "feat: add session token registry"
```

---

## Task 11: Register tokens from the MCP tool and from every page load

**Files:**
- Modify: `src/sales_trainer/web/app.py`
- Modify: `src/sales_trainer/mcp_server.py`
- Test: `tests/unit/test_sessions.py`
- Test: `tests/unit/test_mcp_server.py`

- [x] **Step 1: Write the failing tests**

In `tests/unit/test_sessions.py`, replace the import block with:

```python
import uuid

from fastapi.testclient import TestClient

from sales_trainer.web import sessions
from sales_trainer.web.app import app
```

Then append to the end of the file:

```python
client = TestClient(app)


def test_loading_a_page_registers_the_session_token() -> None:
    token = f"page-{uuid.uuid4()}"
    response = client.get(f"/debug/tts?session={token}")
    assert response.status_code == 200
    assert sessions.is_known(token) is True
```

In `tests/unit/test_mcp_server.py`, replace the import block with:

```python
import pytest

from sales_trainer import mcp_server
from sales_trainer.web import sessions
```

Then append to the end of the file:

```python
def test_start_registers_the_session_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "_ensure_server", lambda: None)
    monkeypatch.setattr(mcp_server.webbrowser, "open", lambda url: True)

    result = mcp_server.start(level=1, product_brief=None, language="es")

    assert sessions.is_known(result["session_id"]) is True
```

- [x] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/unit/test_sessions.py tests/unit/test_mcp_server.py -v`

Expected: FAIL — exit code 1; `test_loading_a_page_registers_the_session_token` fails with `assert False is True`, and `test_start_registers_the_session_token` fails the same way.

- [x] **Step 3: Register inside `_page` in `src/sales_trainer/web/app.py`**

Add the import after the existing `tts` router import:

```python
from sales_trainer.web.sessions import register
```

And change `_page` from:

```python
def _page(relative: str, session: str) -> HTMLResponse:
    html = (STATIC_DIR / relative).read_text(encoding="utf-8")
    return HTMLResponse(content=html.replace("__SESSION_TOKEN__", session), media_type="text/html")
```

to:

```python
def _page(relative: str, session: str) -> HTMLResponse:
    register(session)
    html = (STATIC_DIR / relative).read_text(encoding="utf-8")
    return HTMLResponse(content=html.replace("__SESSION_TOKEN__", session), media_type="text/html")
```

- [x] **Step 4: Register the token in `src/sales_trainer/mcp_server.py`**

Add the import next to `from sales_trainer.web.app import app`:

```python
from sales_trainer.web.sessions import register
```

And change `start` from:

```python
def start(level: int = 1, product_brief: str | None = None, language: str = "es") -> dict[str, str]:
    token = str(uuid.uuid4())
    url = build_url(port=PORT, token=token)
```

to:

```python
def start(level: int = 1, product_brief: str | None = None, language: str = "es") -> dict[str, str]:
    token = str(uuid.uuid4())
    register(token)
    url = build_url(port=PORT, token=token)
```

- [x] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_sessions.py tests/unit/test_mcp_server.py -v`

Expected: exit code 0; `4 passed` for `test_sessions.py` and `5 passed` for `test_mcp_server.py`.

- [x] **Step 6: Run the whole suite**

Run: `uv run pytest -q`

Expected: exit code 0; `59 passed` (30 at the start of the phase + 3 vad + 8 turns + 3 mock + 10 providers + 4 sessions + 1 new in `test_mcp_server.py`).

- [x] **Step 7: Commit**

```bash
git add src/sales_trainer/web/app.py src/sales_trainer/mcp_server.py tests/unit/test_sessions.py tests/unit/test_mcp_server.py
git commit -m "feat: register session tokens from mcp and page loads"
```

---

## Task 12: `GET /api/turns`

**Files:**
- Create: `src/sales_trainer/web/routes/stt.py`
- Modify: `src/sales_trainer/web/app.py`
- Test: `tests/unit/test_turns_route.py`

- [x] **Step 1: Write the failing test**

`tests/unit/test_turns_route.py`:

```python
import uuid

from fastapi.testclient import TestClient

from sales_trainer.voice.stt.base import Word
from sales_trainer.voice.turns import Turn, get_turn_store
from sales_trainer.web.app import app

client = TestClient(app)


def test_an_unknown_session_returns_no_turns() -> None:
    assert client.get("/api/turns?session=missing").json() == {"turns": []}


def test_turns_come_back_in_order_with_their_words() -> None:
    token = f"route-{uuid.uuid4()}"
    store = get_turn_store()
    store.add(
        token,
        Turn(
            audio=b"",
            audio_ms=320,
            text="Hola.",
            language="es",
            words=[Word(word="Hola", start_ms=0, end_ms=100, probability=0.9)],
        ),
    )
    store.add(token, Turn(audio=b"", audio_ms=640, text="Adiós.", language="es"))

    body = client.get(f"/api/turns?session={token}").json()

    assert [turn["text"] for turn in body["turns"]] == ["Hola.", "Adiós."]
    assert body["turns"][0]["audio_ms"] == 320
    assert body["turns"][0]["words"][0] == {"word": "Hola", "start_ms": 0, "end_ms": 100, "probability": 0.9}
    assert body["turns"][1]["words"] == []
```

- [x] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_turns_route.py -v`

Expected: FAIL — exit code 1; the first test fails with `assert 404 == 200`.

- [x] **Step 3: Create `src/sales_trainer/web/routes/stt.py`**

```python
from fastapi import APIRouter

from sales_trainer.voice.turns import get_turn_store

router = APIRouter(prefix="/api", tags=["stt"])


@router.get("/turns")
def list_turns(session: str = "") -> dict[str, list[dict[str, object]]]:
    return {
        "turns": [
            {
                "audio_ms": turn.audio_ms,
                "text": turn.text,
                "language": turn.language,
                "words": [word.model_dump() for word in turn.words],
            }
            for turn in get_turn_store().list(session)
        ]
    }
```

- [x] **Step 4: Mount the router in `src/sales_trainer/web/app.py`**

Change the import block from:

```python
from sales_trainer.web.routes import tts as tts_routes
from sales_trainer.web.sessions import register
```

to:

```python
from sales_trainer.web.routes import stt as stt_routes
from sales_trainer.web.routes import tts as tts_routes
from sales_trainer.web.sessions import register
```

And after `app.include_router(tts_routes.router)` add:

```python
app.include_router(stt_routes.router)
```

- [x] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_turns_route.py -v`

Expected: exit code 0; `2 passed`.

- [x] **Step 6: Commit**

```bash
git add src/sales_trainer/web/routes/stt.py src/sales_trainer/web/app.py tests/unit/test_turns_route.py
git commit -m "feat: add turns endpoint"
```

---

## Task 13: `/ws/stt` handshake — Origin and session token

**Files:**
- Create: `src/sales_trainer/web/routes/stt_ws.py`
- Modify: `src/sales_trainer/web/app.py`
- Test: `tests/unit/test_stt_ws.py`

- [x] **Step 1: Write the failing test**

`tests/unit/test_stt_ws.py`:

```python
import uuid

import pytest
from fastapi.testclient import TestClient

from sales_trainer.web import sessions
from sales_trainer.web.app import app

client = TestClient(app)
ORIGIN = "http://127.0.0.1:8765"


@pytest.fixture
def session_token() -> str:
    token = f"ws-{uuid.uuid4()}"
    sessions.register(token)
    return token


def test_a_foreign_origin_is_rejected() -> None:
    token = f"ws-{uuid.uuid4()}"
    sessions.register(token)
    url = f"/ws/stt?session={token}"
    with client.websocket_connect(url, headers={"origin": "http://evil.example"}) as socket:
        payload = socket.receive_json()
    assert payload["type"] == "error"
    assert payload["code"] == "origin"


def test_a_missing_origin_is_rejected(session_token: str) -> None:
    url = f"/ws/stt?session={session_token}"
    with client.websocket_connect(url, headers={}) as socket:
        payload = socket.receive_json()
    assert payload["code"] == "origin"


def test_an_unknown_token_is_rejected() -> None:
    url = f"/ws/stt?session=nope-{uuid.uuid4()}"
    with client.websocket_connect(url, headers={"origin": ORIGIN}) as socket:
        payload = socket.receive_json()
    assert payload["type"] == "error"
    assert payload["code"] == "session"
```

- [x] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_stt_ws.py -v`

Expected: FAIL — exit code 1; `websocket_connect` raises because `/ws/stt` does not exist (403 handshake).

- [x] **Step 3: Create `src/sales_trainer/web/routes/stt_ws.py`**

```python
import os

from fastapi import APIRouter, WebSocket

from sales_trainer.web.sessions import is_known

router = APIRouter()

POLICY_VIOLATION = 1008


def allowed_origins() -> set[str]:
    port = os.environ.get("SALES_TRAINER_PORT", "8765")
    return {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}


async def _reject(websocket: WebSocket, code: str, message: str) -> None:
    await websocket.send_json({"type": "error", "code": code, "message": message})
    await websocket.close(code=POLICY_VIOLATION)


@router.websocket("/ws/stt")
async def stt_socket(websocket: WebSocket, session: str = "") -> None:
    await websocket.accept()
    origin = websocket.headers.get("origin", "")
    if origin not in allowed_origins():
        await _reject(websocket, "origin", f"origin not allowed: {origin or '(missing)'}")
        return
    if not is_known(session):
        await _reject(websocket, "session", "unknown session token")
        return
    await websocket.send_json({"type": "ready"})
```

- [x] **Step 4: Mount the router in `src/sales_trainer/web/app.py`**

Add the import after the `stt` router import:

```python
from sales_trainer.web.routes import stt_ws as stt_ws_routes
```

And after `app.include_router(stt_routes.router)` add:

```python
app.include_router(stt_ws_routes.router)
```

- [x] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_stt_ws.py -v`

Expected: exit code 0; `3 passed`.

- [x] **Step 6: Commit**

```bash
git add src/sales_trainer/web/routes/stt_ws.py src/sales_trainer/web/app.py tests/unit/test_stt_ws.py
git commit -m "feat: add stt websocket with origin and token checks"
```

---

## Task 14: `/ws/stt` turn loop — VAD, turns, transcription, store

**Files:**
- Modify: `src/sales_trainer/web/routes/stt_ws.py`
- Test: `tests/unit/test_stt_ws.py`

- [x] **Step 1: Append the failing tests**

Append to `tests/unit/test_stt_ws.py`:

```python
from sales_trainer.web.routes import stt_ws

CHUNK = b"\x00\x00" * 512


class ScriptedVAD:
    def __init__(self, script: list[float]) -> None:
        self._script = list(script)

    def probability(self, chunk: bytes) -> float:
        return self._script.pop(0) if self._script else 0.0


def read_until(socket, kind: str) -> dict:
    while True:
        message = socket.receive_json()
        if message["type"] == kind:
            return message


def test_one_turn_produces_one_transcript_and_is_stored(monkeypatch: pytest.MonkeyPatch, session_token: str) -> None:
    monkeypatch.setenv("SALES_TRAINER_STT", "mock")
    monkeypatch.setattr(stt_ws, "_make_vad", lambda: ScriptedVAD([0.9] * 8 + [0.1] * 22))

    with client.websocket_connect(f"/ws/stt?session={session_token}", headers={"origin": ORIGIN}) as socket:
        assert socket.receive_json()["type"] == "ready"
        for _ in range(8):
            socket.send_bytes(CHUNK)
        started = read_until(socket, "turn_start")
        for _ in range(22):
            socket.send_bytes(CHUNK)
        ended = read_until(socket, "turn_end")
        transcript = read_until(socket, "transcript")

    assert started["t_ms"] == 64
    assert ended["audio_ms"] == 960
    assert transcript["text"]
    assert transcript["language"] == "es"
    words = transcript["words"]
    assert words
    assert [word["start_ms"] for word in words] == sorted(word["start_ms"] for word in words)
    assert all(0 <= word["start_ms"] <= word["end_ms"] <= 960 for word in words)
    assert all(0.0 <= word["probability"] <= 1.0 for word in words)

    stored = client.get(f"/api/turns?session={session_token}").json()["turns"]
    assert len(stored) == 1
    assert stored[0]["text"] == transcript["text"]


def test_a_blip_closes_without_a_transcript(monkeypatch: pytest.MonkeyPatch, session_token: str) -> None:
    monkeypatch.setenv("SALES_TRAINER_STT", "mock")
    monkeypatch.setattr(stt_ws, "_make_vad", lambda: ScriptedVAD([0.9] * 2 + [0.1] * 22))

    with client.websocket_connect(f"/ws/stt?session={session_token}", headers={"origin": ORIGIN}) as socket:
        assert socket.receive_json()["type"] == "ready"
        for _ in range(24):
            socket.send_bytes(CHUNK)
        ended = read_until(socket, "turn_end")

    assert ended["audio_ms"] == 768
    assert client.get(f"/api/turns?session={session_token}").json()["turns"] == []
```

- [x] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_stt_ws.py -v`

Expected: FAIL — exit code 1; `read_until` blocks on `turn_start` because the socket still only sends `ready` (the test times out / the websocket closes without the message).

- [x] **Step 3: Replace `src/sales_trainer/web/routes/stt_ws.py` with the complete file**

```python
import asyncio
import os
from dataclasses import replace

from fastapi import APIRouter, WebSocket

from sales_trainer.voice.stt import get_stt_provider
from sales_trainer.voice.stt.base import STTUnavailable
from sales_trainer.voice.turns import CHUNK_MS, SILENCE_MS, TurnDetector, get_turn_store
from sales_trainer.voice.vad import CHUNK_BYTES, SileroVAD
from sales_trainer.web.sessions import is_known

router = APIRouter()

POLICY_VIOLATION = 1008
LEVEL_EVERY_CHUNKS = 3


def allowed_origins() -> set[str]:
    port = os.environ.get("SALES_TRAINER_PORT", "8765")
    return {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}


def _make_vad() -> SileroVAD:
    return SileroVAD()


async def _reject(websocket: WebSocket, code: str, message: str) -> None:
    await websocket.send_json({"type": "error", "code": code, "message": message})
    await websocket.close(code=POLICY_VIOLATION)


@router.websocket("/ws/stt")
async def stt_socket(websocket: WebSocket, session: str = "") -> None:
    await websocket.accept()
    origin = websocket.headers.get("origin", "")
    if origin not in allowed_origins():
        await _reject(websocket, "origin", f"origin not allowed: {origin or '(missing)'}")
        return
    if not is_known(session):
        await _reject(websocket, "session", "unknown session token")
        return
    try:
        provider = get_stt_provider()
    except STTUnavailable as error:
        await _reject(websocket, "stt", str(error))
        return
    try:
        vad = _make_vad()
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        await _reject(websocket, "vad", str(error))
        return

    silence_ms = int(os.environ.get("SALES_TRAINER_SILENCE_MS", str(SILENCE_MS)))
    detector = TurnDetector(silence_ms=silence_ms)
    store = get_turn_store()
    await websocket.send_json({"type": "ready"})

    elapsed_ms = 0
    peak = 0.0
    chunks_since_level = 0
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        chunk = message.get("bytes")
        if chunk is None or len(chunk) != CHUNK_BYTES:
            continue

        elapsed_ms += CHUNK_MS
        probability = vad.probability(chunk)
        peak = max(peak, probability)
        chunks_since_level += 1
        if chunks_since_level >= LEVEL_EVERY_CHUNKS:
            await websocket.send_json({"type": "level", "probability": round(peak, 3)})
            peak = 0.0
            chunks_since_level = 0

        update = detector.push(chunk, probability)
        if update.started:
            await websocket.send_json({"type": "turn_start", "t_ms": elapsed_ms})
        if update.ended is None:
            continue

        turn = update.ended
        await websocket.send_json({"type": "turn_end", "t_ms": elapsed_ms, "audio_ms": turn.audio_ms})
        if update.discarded:
            continue

        try:
            # whisper blocks for seconds; a worker thread keeps the socket responsive.
            result = await asyncio.to_thread(provider.transcribe, turn.audio)
        except STTUnavailable as error:
            await websocket.send_json({"type": "error", "code": "stt", "message": str(error)})
            continue

        turn = replace(turn, text=result.text, language=result.language, words=result.words)
        store.add(session, turn)
        await websocket.send_json(
            {
                "type": "transcript",
                "text": turn.text,
                "language": turn.language,
                "words": [word.model_dump() for word in turn.words],
            }
        )
```

- [x] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_stt_ws.py -v`

Expected: exit code 0; `5 passed`.

- [x] **Step 5: Lint**

Run: `uv run ruff check .`

Expected: exit code 0; `All checks passed!`.

- [x] **Step 6: Commit**

```bash
git add src/sales_trainer/web/routes/stt_ws.py tests/unit/test_stt_ws.py
git commit -m "feat: transcribe finished turns over the stt socket"
```

---

## Task 15: PCM helpers in the browser — `pcm.js` and its node check

**Files:**
- Create: `src/sales_trainer/web/static/js/pcm.js`
- Create: `tests/js/pcm_downsample.mjs`
- Test: `tests/unit/test_pcm_downsample_js.py`

- [x] **Step 1: Write the failing node script and its pytest wrapper**

`tests/js/pcm_downsample.mjs`:

```javascript
import { PcmFramer, toPcm16 } from "../../src/sales_trainer/web/static/js/pcm.js";

function expect(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${expected}, got ${actual}`);
  }
}

// 16 kHz: one input sample per output sample.
const framer16 = new PcmFramer(1);
const frames16 = [];
for (let i = 0; i < 512; i += 1) {
  const frame = framer16.push(i / 512);
  if (frame) {
    frames16.push(frame);
  }
}
expect(frames16.length, 1, "one frame per 512 samples at 16 kHz");
expect(frames16[0].length, 512, "frame length");
expect(frames16[0][0], 0, "first sample");
expect(frames16[0][511], Math.round((511 / 512) * 32767), "last sample");

// 48 kHz: three input samples average into one output sample.
const framer48 = new PcmFramer(3);
let produced = 0;
for (let i = 0; i < 512 * 3 - 1; i += 1) {
  if (framer48.push(0.5)) {
    produced += 1;
  }
}
expect(produced, 0, "no frame before 1536 input samples");
const frame48 = framer48.push(0.5);
expect(frame48 === null ? 0 : frame48.length, 512, "frame after 1536 input samples");
expect(frame48[0], Math.round(0.5 * 32767), "averaged value");
expect(frame48[511], Math.round(0.5 * 32767), "averaged last value");

// Clipping keeps a loud sample inside the PCM16 range.
const clipped = toPcm16(new Float32Array([2, -2, 0]));
expect(clipped[0], 32767, "clip high");
expect(clipped[1], -32767, "clip low");
expect(clipped[2], 0, "silence");

console.log("pcm downsample ok");
```

`tests/unit/test_pcm_downsample_js.py`:

```python
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pcm_downsample_script_passes() -> None:
    result = subprocess.run(
        ["node", str(ROOT / "tests" / "js" / "pcm_downsample.mjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "pcm downsample ok" in result.stdout
```

- [x] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_pcm_downsample_js.py -v`

Expected: FAIL — exit code 1; node reports `Cannot find module .../pcm.js`.

- [x] **Step 3: Create `src/sales_trainer/web/static/js/pcm.js`**

```javascript
// Pure PCM helpers shared by the audio worklet and the node test.

export function toPcm16(samples) {
  const out = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    out[i] = Math.round(clamped * 32767);
  }
  return out;
}

// Box-filter downsampling plus framing: every `ratio` input samples become one
// 16 kHz sample, and every `frameSize` of those becomes one Int16 chunk.
export class PcmFramer {
  constructor(ratio, frameSize = 512) {
    this.ratio = ratio;
    this.frameSize = frameSize;
    this.frame = new Float32Array(frameSize);
    this.filled = 0;
    this.sum = 0;
    this.count = 0;
  }

  push(sample) {
    this.sum += sample;
    this.count += 1;
    if (this.count < this.ratio) {
      return null;
    }
    this.frame[this.filled] = this.sum / this.ratio;
    this.filled += 1;
    this.sum = 0;
    this.count = 0;
    if (this.filled < this.frameSize) {
      return null;
    }
    this.filled = 0;
    return toPcm16(this.frame);
  }
}
```

- [x] **Step 4: Run the test**

Run: `uv run pytest tests/unit/test_pcm_downsample_js.py -v`

Expected: exit code 0; `1 passed`.

- [x] **Step 5: Commit**

```bash
git add src/sales_trainer/web/static/js/pcm.js tests/js/pcm_downsample.mjs tests/unit/test_pcm_downsample_js.py
git commit -m "feat: add pcm16 framing and downsampling helpers"
```

---

## Task 16: AudioWorklet and microphone bridge

**Files:**
- Create: `src/sales_trainer/web/static/js/pcm-worklet.js`
- Create: `src/sales_trainer/web/static/js/mic.js`

- [x] **Step 1: Create `src/sales_trainer/web/static/js/pcm-worklet.js`**

```javascript
import { PcmFramer } from "./pcm.js";

class PcmWorklet extends AudioWorkletProcessor {
  constructor() {
    super();
    // The page asks for a 16 kHz context; if the browser ignores it, average down.
    this.framer = new PcmFramer(Math.max(1, Math.round(sampleRate / 16000)));
  }

  process(inputs) {
    const channel = inputs[0][0];
    if (channel) {
      for (let i = 0; i < channel.length; i += 1) {
        const frame = this.framer.push(channel[i]);
        if (frame) {
          this.port.postMessage(frame);
        }
      }
    }
    return true;
  }
}

registerProcessor("pcm-worklet", PcmWorklet);
```

- [x] **Step 2: Create `src/sales_trainer/web/static/js/mic.js`**

```javascript
// Microphone to websocket: PCM16 mono 16 kHz frames of 512 samples (32 ms).

export async function startListening({ session, onMessage, onError }) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
    },
  });

  const context = new AudioContext({ sampleRate: 16000 });
  await context.resume();
  await context.audioWorklet.addModule("/static/js/pcm-worklet.js");

  const source = context.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(context, "pcm-worklet");
  // A worklet with no path to the destination is not pulled by the graph.
  node.connect(context.destination);

  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${scheme}://${location.host}/ws/stt?session=${encodeURIComponent(session)}`);
  socket.binaryType = "arraybuffer";

  socket.addEventListener("message", (event) => onMessage(JSON.parse(event.data)));
  socket.addEventListener("error", () => onError(new Error("websocket error")));

  node.port.onmessage = (event) => {
    if (socket.readyState === WebSocket.OPEN) {
      socket.send(event.data.buffer);
    }
  };
  source.connect(node);

  return {
    stop() {
      node.port.onmessage = null;
      source.disconnect();
      node.disconnect();
      socket.close();
      void context.close();
      for (const track of stream.getTracks()) {
        track.stop();
      }
    },
  };
}
```

- [x] **Step 3: Verify both files are served**

Run:

```bash
uv run python -c "
from fastapi.testclient import TestClient
from sales_trainer.web.app import app
c = TestClient(app)
for path in ['/static/js/pcm.js', '/static/js/pcm-worklet.js', '/static/js/mic.js']:
    print(path, c.get(path).status_code)
"
```

Expected: exit code 0; `200` for each of the three paths.

- [x] **Step 4: Lint**

Run: `uv run ruff check .`

Expected: exit code 0; `All checks passed!`.

- [x] **Step 5: Commit**

```bash
git add src/sales_trainer/web/static/js/pcm-worklet.js src/sales_trainer/web/static/js/mic.js
git commit -m "feat: add microphone capture worklet and socket bridge"
```

---

## Task 17: `/debug/stt` page

**Files:**
- Create: `src/sales_trainer/web/static/debug/stt.html`
- Create: `src/sales_trainer/web/static/js/stt-debug.js`
- Modify: `src/sales_trainer/web/app.py`

- [x] **Step 1: Create `src/sales_trainer/web/static/debug/stt.html`**

```html
<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Sales Trainer — STT</title>
    <style>
      html,
      body {
        margin: 0;
        height: 100%;
        background: #101418;
        color: #e6edf3;
        font: 13px system-ui, sans-serif;
      }
      body {
        display: grid;
        grid-template-columns: 320px 1fr;
      }
      #controls {
        padding: 12px;
        background: #171d24;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      button {
        padding: 10px;
        border: 1px solid #2c3642;
        border-radius: 6px;
        background: #2a3542;
        color: inherit;
        cursor: pointer;
      }
      #level {
        width: 100%;
        height: 12px;
      }
      #turns {
        margin: 0;
        padding: 12px;
        overflow-y: auto;
      }
      #turns li {
        margin-bottom: 8px;
        line-height: 1.5;
      }
      .words {
        color: #8b98a5;
      }
    </style>
  </head>
  <body>
    <section id="controls">
      <button id="start" type="button">Escuchar</button>
      <button id="stop" type="button">Parar</button>
      <label for="level">Nivel (probabilidad del VAD)</label>
      <progress id="level" max="1" value="0"></progress>
      <p id="status">listo</p>
      <p>El navegador envía PCM16 mono a 16 kHz; el servidor corta los turnos con Silero VAD y transcribe solo el turno terminado.</p>
    </section>
    <ol id="turns"></ol>
    <script type="module" src="/static/js/stt-debug.js"></script>
  </body>
</html>
```

- [x] **Step 2: Create `src/sales_trainer/web/static/js/stt-debug.js`**

```javascript
import { startListening } from "./mic.js";

const status = document.getElementById("status");
const level = document.getElementById("level");
const turns = document.getElementById("turns");
const startButton = document.getElementById("start");
const stopButton = document.getElementById("stop");

const session = new URLSearchParams(window.location.search).get("session") ?? "";
const state = { ready: false, listening: false, turns: [], lastError: null };
window.sttDebug = state;

let connection = null;

function renderTurn(turn) {
  const item = document.createElement("li");
  const words = turn.words
    .map((word) => `${word.word} [${word.start_ms}-${word.end_ms} ms · ${word.probability.toFixed(2)}]`)
    .join(" ");
  item.textContent = turn.text;
  const detail = document.createElement("div");
  detail.className = "words";
  detail.textContent = words;
  item.append(detail);
  turns.prepend(item);
}

startButton.addEventListener("click", async () => {
  if (connection !== null) {
    return;
  }
  status.textContent = "conectando";
  try {
    connection = await startListening({
      session,
      onMessage: (message) => {
        if (message.type === "ready") {
          state.listening = true;
          status.textContent = "escuchando";
        } else if (message.type === "level") {
          level.value = message.probability;
        } else if (message.type === "turn_end") {
          level.value = 0;
          status.textContent = `turno de ${message.audio_ms} ms`;
        } else if (message.type === "transcript") {
          state.turns.push(message);
          renderTurn(message);
        } else if (message.type === "error") {
          state.lastError = message.message;
          status.textContent = `error: ${message.message}`;
        }
      },
      onError: (error) => {
        state.lastError = error.message;
        status.textContent = `error: ${error.message}`;
      },
    });
  } catch (error) {
    state.lastError = error.message;
    status.textContent = `error: ${error.message}`;
  }
});

stopButton.addEventListener("click", () => {
  if (connection !== null) {
    connection.stop();
    connection = null;
  }
  state.listening = false;
  level.value = 0;
  status.textContent = "parado";
});

requestAnimationFrame(() => {
  requestAnimationFrame(() => {
    state.ready = true;
  });
});
```

- [x] **Step 3: Add the route to `src/sales_trainer/web/app.py`**

Append after the `/debug/tts` handler:

```python
@app.get("/debug/stt")
async def debug_stt(session: str = "") -> HTMLResponse:
    return _page("debug/stt.html", session)
```

- [x] **Step 4: Verify the page and its scripts are served**

Run:

```bash
uv run python -c "
from fastapi.testclient import TestClient
from sales_trainer.web.app import app
from sales_trainer.web import sessions
c = TestClient(app)
print('/debug/stt', c.get('/debug/stt?session=manual').status_code)
print('stt-debug.js', c.get('/static/js/stt-debug.js').status_code)
print('session registered', sessions.is_known('manual'))
"
```

Expected: exit code 0; `/debug/stt 200`, `stt-debug.js 200`, `session registered True`.

- [x] **Step 5: Commit**

```bash
git add src/sales_trainer/web/static/debug/stt.html src/sales_trainer/web/static/js/stt-debug.js src/sales_trainer/web/app.py
git commit -m "feat: add stt debug page"
```

---

## Task 18: End-to-end with the fake microphone

**Files:**
- Create: `tests/e2e/test_stt_page.py`

- [x] **Step 1: Create the test**

```python
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

PORT = 8126
BASE_URL = f"http://127.0.0.1:{PORT}"
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "hola-marta-16k.wav"
TOKEN = "e2e-stt"


def _wait_for_server(timeout_seconds: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = urllib.request.urlopen(f"{BASE_URL}/debug/stt?session={TOKEN}", timeout=2)
            try:
                if response.status == 200:
                    return
            finally:
                response.close()
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    raise RuntimeError("web server did not become ready in time")


@pytest.mark.e2e
def test_debug_stt_page_transcribes_a_turn_from_the_fake_microphone() -> None:
    env = {**os.environ, "SALES_TRAINER_STT": "mock", "SALES_TRAINER_PORT": str(PORT)}
    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "sales_trainer.web.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    try:
        _wait_for_server()
        errors: list[str] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                args=[
                    "--use-angle=swiftshader",
                    "--enable-unsafe-swiftshader",
                    "--autoplay-policy=no-user-gesture-required",
                    "--use-fake-device-for-media-stream",
                    "--use-fake-ui-for-media-stream",
                    f"--use-file-for-fake-audio-capture={FIXTURE}",
                ]
            )
            page = browser.new_page()

            def on_console(message) -> None:
                if message.type == "error":
                    errors.append(message.text)

            page.on("console", on_console)
            page.on("pageerror", lambda error: errors.append(str(error)))

            page.goto(f"{BASE_URL}/debug/stt?session={TOKEN}")
            page.wait_for_function("window.sttDebug && window.sttDebug.ready === true")
            page.click("#start")
            page.wait_for_function("window.sttDebug.listening === true", timeout=15000)
            page.wait_for_function("window.sttDebug.turns.length > 0", timeout=30000)

            turns = page.evaluate("window.sttDebug.turns")
            assert turns[0]["text"]
            assert turns[0]["language"] == "es"
            assert turns[0]["words"]
            assert turns[0]["words"][0]["start_ms"] >= 0
            assert page.evaluate("window.sttDebug.lastError") is None
            assert errors == []
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
```

- [x] **Step 2: Run it**

Run: `uv run pytest -m e2e -v`

Expected: exit code 0; `4 passed` (three Phase 1-2 e2e tests plus this one).

If `window.sttDebug.turns.length > 0` times out, the fake microphone fed no speech: check that `tests/fixtures/hola-marta-16k.wav` is 16 kHz mono 16-bit (Task 3, Step 2) and that Chromium logs no `getUserMedia` error in `errors`.

- [x] **Step 3: Commit**

```bash
git add tests/e2e/test_stt_page.py
git commit -m "test: add e2e coverage for stt turn detection and transcript"
```

---

## Task 19: Full suite and linter

- [x] **Step 1: Run everything**

Run: `uv run pytest -q`

Expected: exit code 0; `67 passed`.

The count is: 30 pre-existing + 3 `test_vad.py` + 8 `test_turns.py` + 3 `test_stt_mock.py` + 10 `test_stt_providers.py` + 4 `test_sessions.py` + 1 added to `test_mcp_server.py` + 2 `test_turns_route.py` + 5 `test_stt_ws.py` + 1 `test_pcm_downsample_js.py` + 1 `test_stt_page.py`.

- [x] **Step 2: Lint**

Run: `uv run ruff check .`

Expected: exit code 0; `All checks passed!`.

- [x] **Step 3: Fix anything the two commands flag, then re-run both until green.**

Do not commit a red suite.

---

## Task 20: Close the phase

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/decisions.md`

- [x] **Step 1: Update the status in `AGENTS.md`**

Before:

```
- Current phase: 3 (microphone, VAD and STT). In progress: microphone capture, VAD and STT with timestamps.
```

After:

```
- Current phase: 4 (LLM, characters and evaluation). In progress: character dialogue and the success gauge.
```

If Phase 4 is not the next phase in `MEMORY.md` when this runs, keep the Phase 3 wording out and write the phase that `MEMORY.md` names next; do not invent a topic.

- [x] **Step 2: Append the decision to `docs/decisions.md`**

```markdown
## 2026-11-09 — Phase 3: Silero VAD on ONNX, faster-whisper as the default STT

- **Decision:** Phase 3 captures with `getUserMedia` + an `AudioWorklet` that emits 512-sample PCM16 chunks at 16 kHz (32 ms) over `/ws/stt`; the server segments turns with Silero VAD v5 (vendored ONNX, `onnxruntime`) and a pure `TurnDetector` (2 chunks to start, 700 ms of silence to close, 250 ms minimum of speech, 30 s maximum); only finished turns are transcribed, by faster-whisper `small` int8 by default, with Azure Speech as the alternative and a mock for the suite.
- **Discarded alternative:** the `silero-vad` PyPI package, which hard-requires `torch>=1.12` (≈2.5 GB) for a 2.2 MB model.
- **Discarded alternative:** amplitude- or energy-based VAD; the probabilities come from a real model.
- **Reason:** the ONNX session costs 0.09 ms per 32 ms chunk on this machine, the model is MIT and 2.2 MB, and `onnxruntime` already ships with `faster-whisper`.
- **Deviations from the design:** Azure receives raw PCM16 through `PushAudioInputStream` with an explicit `AudioStreamFormat(16000, 16, 1)` instead of a WAV, because that stream pushes sample frames and a RIFF header would be transcribed as a click. The 250 ms minimum counts **speech**, not turn duration: a turn cannot close before 700 ms of silence, so a duration minimum would never reject anything.
- **Consequences:** `SALES_TRAINER_STT=faster-whisper|azure|mock`, `SALES_TRAINER_WHISPER_MODEL` (default `small`), `SALES_TRAINER_SILENCE_MS` (default 700). `/ws/stt` validates `Origin` against `http://127.0.0.1:PORT` and `http://localhost:PORT` and the session token against `web/sessions.py`, which closes the Phase 0 known limit. Turns live in memory per session and are readable at `GET /api/turns?session=`.
- **Known limit:** the first faster-whisper run downloads the model (250-480 MB) and fails offline with `STTUnavailable`, which the socket forwards as `{"type":"error","code":"stt"}`; the automated suite never touches whisper.
- **Known limit:** the fake microphone e2e runs only the mock transcriber. Accuracy and latency of whisper and Azure remain a manual check; record the measured transcription time here when it is done.
- **Known limit:** no audio touches the disk and `SAVE_AUDIO` stays unimplemented until the configuration phase; the only committed audio is `tests/fixtures/hola-marta-16k.wav`.
```

- [x] **Step 3: Commit**

```bash
git add AGENTS.md docs/decisions.md
git commit -m "docs: close out phase 3"
```

---

## Spec coverage

- Criterion 1 (mic with `echoCancellation`/`noiseSuppression`, PCM16 mono 16 kHz ~32 ms over `/ws/stt`): Tasks 15-17 (`pcm.js`, `pcm-worklet.js`, `mic.js`, `/debug/stt`), proven live in Task 18.
- Criterion 2 (`Origin` and session token validation, tokens registered by `sales_trainer_start` or a page load): Tasks 10, 11, 13; rejected in `tests/unit/test_stt_ws.py` and `tests/unit/test_sessions.py`.
- Criterion 3 (speech + 700 ms of silence → one turn → exactly one transcript): Task 5 (`TurnDetector`, 8 tests) and Task 14 (`test_one_turn_produces_one_transcript_and_is_stored`); `SALES_TRAINER_SILENCE_MS` is read in Task 14.
- Criterion 4 (`text`, `language`, `words` with `word`/`start_ms`/`end_ms`/`probability` in 0-1): `base.py` in Task 5, produced by Tasks 6-8, emitted in Task 14, asserted in `test_stt_mock.py`, `test_stt_providers.py` and `test_stt_ws.py`.
- Criterion 5 (non-decreasing timings inside the turn): mock in Task 6 (`test_mock_timings_are_ordered_and_inside_the_turn`), whisper/azure word conversion in Tasks 7-8, end-to-end bound asserted in Task 14.
- Criterion 6 (`GET /api/turns?session=`): Task 12, asserted again from the socket in Task 14.
- Criterion 7 (suite green with no keys, no network, no model, `SALES_TRAINER_STT=mock`): Tasks 6, 9 (lazy imports), 14 and 18; the e2e runs with `SALES_TRAINER_STT=mock`.
- Criterion 8 (`ruff` clean, the 30 existing tests intact): Task 19.
- Non-goals respected: no partials (only `update.ended` is transcribed), no barge-in, no client-side segmentation, no audio on disk, no LLM/characters/evaluation, no `SAVE_AUDIO`, no diarization, no streaming synthesis.
- Spec "Files to change" that are **not** in this plan: none. `tests/unit/test_stt_providers.py` covers the factory, the Azure JSON parsing and the whisper conversion in one file, as the spec listed it.

## Execution order

Tasks 1-3 install what the rest needs (dependencies, the ONNX model, the committed fixture). Tasks 4-5 build the pure server-side core bottom-up (VAD → turn detection) with tests first. Tasks 6-9 add the three STT providers behind one protocol, then the factory. Tasks 10-14 expose the core: token registry, registration from both entry points, the turns endpoint, and the WebSocket (handshake first, then the turn loop). Tasks 15-17 build the browser side, smallest pure piece first. Task 18 proves the whole path with a real worklet, a real socket and a real VAD over the fake microphone, with only the transcriber doubled. Tasks 19-20 close the phase.
