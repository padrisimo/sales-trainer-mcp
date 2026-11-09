# Phase 2: TTS with Viseme Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-subagent-driven-development (recommended) or superpowers-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a Spanish sentence into audio plus a viseme timeline with the engine's real timings, serve both over `POST /api/tts`, and play them in `/debug/tts` driving the Phase 1 mouth morph targets from `AudioContext.currentTime`.

**Architecture:** `src/sales_trainer/voice/` holds a `TTSProvider` protocol, an Azure implementation that converts `viseme_received` tick offsets to milliseconds, and a deterministic mock provider that returns a real silent WAV. `POST /api/tts` returns base64 audio plus `{t_ms, viseme, weight}` events. In the browser, `speak.js` decodes the audio, plays it with Web Audio and samples `AudioContext.currentTime` every frame to pick the active viseme with a pure `visemeAt` function.

**Tech Stack:** Python 3.11, FastAPI 0.162, pydantic v2, `azure-cognitiveservices-speech` 1.53 (already installed), `wave` from the standard library, Three.js 0.187 (already vendored), pytest + Playwright.

**Repository:** `/Users/adrian/Documents/Projects/sales-trainer-mcp`, branch `main`. Starting point: 11 green tests, clean `ruff`, Phase 1 avatar with `avatar.group.userData.targetViseme` as the mouth control.

**Verified SDK facts (do not re-invent):** `SpeechSynthesizer.viseme_received` exists; `SpeechSynthesisVisemeEventArgs` exposes `viseme_id`, `audio_offset` (ticks, 100 ns) and `animation`; `SpeechSynthesisResult.audio_data` returns the audio bytes; `SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm` exists; `ResultReason.SynthesizingAudioCompleted` exists; `CancellationDetails` exposes `reason` and `error_details`.

---

## Task 1: Provider models and the viseme table

**Files:**
- Create: `src/sales_trainer/voice/__init__.py`
- Create: `src/sales_trainer/voice/tts/__init__.py`
- Create: `src/sales_trainer/voice/tts/base.py`
- Create: `src/sales_trainer/voice/visemes.py`
- Create: `tests/unit/test_visemes.py`

- [x] **Step 1: Create the package files**

`src/sales_trainer/voice/__init__.py`:

```python
"""Voice pipeline: TTS, visemes, and later STT and prosody."""
```

- [x] **Step 2: Create `src/sales_trainer/voice/tts/base.py`**

```python
from typing import Protocol

from pydantic import BaseModel, Field


class VisemeEvent(BaseModel):
    t_ms: int = Field(ge=0)
    viseme: str
    weight: float = Field(ge=0.0, le=1.0)


class TTSResult(BaseModel):
    audio: bytes
    mime: str = "audio/wav"
    visemes: list[VisemeEvent]


class TTSUnavailable(RuntimeError):
    """Raised when the configured provider cannot synthesize."""


class TTSProvider(Protocol):
    def synthesize(self, text: str, voice: str | None = None) -> TTSResult: ...
```

- [x] **Step 3: Create `src/sales_trainer/voice/visemes.py`**

```python
from sales_trainer.voice.tts.base import VisemeEvent

# Same 15 names, same order, as src/sales_trainer/web/static/js/visemes.js.
VISEMES = [
    "sil",
    "PP",
    "FF",
    "TH",
    "DD",
    "kk",
    "CH",
    "SS",
    "nn",
    "RR",
    "aa",
    "E",
    "I",
    "O",
    "U",
]

# Azure viseme IDs 0-21 to our set. Spanish has phonemes with no Oculus counterpart
# (h, l, r), so they land on the closest shape instead of being dropped.
AZURE_VISEME_TO_VISEME = {
    0: "sil",
    1: "aa",
    2: "aa",
    3: "O",
    4: "E",
    5: "RR",
    6: "I",
    7: "U",
    8: "O",
    9: "aa",
    10: "O",
    11: "aa",
    12: "aa",
    13: "RR",
    14: "DD",
    15: "SS",
    16: "CH",
    17: "TH",
    18: "FF",
    19: "DD",
    20: "kk",
    21: "PP",
}

MERGE_WINDOW_MS = 60


def azure_to_viseme(azure_id: int) -> str:
    return AZURE_VISEME_TO_VISEME.get(azure_id, "sil")


def smooth(events: list[VisemeEvent], merge_window_ms: int = MERGE_WINDOW_MS) -> list[VisemeEvent]:
    """Drop duplicates that would flicker the mouth, keeping the timeline monotonic."""
    out: list[VisemeEvent] = []
    for event in sorted(events, key=lambda item: item.t_ms):
        if event.t_ms < 0:
            continue
        if out and out[-1].viseme == event.viseme and event.t_ms - out[-1].t_ms <= merge_window_ms:
            continue
        out.append(event)
    return out
```

- [x] **Step 4: Write `tests/unit/test_visemes.py`**

```python
import re
from pathlib import Path

from sales_trainer.voice.tts.base import VisemeEvent
from sales_trainer.voice.visemes import (
    AZURE_VISEME_TO_VISEME,
    VISEMES,
    azure_to_viseme,
    smooth,
)

ROOT = Path(__file__).resolve().parents[2]
VISEMES_JS = ROOT / "src" / "sales_trainer" / "web" / "static" / "js" / "visemes.js"


def test_azure_mapping_covers_every_id() -> None:
    assert set(AZURE_VISEME_TO_VISEME) == set(range(22))


def test_azure_mapping_targets_are_known_visemes() -> None:
    assert set(AZURE_VISEME_TO_VISEME.values()) <= set(VISEMES)


def test_unknown_azure_id_falls_back_to_silence() -> None:
    assert azure_to_viseme(99) == "sil"


def test_smooth_keeps_the_timeline_monotonic() -> None:
    events = [
        VisemeEvent(t_ms=300, viseme="aa", weight=1.0),
        VisemeEvent(t_ms=100, viseme="PP", weight=1.0),
    ]
    assert [event.t_ms for event in smooth(events)] == [100, 300]


def test_smooth_drops_duplicates_inside_the_window() -> None:
    events = [
        VisemeEvent(t_ms=0, viseme="aa", weight=1.0),
        VisemeEvent(t_ms=40, viseme="aa", weight=1.0),
        VisemeEvent(t_ms=400, viseme="aa", weight=1.0),
    ]
    assert [event.t_ms for event in smooth(events)] == [0, 400]


def test_smooth_keeps_a_real_change_of_shape() -> None:
    events = [
        VisemeEvent(t_ms=0, viseme="aa", weight=1.0),
        VisemeEvent(t_ms=40, viseme="PP", weight=1.0),
    ]
    assert [event.viseme for event in smooth(events)] == ["aa", "PP"]


def test_python_and_javascript_viseme_lists_match() -> None:
    source = VISEMES_JS.read_text(encoding="utf-8")
    block = re.search(r"export const VISEMES = \[(.*?)\];", source, re.S)
    assert block is not None
    js_names = re.findall(r'"([^"]+)"', block.group(1))
    assert js_names == VISEMES
```

- [x] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_visemes.py -v`

Expected: exit code 0; `7 passed`.

- [x] **Step 6: Commit**

```bash
git add src/sales_trainer/voice tests/unit/test_visemes.py
git commit -m "feat: add viseme table and azure mapping"
```

---

## Task 2: Mock provider with a real silent WAV

**Files:**
- Create: `src/sales_trainer/voice/tts/mock.py`
- Create: `src/sales_trainer/voice/tts/__init__.py`
- Create: `tests/unit/test_tts_mock.py`

- [x] **Step 1: Create `src/sales_trainer/voice/tts/mock.py`**

```python
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
```

- [x] **Step 2: Create `src/sales_trainer/voice/tts/__init__.py`**

```python
import os

from sales_trainer.voice.tts.base import TTSProvider, TTSResult, TTSUnavailable, VisemeEvent
from sales_trainer.voice.tts.mock import MockTTSProvider

__all__ = ["TTSProvider", "TTSResult", "TTSUnavailable", "VisemeEvent", "get_provider"]


def get_provider() -> TTSProvider:
    name = os.environ.get("SALES_TRAINER_TTS", "azure").lower()
    if name == "mock":
        return MockTTSProvider()
    if name == "azure":
        # Imported lazily so the mock path never imports the Azure SDK.
        from sales_trainer.voice.tts.azure import AzureTTSProvider

        return AzureTTSProvider()
    raise TTSUnavailable(f"unknown SALES_TRAINER_TTS value: {name}")
```

- [x] **Step 3: Write `tests/unit/test_tts_mock.py`**

```python
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
```

- [x] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_tts_mock.py -v`

Expected: exit code 0; `3 passed`.

- [x] **Step 5: Commit**

```bash
git add src/sales_trainer/voice/tts tests/unit/test_tts_mock.py
git commit -m "feat: add mock tts provider with real silent wav"
```

---

## Task 3: Azure provider

**Files:**
- Create: `src/sales_trainer/voice/tts/azure.py`
- Create: `tests/unit/test_tts_azure.py`

- [x] **Step 1: Create `src/sales_trainer/voice/tts/azure.py`**

```python
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
```

- [x] **Step 2: Write `tests/unit/test_tts_azure.py`**

```python
from types import SimpleNamespace

import pytest

from sales_trainer.voice.tts.base import TTSUnavailable
from sales_trainer.voice.tts.azure import AzureTTSProvider


def test_missing_credentials_raise() -> None:
    with pytest.raises(TTSUnavailable):
        AzureTTSProvider(key="", region="", voice="es-ES-ElviraNeural")


def test_ticks_are_converted_to_milliseconds() -> None:
    provider = AzureTTSProvider(key="k", region="r")
    event = provider._events_from(SimpleNamespace(audio_offset=12_340_000, viseme_id=21))
    assert event.t_ms == 1234
    assert event.viseme == "PP"


def test_unknown_azure_viseme_becomes_silence() -> None:
    provider = AzureTTSProvider(key="k", region="r")
    event = provider._events_from(SimpleNamespace(audio_offset=0, viseme_id=99))
    assert event.viseme == "sil"
```

- [x] **Step 3: Run the tests**

Run: `uv run pytest tests/unit/test_tts_azure.py -v`

Expected: exit code 0; `3 passed`.

- [x] **Step 4: Commit**

```bash
git add src/sales_trainer/voice/tts/azure.py tests/unit/test_tts_azure.py
git commit -m "feat: add azure tts provider with native viseme offsets"
```

---

## Task 4: HTTP endpoint

**Files:**
- Create: `src/sales_trainer/web/routes/__init__.py`
- Create: `src/sales_trainer/web/routes/tts.py`
- Create: `tests/unit/test_tts_route.py`
- Modify: `src/sales_trainer/web/app.py`

- [x] **Step 1: Write the failing test**

`tests/unit/test_tts_route.py`:

```python
import base64
import io
import wave

import pytest
from fastapi.testclient import TestClient

from sales_trainer.web.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _use_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SALES_TRAINER_TTS", "mock")


def test_tts_returns_audio_and_visemes() -> None:
    response = client.post("/api/tts", json={"text": "Hola, soy Marta."})
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"audio_base64", "mime", "visemes"}
    assert payload["mime"] == "audio/wav"
    with wave.open(io.BytesIO(base64.b64decode(payload["audio_base64"])), "rb") as wav:
        assert wav.getnframes() > 0
    assert payload["visemes"]
    first = payload["visemes"][0]
    assert set(first) == {"t_ms", "viseme", "weight"}


def test_tts_rejects_empty_text() -> None:
    assert client.post("/api/tts", json={"text": ""}).status_code == 422


def test_tts_rejects_oversized_text() -> None:
    assert client.post("/api/tts", json={"text": "a" * 401}).status_code == 422


def test_tts_reports_unavailable_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SALES_TRAINER_TTS", "azure")
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    assert client.post("/api/tts", json={"text": "Hola."}).status_code == 503
```

- [x] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_tts_route.py -v`

Expected: FAIL — exit code 1; the first test fails with `assert 404 == 200`.

- [x] **Step 3: Create `src/sales_trainer/web/routes/__init__.py`**

```python
"""HTTP routes for the web UI."""
```

- [x] **Step 4: Create `src/sales_trainer/web/routes/tts.py`**

```python
import base64

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sales_trainer.voice.tts import get_provider
from sales_trainer.voice.tts.base import TTSUnavailable

router = APIRouter(prefix="/api", tags=["tts"])

MAX_TEXT_LENGTH = 400


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)


@router.post("/tts")
def synthesize(request: TTSRequest) -> dict[str, object]:
    try:
        result = get_provider().synthesize(request.text)
    except TTSUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return {
        "audio_base64": base64.b64encode(result.audio).decode("ascii"),
        "mime": result.mime,
        "visemes": [event.model_dump() for event in result.visemes],
    }
```

- [x] **Step 5: Mount the router and the debug page in `src/sales_trainer/web/app.py`**

Add the import and the include right after `app.mount(...)`:

```python
from sales_trainer.web.routes import tts as tts_routes
...
app.include_router(tts_routes.router)
```

And add the route, next to `/debug/visemes`:

```python
@app.get("/debug/tts")
async def debug_tts(session: str = "") -> HTMLResponse:
    return _page("debug/tts.html", session)
```

- [x] **Step 6: Create a placeholder page so the route test can pass**

`src/sales_trainer/web/static/debug/tts.html` (completed in Task 6):

```html
<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <title>Sales Trainer — TTS</title>
  </head>
  <body>
    <canvas id="avatar"></canvas>
    <div id="controls">
      <input id="text" value="Hola, soy Marta. ¿En qué puedo ayudarte?" />
      <button id="speak" type="button">Hablar</button>
      <p id="status">listo</p>
    </div>
    <script type="module" src="/static/js/tts-debug.js"></script>
  </body>
</html>
```

- [x] **Step 7: Run the route tests**

Run: `uv run pytest tests/unit/test_tts_route.py -v`

Expected: exit code 0; `4 passed`.

- [x] **Step 8: Commit**

```bash
git add src/sales_trainer/web/routes src/sales_trainer/web/app.py src/sales_trainer/web/static/debug/tts.html tests/unit/test_tts_route.py
git commit -m "feat: add tts http endpoint"
```

---

## Task 5: `visemeAt` — the pure sync function

**Files:**
- Create: `src/sales_trainer/web/static/js/speak.js`
- Create: `tests/js/viseme_timeline.mjs`
- Create: `tests/unit/test_viseme_timeline_js.py`

- [ ] **Step 1: Create `src/sales_trainer/web/static/js/speak.js`**

```javascript
// Pure timeline lookup: the last event at or before tMs, "sil" before the first
// event and when the timeline is empty. The player samples AudioContext.currentTime
// and asks this function, so the mouth never drifts with timer accumulation.
export function visemeAt(timeline, tMs) {
  let current = "sil";
  for (const event of timeline) {
    if (event.t_ms > tMs) break;
    current = event.viseme;
  }
  return current;
}

let audioContext = null;

function getAudioContext() {
  if (audioContext === null) {
    audioContext = new AudioContext();
  }
  return audioContext;
}

export async function speak(text, { onViseme = () => {}, onEnd = () => {} } = {}) {
  const response = await fetch("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!response.ok) {
    throw new Error(`tts request failed: ${response.status}`);
  }
  const payload = await response.json();

  const raw = atob(payload.audio_base64);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) {
    bytes[i] = raw.charCodeAt(i);
  }

  const context = getAudioContext();
  await context.resume();
  const buffer = await context.decodeAudioData(bytes.buffer);

  const source = context.createBufferSource();
  source.buffer = buffer;
  source.connect(context.destination);

  const startedAt = context.currentTime;
  const durationMs = buffer.duration * 1000;

  function tick() {
    const elapsedMs = (context.currentTime - startedAt) * 1000;
    if (elapsedMs > durationMs + 100) {
      return;
    }
    onViseme(visemeAt(payload.visemes, elapsedMs), elapsedMs);
    requestAnimationFrame(tick);
  }

  source.onended = () => onEnd();
  source.start(startedAt);
  requestAnimationFrame(tick);

  return { durationMs, timeline: payload.visemes };
}
```

- [ ] **Step 2: Write `tests/js/viseme_timeline.mjs`**

```javascript
import { visemeAt } from "../../src/sales_trainer/web/static/js/speak.js";

const timeline = [
  { t_ms: 0, viseme: "sil", weight: 1 },
  { t_ms: 100, viseme: "aa", weight: 1 },
  { t_ms: 300, viseme: "PP", weight: 1 },
];

function expect(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${expected}, got ${actual}`);
  }
}

expect(visemeAt([], 0), "sil", "empty timeline");
expect(visemeAt(timeline, 0), "sil", "first event");
expect(visemeAt(timeline, 99), "sil", "just before the change");
expect(visemeAt(timeline, 100), "aa", "exact boundary");
expect(visemeAt(timeline, 299), "aa", "inside a segment");
expect(visemeAt(timeline, 300), "PP", "second boundary");
expect(visemeAt(timeline, 99999), "PP", "holds until the end");

console.log("viseme timeline ok");
```

- [ ] **Step 3: Write `tests/unit/test_viseme_timeline_js.py`**

```python
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_viseme_timeline_script_passes() -> None:
    result = subprocess.run(
        ["node", str(ROOT / "tests" / "js" / "viseme_timeline.mjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "viseme timeline ok" in result.stdout
```

- [ ] **Step 4: Run it**

Run: `uv run pytest tests/unit/test_viseme_timeline_js.py -v`

Expected: exit code 0; `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/sales_trainer/web/static/js/speak.js tests/js/viseme_timeline.mjs tests/unit/test_viseme_timeline_js.py
git commit -m "feat: add audio playback and pure viseme lookup"
```

---

## Task 6: `/debug/tts` page

**Files:**
- Create: `src/sales_trainer/web/static/js/tts-debug.js`
- Modify: `src/sales_trainer/web/static/debug/tts.html`

- [ ] **Step 1: Create `src/sales_trainer/web/static/js/tts-debug.js`**

```javascript
import { createScene } from "./scene.js";
import { speak } from "./speak.js";

const canvas = document.getElementById("avatar");
const input = document.getElementById("text");
const button = document.getElementById("speak");
const status = document.getElementById("status");

const scene = createScene(canvas);

const state = { ready: false, speaking: false, activeViseme: "sil", timelineLength: 0 };
window.ttsDebug = state;

button.addEventListener("click", async () => {
  if (state.speaking) {
    return;
  }
  state.speaking = true;
  status.textContent = "hablando";
  try {
    const result = await speak(input.value, {
      onViseme: (viseme) => {
        state.activeViseme = viseme;
        scene.avatar.group.userData.targetViseme = viseme;
      },
      onEnd: () => {
        state.speaking = false;
        state.activeViseme = "sil";
        scene.avatar.group.userData.targetViseme = "sil";
        status.textContent = "listo";
      },
    });
    state.timelineLength = result.timeline.length;
  } catch (error) {
    state.speaking = false;
    status.textContent = `error: ${error.message}`;
  }
});

requestAnimationFrame(() => {
  requestAnimationFrame(() => {
    state.ready = true;
  });
});
```

- [ ] **Step 2: Write the final `src/sales_trainer/web/static/debug/tts.html`**

```html
<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Sales Trainer — TTS</title>
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
        grid-template-columns: 1fr 320px;
      }
      #avatar {
        display: block;
        width: 100%;
        height: 100%;
      }
      #controls {
        padding: 12px;
        background: #171d24;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      #text {
        padding: 8px;
        border: 1px solid #2c3642;
        border-radius: 6px;
        background: #1f2833;
        color: inherit;
      }
      #speak {
        padding: 10px;
        border: 1px solid #2c3642;
        border-radius: 6px;
        background: #2a3542;
        color: inherit;
        cursor: pointer;
      }
    </style>
  </head>
  <body>
    <canvas id="avatar"></canvas>
    <section id="controls">
      <label for="text">Frase</label>
      <input id="text" value="Hola, soy Marta. ¿En qué puedo ayudarte?" />
      <button id="speak" type="button">Hablar</button>
      <p id="status">listo</p>
      <p>Los visemas vienen del motor TTS con sus tiempos; el reloj maestro es <code>AudioContext.currentTime</code>.</p>
    </section>
    <script type="module" src="/static/js/tts-debug.js"></script>
  </body>
</html>
```

- [ ] **Step 3: Verify the route and the static file**

Run:

```bash
uv run python -c "
from fastapi.testclient import TestClient
from sales_trainer.web.app import app
c = TestClient(app)
print('debug tts', c.get('/debug/tts').status_code)
print('tts-debug.js', c.get('/static/js/tts-debug.js').status_code)
print('speak.js', c.get('/static/js/speak.js').status_code)
"
```

Expected: exit code 0; `debug tts 200`, `tts-debug.js 200`, `speak.js 200`.

- [ ] **Step 4: Commit**

```bash
git add src/sales_trainer/web/static/js/tts-debug.js src/sales_trainer/web/static/debug/tts.html
git commit -m "feat: add tts debug page"
```

---

## Task 7: End-to-end playback test

**Files:**
- Create: `tests/e2e/test_tts_page.py`

- [ ] **Step 1: Create the test**

```python
import os
import subprocess
import time
import urllib.error
import urllib.request

import pytest
from playwright.sync_api import sync_playwright

PORT = 8125
BASE_URL = f"http://127.0.0.1:{PORT}"


def _wait_for_server(timeout_seconds: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = urllib.request.urlopen(f"{BASE_URL}/debug/tts", timeout=2)
            try:
                if response.status == 200:
                    return
            finally:
                response.close()
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    raise RuntimeError("web server did not become ready in time")


@pytest.mark.e2e
def test_debug_tts_page_speaks_and_moves_the_mouth() -> None:
    env = {**os.environ, "SALES_TRAINER_TTS": "mock"}
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
                ]
            )
            page = browser.new_page()

            def on_console(message) -> None:
                if message.type == "error":
                    errors.append(message.text)

            page.on("console", on_console)
            page.on("pageerror", lambda error: errors.append(str(error)))

            page.goto(f"{BASE_URL}/debug/tts")
            page.wait_for_function("window.ttsDebug && window.ttsDebug.ready === true")

            page.click("#speak")
            page.wait_for_function("window.ttsDebug.speaking === true")

            seen = set()
            for _ in range(20):
                seen.add(page.evaluate("window.ttsDebug.activeViseme"))
                page.wait_for_timeout(80)

            page.wait_for_function("window.ttsDebug.speaking === false", timeout=10000)

            assert page.evaluate("window.ttsDebug.timelineLength") >= 5
            assert len(seen) >= 2, f"the mouth never changed viseme: {seen}"
            assert errors == []
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
```

- [ ] **Step 2: Run it**

Run: `uv run pytest -m e2e -v`

Expected: exit code 0; `3 passed`.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_tts_page.py
git commit -m "test: add e2e coverage for tts playback and lip sync"
```

---

## Task 8: Full suite and linter

- [ ] **Step 1: Run everything**

Run: `uv run pytest -v`

Expected: exit code 0; `30 passed` (11 existing + 7 visemes + 3 mock + 3 azure + 4 route + 1 timeline JS + 1 e2e).

- [ ] **Step 2: Lint**

Run: `uv run ruff check .`

Expected: exit code 0; `All checks passed!`.

- [ ] **Step 3: Fix anything the two commands flag, then re-run both until green.**

---

## Task 9: Close the phase

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/decisions.md`

- [ ] **Step 1: Update the status in `AGENTS.md`**

Before:

```
- Current phase: 2 (TTS with visemes). In progress: TTS with a synchronized viseme timeline.
- Update here when closing each phase.
```

After:

```
- Current phase: 3 (microphone, VAD and STT). In progress: microphone capture, VAD and STT with timestamps.
- Update here when closing each phase.
```

- [ ] **Step 2: Append the decision to `docs/decisions.md`**

```markdown
## 2026-11-03 — Phase 2: Azure as the TTS provider

- **Decision:** Phase 2 uses Azure Speech as the real TTS provider (native `viseme_received` events with audio offsets in ticks) plus an explicit mock provider for tests.
- **Discarded alternative:** local Piper/Kokoro in this phase, which would need forced alignment with torch to obtain real phoneme timings.
- **Reason:** Azure is the only source of true per-viseme offsets anchored to the audio it just produced, which is exactly what the 40 ms criterion needs; the offline provider gets its own phase.
- **Consequences:** `SALES_TRAINER_TTS=azure|mock` selects the provider; the mock is never a silent fallback. Ticks are converted with `ticks / 10_000`. Audio travels inline as base64, capped at 400 characters per request.
- **Known limit:** Azure viseme IDs 0-21 do not cover every Spanish phoneme; `h`, `l` and `r` land on the closest shape and the mapping is explicit in `voice/visemes.py`.
- **Known limit:** without an Azure key the automated suite only exercises the mock, so lip sync against the real engine stays a manual check.
```

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md docs/decisions.md
git commit -m "docs: close out phase 2"
```

---

## Spec coverage

- Criterion 1 (`POST /api/tts` returns audio, mime and visemes): Tasks 2-4, covered by `tests/unit/test_tts_route.py`.
- Criterion 2 (names always in the 15-set; unmapped IDs become `sil`): Tasks 1 and 3.
- Criterion 3 (monotonic timeline inside the audio): Task 1 (`smooth`) and Task 2 (mock duration bound).
- Criterion 4 (`/debug/tts` speaks and exposes `window.ttsDebug`): Tasks 6-7.
- Criterion 5 (`AudioContext.currentTime` as master clock): Task 5 (`visemeAt` + player loop), asserted in Task 7.
- Criterion 6 (suite green without keys or network): Task 7 runs the e2e with `SALES_TRAINER_TTS=mock`.
- Criterion 7 (ruff clean, previous tests intact): Task 8.
- Non-goals respected: no STT, no characters, no evaluation, no local provider, no audio persisted, no streaming.

## Execution order

Tasks 1-3 build the Python voice layer bottom-up (table → mock → Azure); Task 4 exposes it over HTTP with a red/green cycle; Tasks 5-6 build the browser side; Task 7 proves it in a real browser with the mock; Tasks 8-9 close.
