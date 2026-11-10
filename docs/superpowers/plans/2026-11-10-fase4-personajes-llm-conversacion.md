# Phase 4: Characters, LLM and the Conversation Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-subagent-driven-development (recommended) or superpowers-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user hold a spoken conversation with one of three characters: each finished voice turn goes to an `LLMProvider`, the answer is split into sentences, synthesized one sentence at a time and played by the browser, the user can interrupt the avatar while it speaks, and the conversation ends at the character's turn limit.

**Architecture:** A second WebSocket, `/ws/chat?session=&level=&product=`, reuses the `/ws/stt` handshake and VAD/turn loop, but turns each finished turn into a conversation exchange: `chat.begin()` counts the turn, a background task calls the provider in a worker thread, `split_sentences()` cuts the answer, and one TTS call plus one `audio` message is sent per sentence while a barge-in window stays armed. Characters are three YAML cards plus three Spanish prompt files, validated with pydantic at load. `/debug/chat` drives the whole thing with the microphone and `window.chatDebug` for the e2e.

**Tech Stack:** Python 3.12 (`.venv`), FastAPI 0.162 + Starlette WebSockets, pydantic v2, `httpx` 0.28 (`MockTransport` for the provider tests), `pyyaml` (new), the Phase 3 Silero VAD + `TurnDetector`, the Phase 2/3 TTS providers, pytest + Playwright, Node only for the existing JS checks.

**Repository:** `/Users/adrian/Documents/Projects/sales-trainer-mcp`, branch `main`. Starting point: **68 tests green — 64 unit/integration plus 4 e2e** (`uv run pytest -q` prints `68 passed`), `uv run ruff check .` clean, Python 3.12.15 in `.venv` (the system `python3` is 3.9, always use `uv run`), macOS arm64. Phase 3 shipped `/ws/stt` (`src/sales_trainer/web/routes/stt_ws.py`), `voice/turns.py` (`TurnDetector`, `TurnStore`, `CHUNK_MS`, `THRESHOLD`), `voice/stt` and `voice/tts` provider factories, `web/sessions.py`, and `/debug/stt`.

**Verified facts (do not re-derive):**

- `pytest` notices no `tests/conftest.py`; every test file builds its own `TestClient(app)` and registers its own session tokens with `web.sessions.register`.
- `TestClient.websocket_connect(url, headers={"origin": ...})` accepts a custom `Origin`; a handler that calls `accept()` then `send_json(...)` then `close(code=1008)` lets the client read the error frame before `WebSocketDisconnect` (used by the Phase 3 tests, still true).
- Starlette delivers a text frame as `message["text"]` and a binary frame as `message["bytes"]` from `websocket.receive()`; a frame that is neither has both keys set to `None`.
- `asyncio.to_thread(fn, *args)` runs `fn` in the default executor, so a blocking provider call or an Azure TTS call never blocks the socket's receive loop.
- `asyncio.CancelledError` derives from `BaseException`, so `except LLMUnavailable` and `except TTSUnavailable` never swallow a cancellation.
- `pathlib.Path.is_relative_to` exists on Python 3.11+ and needs resolved absolute paths to be trustworthy.
- `httpx.MockTransport(handler)` builds a client that runs `handler(request)` in-process: no socket, no key, no network. `httpx.Client(transport=...)` accepts it.
- `sales_trainer` calls `load_dotenv(repo/.env, override=False)` at import, so a real environment variable always wins over `.env`. Tests that assert "no model configured" must `monkeypatch.delenv(...)` instead of trusting the ambient environment.
- `voice/tts` names its factory `get_provider`; this plan names the LLM factory `get_llm_provider` because `/ws/chat` imports both and two `get_provider` names in one module would be ambiguous.
- `ruff` has **no** configuration file in this repo (default rules E4/E7/E9/F), but every code block below is also clean under `BLE001` (never `except Exception`), `PLW1510` (`subprocess.run` needs `check=`), `I001` and `E501` (120 columns), so the plan survives a future `[tool.ruff]`.

**Behaviour the spec leaves open, decided here (recorded in Task 16):**

1. A character card that fails to load for a valid level is reported to the client as `{"type":"error","code":"level"}`: the documented code set has no `character` code, the three cards ship with the code, and a broken card means "this level is not available", which is what the page needs to say.
2. `build_system` injects the prompt, the product brief and the four card lists, but **not** the temperature, the threshold or the turn limit: the prompt forbids the character from revealing those numbers, so putting them in the system prompt would invite exactly that leak. Phase 5 reads them from the card in code.
3. A TTS provider that cannot be built when the socket connects is rejected with `{"type":"error","code":"tts"}` and the socket closes, the same class of failure as `llm_config` and for the same reason: without a voice there is no conversation. The spec only names `llm_config`; this is the same rule applied to the other provider the socket builds.
4. `mic.js` gains a `path`/`params` argument and a `send(payload)` method so `chat-debug.js` can reuse it against `/ws/chat` and answer `{"type":"played"}`. The spec says the page "reuses `mic.js`", which is impossible without that argument because `mic.js` hard-codes `/ws/stt`. Two lines change, the STT page keeps its default.
5. After `end` the socket stays open but ignores further audio, instead of closing: closing from the reply task while the receive loop is between messages risks a `Cannot call send once close has been sent` race, and a flag is one line.
6. `end` is sent even when the last turn's provider call failed, because the turn limit was reached either way and a client waiting for `end` must not hang.

---

## Task 1: Add `pyyaml`

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [x] **Step 1: Add the dependency**

Run:

```bash
uv add pyyaml
```

Expected: exit code 0; `uv` prints `Resolved N packages` and `Installed 1 package`, and `pyproject.toml` gains `"pyyaml>=6.0.3"` (or a later `>=` pin) under `dependencies`.

- [x] **Step 2: Verify the import and the version**

Run:

```bash
uv run python -c "import yaml; print('pyyaml', yaml.__version__); print(yaml.safe_load('nivel: 1'))"
```

Expected: exit code 0; `pyyaml 6.0.x` and `{'nivel': 1}`.

- [x] **Step 3: Confirm the suite is still green**

Run: `uv run pytest -q`

Expected: exit code 0; `68 passed`.

- [x] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add pyyaml for the character cards"
```

---

## Task 2: The three character cards and their prompts

**Files:**
- Create: `characters/nivel1.yaml`
- Create: `characters/nivel2.yaml`
- Create: `characters/nivel3.yaml`
- Create: `characters/prompts/nivel1.md`
- Create: `characters/prompts/nivel2.md`
- Create: `characters/prompts/nivel3.md`

The numbers are fixed by `MEMORY.md` §5: Marta 50/75/10, Javier 30/80/10, Carmen 10/85/8. Card field names and comments stay in English; the prompt text is Spanish because it is what the character says.

- [x] **Step 1: Create `characters/nivel1.yaml`**

```yaml
# Level 1 — Easy: receptive operations director. Numbers from MEMORY.md §5.
level: 1
name: Marta Ruiz
voice: es-ES-ElviraNeural
start_temperature: 50
threshold: 75
max_turns: 10
prompt: prompts/nivel1.md
objections:
  - "No sé si mi equipo tendrá tiempo para aprender otra herramienta."
  - "Ahora mismo lo hacemos con hojas de cálculo y nos vale."
hot_buttons:
  - "Ahorro de tiempo medible por semana"
  - "Casos parecidos en empresas de reparto"
cold_buttons:
  - "Precios sin cifras de retorno"
  - "Discursos largos y genéricos"
filler_words:
  - "A ver"
  - "Claro, claro"
```

- [x] **Step 2: Create `characters/nivel2.yaml`**

```yaml
# Level 2 — Medium: neutral and skeptical manager. Numbers from MEMORY.md §5.
level: 2
name: Javier Soto
voice: es-ES-AlvaroNeural
start_temperature: 30
threshold: 80
max_turns: 10
prompt: prompts/nivel2.md
objections:
  - "Ya trabajo con otro proveedor y cambiar ahora me cuesta dinero."
  - "No tengo tiempo para migrar los datos."
  - "Eso suena bien, pero necesito números."
hot_buttons:
  - "Ejemplos reales con cifras"
  - "Una migración sin parar la operación"
cold_buttons:
  - "Vaguezas y promesas sin datos"
  - "Presentaciones largas"
filler_words:
  - "Ya, ya"
  - "Hombre, depende"
```

- [x] **Step 3: Create `characters/nivel3.yaml`**

```yaml
# Level 3 — Hard: uninterested CFO with two minutes. Numbers from MEMORY.md §5.
level: 3
name: Carmen Valdés
voice: es-ES-XimenaNeural
start_temperature: 10
threshold: 85
max_turns: 8
prompt: prompts/nivel3.md
objections:
  - "Solo tengo dos minutos, dígame lo esencial."
  - "No veo por qué debería cambiar nada."
  - "Eso ya lo he oído antes."
hot_buttons:
  - "Horas ahorradas por semana y euros al mes"
  - "Retorno de la inversión y plazo de recuperación"
cold_buttons:
  - "Clichés y palabras de relleno"
  - "Monotonía y discursos largos"
filler_words:
  - "Mmm"
  - "Vamos al grano"
```

- [x] **Step 4: Create `characters/prompts/nivel1.md`**

```markdown
# Nivel 1 — Marta Ruiz

Eres Marta Ruiz, directora de operaciones de una empresa de reparto con 40 personas. Estás
interesada en el producto que te venden, pero no vas a comprar nada sin entenderlo.

## Cómo hablas

- Español de España, tono cercano y profesional.
- Respondes en una a tres frases cortas, nunca en párrafos.
- Haces una pregunta concreta cuando falta información para decidir.
- Reconoces los datos concretos que te dan y pides la cifra cuando te hablan en abstracto.

## Reglas que no puedes romper

- Nunca menciones la temperatura, la puntuación, el umbral de éxito ni el número de turnos.
- No sabes nada del producto salvo lo que el vendedor te ha contado en la conversación.
  Si no lo ha dicho, no lo inventes: pregúntalo.
- No describes tu propio estado interno ni hablas de la evaluación.
- Si el vendedor se alarga o divaga, lo dices en una frase y pides concreción.

## Qué te convence

- Ahorro de tiempo medible: minutos por ruta, horas por semana.
- Casos parecidos en empresas de reparto.
- Un precio que se pueda comparar con ese ahorro.

## Qué te enfría

- Precios sin ninguna cifra de retorno.
- Discursos largos y genéricos.
```

- [ ] **Step 5: Create `characters/prompts/nivel2.md`**

```markdown
# Nivel 2 — Javier Soto

Eres Javier Soto, jefe de operaciones de una empresa de distribución mediana. Escuchas por
educación, pero desconfías: ya te han vendido humo antes.

## Cómo hablas

- Español de España, tono neutro y algo escéptico.
- Respondes en una a tres frases cortas.
- Sueles abrir con una objeción y luego pides una prueba.
- Pides ejemplos, cifras y plazos concretos antes de moverte.

## Reglas que no puedes romper

- Nunca menciones la temperatura, la puntuación, el umbral de éxito ni el número de turnos.
- No sabes nada del producto salvo lo que el vendedor te ha contado en la conversación.
  Si no lo ha dicho, no lo inventes: pregúntalo.
- No describes tu propio estado interno ni hablas de la evaluación.
- Si el vendedor promete algo sin datos, lo señalas y pides el número.

## Qué te convence

- Ejemplos reales con cifras.
- Una migración que no pare la operación.

## Qué te enfría

- Vaguezas y promesas sin datos.
- Presentaciones largas y genéricas.
```

- [ ] **Step 6: Create `characters/prompts/nivel3.md`**

```markdown
# Nivel 3 — Carmen Valdés

Eres Carmen Valdés, directora financiera. Solo le das dos minutos a este vendedor y tu
impaciencia se nota en cada frase.

## Cómo hablas

- Español de España, tono seco y cortante.
- Respondes en una o dos frases muy cortas, nunca más de tres.
- Interrumpes si la respuesta se alarga: "Vamos al grano".
- Contestas con otra pregunta cuando algo no está cuantificado.

## Reglas que no puedes romper

- Nunca menciones la temperatura, la puntuación, el umbral de éxito ni el número de turnos.
- No sabes nada del producto salvo lo que el vendedor te ha contado en la conversación.
  Si no lo ha dicho, no lo inventes: pregúntalo.
- No describes tu propio estado interno ni hablas de la evaluación.
- Si oyes un cliché o una muletilla, lo dices y pides una cifra.

## Qué te convence

- Horas ahorradas por semana y euros al mes.
- Retorno de la inversión y plazo de recuperación.
- Pruebas sociales creíbles y preguntas de descubrimiento buenas.

## Qué te enfría

- Clichés, muletillas y monotonía.
- Discursos largos sin una sola cifra.
```

- [ ] **Step 7: Verify the cards parse and carry the `MEMORY.md` numbers**

Run:

```bash
uv run python -c "
import yaml
from pathlib import Path
for level in (1, 2, 3):
    card = yaml.safe_load(Path(f'characters/nivel{level}.yaml').read_text(encoding='utf-8'))
    prompt = Path('characters') / card['prompt']
    text = prompt.read_text(encoding='utf-8') if prompt.is_file() else ''
    print(level, card['name'], card['start_temperature'], card['threshold'], card['max_turns'], prompt.is_file(), len(text) > 800)
"
```

Expected: exit code 0; three lines whose first six fields are exactly:

```
1 Marta Ruiz 50 75 10 True True
2 Javier Soto 30 80 10 True True
3 Carmen Valdés 10 85 8 True True
```

- [ ] **Step 8: Commit**

```bash
git add characters
git commit -m "feat: add the three character cards and their spanish prompts"
```

---

## Task 3: `characters` package — the pydantic card loader

**Files:**
- Create: `src/sales_trainer/characters/__init__.py`
- Create: `src/sales_trainer/characters/loader.py`
- Test: `tests/unit/test_characters.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_characters.py`:

```python
import pytest
from pydantic import ValidationError

from sales_trainer.characters import load_character
from sales_trainer.characters.loader import Character, CharacterUnavailable

# MEMORY.md §5: start temperature / success threshold / maximum turns.
MEMORY_NUMBERS = {1: (50, 75, 10), 2: (30, 80, 10), 3: (10, 85, 8)}


@pytest.mark.parametrize("level", [1, 2, 3])
def test_the_cards_match_the_project_memory(level: int) -> None:
    character = load_character(level)
    start, threshold, max_turns = MEMORY_NUMBERS[level]
    assert character.level == level
    assert character.start_temperature == start
    assert character.threshold == threshold
    assert character.max_turns == max_turns


def test_the_three_characters_have_their_names_and_voices() -> None:
    characters = [load_character(level) for level in (1, 2, 3)]
    assert [character.name for character in characters] == ["Marta Ruiz", "Javier Soto", "Carmen Valdés"]
    assert all(character.voice for character in characters)


def test_every_prompt_file_is_loaded_as_text() -> None:
    for level in (1, 2, 3):
        character = load_character(level)
        assert len(character.prompt_text) > 800
        assert "temperatura" in character.prompt_text.lower()


def test_a_level_out_of_range_is_rejected() -> None:
    for level in (0, 4):
        with pytest.raises(CharacterUnavailable):
            load_character(level)


def test_a_card_pointing_outside_the_prompts_dir_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Character(
            level=1,
            name="Marta",
            voice="v",
            start_temperature=50,
            threshold=75,
            max_turns=10,
            prompt="../../.env",
        )


def test_max_turns_out_of_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Character(
            level=1,
            name="Marta",
            voice="v",
            start_temperature=50,
            threshold=75,
            max_turns=80,
            prompt="prompts/nivel1.md",
        )
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_characters.py -v`

Expected: FAIL — exit code 1, `ModuleNotFoundError: No module named 'sales_trainer.characters'`.

- [ ] **Step 3: Create `src/sales_trainer/characters/__init__.py`**

```python
"""Character cards: the three levels, their prompts and their numbers."""

from sales_trainer.characters.loader import Character, CharacterUnavailable, load_character

__all__ = ["Character", "CharacterUnavailable", "load_character"]
```

- [ ] **Step 4: Create `src/sales_trainer/characters/loader.py`**

```python
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

# The cards live outside the package, like .env; documented as a known limit.
CHARACTERS_DIR = Path(__file__).resolve().parents[3] / "characters"
PROMPTS_DIR = CHARACTERS_DIR / "prompts"


class CharacterUnavailable(RuntimeError):
    """Raised when a character card cannot be loaded."""


class Character(BaseModel):
    level: int = Field(ge=1, le=3)
    name: str = Field(min_length=1)
    voice: str = Field(min_length=1)
    start_temperature: int = Field(ge=0, le=100)
    threshold: int = Field(ge=0, le=100)
    max_turns: int = Field(ge=1, le=50)
    prompt: str
    prompt_text: str = ""
    objections: list[str] = Field(default_factory=list)
    hot_buttons: list[str] = Field(default_factory=list)
    cold_buttons: list[str] = Field(default_factory=list)
    filler_words: list[str] = Field(default_factory=list)

    @field_validator("prompt")
    @classmethod
    def _prompt_must_be_a_file_under_prompts(cls, value: str) -> str:
        path = (CHARACTERS_DIR / value).resolve()
        if not path.is_relative_to(PROMPTS_DIR) or not path.is_file():
            raise ValueError(f"prompt must be an existing file under characters/prompts: {value}")
        return value


def load_character(level: int) -> Character:
    if not 1 <= level <= 3:
        raise CharacterUnavailable(f"level must be 1, 2 or 3, got {level}")
    path = CHARACTERS_DIR / f"nivel{level}.yaml"
    try:
        card = Character.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        prompt_text = (CHARACTERS_DIR / card.prompt).read_text(encoding="utf-8")
    except (OSError, ValidationError, yaml.YAMLError) as error:
        raise CharacterUnavailable(f"character card nivel{level} is invalid: {error}") from error
    return card.model_copy(update={"prompt_text": prompt_text})
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_characters.py -v`

Expected: exit code 0; `8 passed` (the parametrized card test counts as three).

- [ ] **Step 6: Lint**

Run: `uv run ruff check .`

Expected: exit code 0; `All checks passed!`.

- [ ] **Step 7: Commit**

```bash
git add src/sales_trainer/characters tests/unit/test_characters.py
git commit -m "feat: validate character cards with pydantic"
```

---

## Task 4: `llm/base.py` and the mock provider

**Files:**
- Create: `src/sales_trainer/llm/base.py`
- Create: `src/sales_trainer/llm/mock.py`
- Test: `tests/unit/test_llm.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_llm.py`:

```python
from sales_trainer.llm.base import Message
from sales_trainer.llm.mock import TEMPLATE, MockLLMProvider


def test_the_mock_answers_deterministically() -> None:
    provider = MockLLMProvider()
    messages = [Message(role="user", content="Hola.")]
    assert provider.complete("sistema", messages) == TEMPLATE.format(turn=1)
    assert provider.complete("sistema", messages) == TEMPLATE.format(turn=1)


def test_the_mock_counts_user_turns() -> None:
    provider = MockLLMProvider()
    messages = [
        Message(role="user", content="Hola."),
        Message(role="assistant", content="Dime."),
        Message(role="user", content="Ahorro tiempo."),
    ]
    assert "turno 2" in provider.complete("sistema", messages)
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_llm.py -v`

Expected: FAIL — exit code 1, `ModuleNotFoundError: No module named 'sales_trainer.llm'`.

- [ ] **Step 3: Create `src/sales_trainer/llm/base.py`**

```python
from typing import Literal, Protocol

from pydantic import BaseModel

Role = Literal["user", "assistant"]


class Message(BaseModel):
    role: Role
    content: str


class LLMUnavailable(RuntimeError):
    """Raised when the configured provider cannot answer."""


class LLMProvider(Protocol):
    def complete(self, system: str, messages: list[Message]) -> str: ...
```

- [ ] **Step 4: Create `src/sales_trainer/llm/mock.py`**

```python
from sales_trainer.llm.base import Message

TEMPLATE = "Te sigo. Sobre el turno {turn}, ¿cuánto tiempo ahorraría mi equipo al día?"


class MockLLMProvider:
    """Deterministic double: one short Spanish answer per user turn, no network."""

    def complete(self, system: str, messages: list[Message]) -> str:
        turn = sum(1 for message in messages if message.role == "user")
        return TEMPLATE.format(turn=turn)
```

`TEMPLATE` holds two sentences, so every socket test knows exactly how many `audio` messages to expect from one mock reply.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_llm.py -v`

Expected: exit code 0; `2 passed`.

- [ ] **Step 6: Check that the mock never touches the network**

Run:

```bash
SALES_TRAINER_LLM=mock uv run python -c "
import sys
from sales_trainer.llm.mock import MockLLMProvider
from sales_trainer.llm.base import Message
print(MockLLMProvider().complete('s', [Message(role='user', content='hola')]))
print('httpx imported:', 'httpx' in sys.modules)
"
```

Expected: `Te sigo. Sobre el turno 1, ¿cuánto tiempo ahorraría mi equipo al día?` and `httpx imported: False`.

- [ ] **Step 7: Commit**

```bash
git add src/sales_trainer/llm/base.py src/sales_trainer/llm/mock.py tests/unit/test_llm.py
git commit -m "feat: add the llm protocol and a deterministic mock"
```

---

## Task 5: OpenAI-compatible provider

**Files:**
- Create: `src/sales_trainer/llm/openai_compat.py`
- Test: `tests/unit/test_llm.py`

- [ ] **Step 1: Replace the import block and append the failing tests**

In `tests/unit/test_llm.py`, replace the import block with:

```python
import json

import httpx
import pytest

from sales_trainer.llm.base import LLMUnavailable, Message
from sales_trainer.llm.mock import TEMPLATE, MockLLMProvider
from sales_trainer.llm.openai_compat import OpenAICompatProvider
```

Then append these tests to the end of the file:

```python
def openai_provider(handler, **kwargs) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        model="llama3.1",
        base_url="http://127.0.0.1:11434/v1",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def test_the_openai_provider_requires_a_model_and_a_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SALES_TRAINER_LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    with pytest.raises(LLMUnavailable):
        OpenAICompatProvider(model="", base_url="")
    with pytest.raises(LLMUnavailable):
        OpenAICompatProvider(model="llama3.1", base_url="")


def test_the_openai_timeout_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SALES_TRAINER_LLM_TIMEOUT", "12")
    assert openai_provider(lambda request: httpx.Response(200, json={})).timeout == 12.0


def test_the_openai_timeout_defaults_to_30_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SALES_TRAINER_LLM_TIMEOUT", raising=False)
    assert openai_provider(lambda request: httpx.Response(200, json={})).timeout == 30.0


def test_openai_sends_the_model_messages_and_key() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": " Hola. "}}]})

    provider = OpenAICompatProvider(
        model="llama3.1",
        base_url="http://127.0.0.1:11434/v1/",
        api_key="k",
        transport=httpx.MockTransport(handler),
    )
    text = provider.complete("eres Marta", [Message(role="user", content="hola")])

    assert text == "Hola."
    assert seen["url"] == "http://127.0.0.1:11434/v1/chat/completions"
    assert seen["auth"] == "Bearer k"
    assert seen["body"] == {
        "model": "llama3.1",
        "messages": [
            {"role": "system", "content": "eres Marta"},
            {"role": "user", "content": "hola"},
        ],
    }


def test_openai_works_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "Vale."}}]})

    provider = OpenAICompatProvider(
        model="llama3.1",
        base_url="http://127.0.0.1:11434/v1",
        api_key="",
        transport=httpx.MockTransport(handler),
    )
    assert provider.complete("s", [Message(role="user", content="hola")]) == "Vale."
    assert seen["auth"] is None


def test_openai_http_error_becomes_unavailable() -> None:
    provider = openai_provider(lambda request: httpx.Response(500, json={"error": "boom"}))
    with pytest.raises(LLMUnavailable):
        provider.complete("s", [Message(role="user", content="hola")])


def test_openai_timeout_becomes_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    provider = openai_provider(handler)
    with pytest.raises(LLMUnavailable):
        provider.complete("s", [Message(role="user", content="hola")])


def test_openai_bad_body_becomes_unavailable() -> None:
    provider = openai_provider(lambda request: httpx.Response(200, json={"nope": True}))
    with pytest.raises(LLMUnavailable):
        provider.complete("s", [Message(role="user", content="hola")])


def test_openai_non_json_body_becomes_unavailable() -> None:
    provider = openai_provider(lambda request: httpx.Response(200, text="<html>"))
    with pytest.raises(LLMUnavailable):
        provider.complete("s", [Message(role="user", content="hola")])
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_llm.py -v`

Expected: FAIL — exit code 1, `ModuleNotFoundError: No module named 'sales_trainer.llm.openai_compat'`.

- [ ] **Step 3: Create `src/sales_trainer/llm/openai_compat.py`**

```python
import os

import httpx

from sales_trainer.llm.base import LLMUnavailable, Message

DEFAULT_TIMEOUT = 30.0


def timeout_seconds() -> float:
    return float(os.environ.get("SALES_TRAINER_LLM_TIMEOUT", str(DEFAULT_TIMEOUT)))


class OpenAICompatProvider:
    """Covers Ollama, LM Studio, DeepSeek and OpenAI: only the URL and model change."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float | None = None,
    ) -> None:
        self._model = model or os.environ.get("SALES_TRAINER_LLM_MODEL", "")
        self._base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "")).rstrip("/")
        self._api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        if not self._model:
            raise LLMUnavailable("SALES_TRAINER_LLM_MODEL is required")
        if not self._base_url:
            raise LLMUnavailable("OPENAI_BASE_URL is required")
        self.timeout = timeout if timeout is not None else timeout_seconds()
        self._client = httpx.Client(transport=transport, timeout=self.timeout)

    def complete(self, system: str, messages: list[Message]) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, *[message.model_dump() for message in messages]],
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = self._client.post(f"{self._base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            raise LLMUnavailable(f"openai-compatible completion failed: {error}") from error
        if not isinstance(content, str) or not content.strip():
            raise LLMUnavailable("openai-compatible completion returned no text")
        return content.strip()
```

`httpx.HTTPError` covers timeouts and non-2xx responses; `ValueError` covers a body that is not JSON; `KeyError`/`IndexError`/`TypeError` cover a JSON body of the wrong shape. No blind `except Exception`, so `BLE001` stays clean.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_llm.py -v`

Expected: exit code 0; `11 passed` (2 from Task 4 plus 9 here).

- [ ] **Step 5: Lint**

Run: `uv run ruff check .`

Expected: exit code 0; `All checks passed!`.

- [ ] **Step 6: Commit**

```bash
git add src/sales_trainer/llm/openai_compat.py tests/unit/test_llm.py
git commit -m "feat: add the openai-compatible llm provider"
```

---

## Task 6: Anthropic provider

**Files:**
- Create: `src/sales_trainer/llm/anthropic.py`
- Test: `tests/unit/test_llm.py`

- [ ] **Step 1: Replace the import block and append the failing tests**

In `tests/unit/test_llm.py`, replace the import block with:

```python
import json

import httpx
import pytest

from sales_trainer.llm.anthropic import AnthropicProvider
from sales_trainer.llm.base import LLMUnavailable, Message
from sales_trainer.llm.mock import TEMPLATE, MockLLMProvider
from sales_trainer.llm.openai_compat import OpenAICompatProvider
```

Then append these tests to the end of the file:

```python
def anthropic_provider(handler, **kwargs) -> AnthropicProvider:
    return AnthropicProvider(
        model="test-model",
        api_key="k",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def test_the_anthropic_provider_requires_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMUnavailable):
        AnthropicProvider(model="test-model", api_key="")


def test_anthropic_sends_the_system_and_the_messages() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-api-key")
        seen["version"] = request.headers.get("anthropic-version")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": " Hola. "}]})

    provider = anthropic_provider(handler)
    text = provider.complete("eres Marta", [Message(role="user", content="hola")])

    assert text == "Hola."
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["key"] == "k"
    assert seen["version"] == "2023-06-01"
    assert seen["body"] == {
        "model": "test-model",
        "max_tokens": 300,
        "system": "eres Marta",
        "messages": [{"role": "user", "content": "hola"}],
    }


def test_anthropic_http_error_becomes_unavailable() -> None:
    provider = anthropic_provider(lambda request: httpx.Response(500, json={"error": "boom"}))
    with pytest.raises(LLMUnavailable):
        provider.complete("s", [Message(role="user", content="hola")])


def test_anthropic_bad_body_becomes_unavailable() -> None:
    provider = anthropic_provider(lambda request: httpx.Response(200, json={"nope": True}))
    with pytest.raises(LLMUnavailable):
        provider.complete("s", [Message(role="user", content="hola")])


def test_anthropic_without_a_text_block_becomes_unavailable() -> None:
    provider = anthropic_provider(lambda request: httpx.Response(200, json={"content": []}))
    with pytest.raises(LLMUnavailable):
        provider.complete("s", [Message(role="user", content="hola")])
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_llm.py -v`

Expected: FAIL — exit code 1, `ModuleNotFoundError: No module named 'sales_trainer.llm.anthropic'`.

- [ ] **Step 3: Create `src/sales_trainer/llm/anthropic.py`**

```python
import os

import httpx

from sales_trainer.llm.base import LLMUnavailable, Message

ENDPOINT = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
# The prompts cap answers at 1-3 short sentences, so 300 tokens is generous.
MAX_TOKENS = 300
DEFAULT_TIMEOUT = 30.0


def timeout_seconds() -> float:
    return float(os.environ.get("SALES_TRAINER_LLM_TIMEOUT", str(DEFAULT_TIMEOUT)))


class AnthropicProvider:
    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float | None = None,
    ) -> None:
        self._model = model or os.environ.get("SALES_TRAINER_LLM_MODEL", "")
        self._api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        if not self._model:
            raise LLMUnavailable("SALES_TRAINER_LLM_MODEL is required")
        if not self._api_key:
            raise LLMUnavailable("ANTHROPIC_API_KEY is required")
        self.timeout = timeout if timeout is not None else timeout_seconds()
        self._client = httpx.Client(transport=transport, timeout=self.timeout)

    def complete(self, system: str, messages: list[Message]) -> str:
        payload = {
            "model": self._model,
            "max_tokens": MAX_TOKENS,
            "system": system,
            "messages": [message.model_dump() for message in messages],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        try:
            response = self._client.post(ENDPOINT, json=payload, headers=headers)
            response.raise_for_status()
            content = response.json()["content"][0]["text"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            raise LLMUnavailable(f"anthropic completion failed: {error}") from error
        if not isinstance(content, str) or not content.strip():
            raise LLMUnavailable("anthropic completion returned no text")
        return content.strip()
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_llm.py -v`

Expected: exit code 0; `16 passed` (11 after Task 5 plus 5 here).

- [ ] **Step 5: Commit**

```bash
git add src/sales_trainer/llm/anthropic.py tests/unit/test_llm.py
git commit -m "feat: add the anthropic llm provider"
```

---

## Task 7: LLM factory

**Files:**
- Create: `src/sales_trainer/llm/__init__.py`
- Test: `tests/unit/test_llm.py`

- [ ] **Step 1: Replace the import block and append the failing tests**

In `tests/unit/test_llm.py`, replace the import block with:

```python
import json

import httpx
import pytest

from sales_trainer.llm import get_llm_provider, provider_name
from sales_trainer.llm.anthropic import AnthropicProvider
from sales_trainer.llm.base import LLMUnavailable, Message
from sales_trainer.llm.mock import TEMPLATE, MockLLMProvider
from sales_trainer.llm.openai_compat import OpenAICompatProvider
```

Then append these tests to the end of the file:

```python
def test_the_default_provider_name_is_openai_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SALES_TRAINER_LLM", raising=False)
    assert provider_name() == "openai-compatible"


def test_mock_is_selected_by_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SALES_TRAINER_LLM", "mock")
    assert isinstance(get_llm_provider(), MockLLMProvider)


def test_anthropic_is_selected_by_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SALES_TRAINER_LLM", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("SALES_TRAINER_LLM_MODEL", "test-model")
    assert isinstance(get_llm_provider(), AnthropicProvider)


def test_an_unknown_llm_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SALES_TRAINER_LLM", "carrier-pigeon")
    with pytest.raises(LLMUnavailable):
        get_llm_provider()


def test_a_provider_that_cannot_be_built_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SALES_TRAINER_LLM", "openai-compatible")
    monkeypatch.delenv("SALES_TRAINER_LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    with pytest.raises(LLMUnavailable):
        get_llm_provider()
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_llm.py -v`

Expected: FAIL — exit code 1, `ImportError: cannot import name 'get_llm_provider' from 'sales_trainer.llm'`.

- [ ] **Step 3: Create `src/sales_trainer/llm/__init__.py`**

```python
"""LLM providers: openai-compatible (default), anthropic and mock."""

import os

from sales_trainer.llm.base import LLMProvider, LLMUnavailable, Message

__all__ = ["LLMProvider", "LLMUnavailable", "Message", "get_llm_provider", "provider_name"]

DEFAULT_PROVIDER = "openai-compatible"


def provider_name() -> str:
    return os.environ.get("SALES_TRAINER_LLM", DEFAULT_PROVIDER).strip().lower()


def get_llm_provider() -> LLMProvider:
    name = provider_name()
    if name == "mock":
        from sales_trainer.llm.mock import MockLLMProvider

        return MockLLMProvider()
    if name == "openai-compatible":
        from sales_trainer.llm.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider()
    if name == "anthropic":
        from sales_trainer.llm.anthropic import AnthropicProvider

        return AnthropicProvider()
    raise LLMUnavailable(f"unknown SALES_TRAINER_LLM value: {name}")
```

The imports are lazy for the same reason `voice/stt` does it: the mock path must never import an HTTP client.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_llm.py -v`

Expected: exit code 0; `21 passed` (16 after Task 6 plus 5 here).

- [ ] **Step 5: Confirm the mock path imports no HTTP client**

Run:

```bash
SALES_TRAINER_LLM=mock uv run python -c "
import sys
from sales_trainer.llm import get_llm_provider
print(type(get_llm_provider()).__name__)
print('httpx imported:', 'httpx' in sys.modules)
print('openai_compat imported:', 'sales_trainer.llm.openai_compat' in sys.modules)
print('anthropic imported:', 'sales_trainer.llm.anthropic' in sys.modules)
"
```

Expected: `MockLLMProvider`, `httpx imported: False`, `openai_compat imported: False`, `anthropic imported: False`.

- [ ] **Step 6: Lint and commit**

Run: `uv run ruff check .`

Expected: exit code 0; `All checks passed!`.

```bash
git add src/sales_trainer/llm/__init__.py tests/unit/test_llm.py
git commit -m "feat: add the llm provider factory"
```

---

## Task 8: `chat.split_sentences` — the Spanish splitter

**Files:**
- Create: `src/sales_trainer/chat.py`
- Test: `tests/unit/test_chat.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_chat.py`:

```python
from sales_trainer.chat import split_sentences


def test_a_plain_sentence_is_one_piece() -> None:
    assert split_sentences("Hola, soy Marta.") == ["Hola, soy Marta."]


def test_two_sentences_split_after_the_period() -> None:
    assert split_sentences("Hola. ¿Qué tal?") == ["Hola.", "¿Qué tal?"]


def test_question_and_exclamation_marks_keep_their_openers() -> None:
    assert split_sentences("¡Vaya! ¿En serio? Claro.") == ["¡Vaya!", "¿En serio?", "Claro."]


def test_an_ellipsis_is_one_ending() -> None:
    assert split_sentences("No sé… Puede ser. Y ya.") == ["No sé…", "Puede ser.", "Y ya."]


def test_decimals_and_thousands_do_not_split() -> None:
    assert split_sentences("Ahorra un 3,5 % y cuesta 1.200 euros.") == ["Ahorra un 3,5 % y cuesta 1.200 euros."]


def test_the_fixed_abbreviations_do_not_split() -> None:
    text = (
        "El Sr. García habló con la Sra. López. "
        "El Dr. Ruiz llegó, y Ud. y Uds. lo vieron. "
        "Por ejemplo p. ej. esto, y las EE. UU. también."
    )
    assert split_sentences(text) == [
        "El Sr. García habló con la Sra. López.",
        "El Dr. Ruiz llegó, y Ud. y Uds. lo vieron.",
        "Por ejemplo p. ej. esto, y las EE. UU. también.",
    ]


def test_empty_text_has_no_sentences() -> None:
    assert split_sentences("") == []
    assert split_sentences("   ") == []
    assert split_sentences("Sin punto final") == ["Sin punto final"]
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_chat.py -v`

Expected: FAIL — exit code 1, `ModuleNotFoundError: No module named 'sales_trainer.chat'`.

- [ ] **Step 3: Create `src/sales_trainer/chat.py`**

```python
SENTENCE_ENDINGS = ".!?…"
ABBREVIATIONS = ("Sr.", "Sra.", "Dr.", "Ud.", "Uds.", "p. ej.", "EE. UU.")


def _inside_abbreviation(text: str, start: int, end: int) -> bool:
    """A boundary that closes or falls inside an abbreviation is not a sentence end.

    Merging two sentences costs one longer TTS call; splitting "EE. UU." is heard at once.
    """
    for abbreviation in ABBREVIATIONS:
        if end - start >= len(abbreviation) and text[end - len(abbreviation) : end] == abbreviation:
            return True
        for offset in range(max(start, end - len(abbreviation)), end):
            if text[offset:end] == abbreviation[: end - offset]:
                return True
    return False


def split_sentences(text: str) -> list[str]:
    """Cut Spanish text after . ! ? … without breaking decimals, thousands or abbreviations."""
    sentences: list[str] = []
    start = 0
    index = 0
    while index < len(text):
        if text[index] not in SENTENCE_ENDINGS:
            index += 1
            continue
        end = index + 1
        while end < len(text) and text[end] in SENTENCE_ENDINGS:
            end += 1
        index = end
        if end < len(text) and not text[end].isspace():
            continue  # a decimal or a thousands separator, not an ending
        if _inside_abbreviation(text, start, end):
            continue
        candidate = text[start:end].strip()
        if candidate:
            sentences.append(candidate)
        start = end
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_chat.py -v`

Expected: exit code 0; `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/sales_trainer/chat.py tests/unit/test_chat.py
git commit -m "feat: split spanish replies into sentences for tts"
```

---

## Task 9: `chat.py` — exchange, conversation, `begin`, `reply`, `done_reason`

**Files:**
- Modify: `src/sales_trainer/chat.py` (replaced whole)
- Test: `tests/unit/test_chat.py`

- [ ] **Step 1: Replace the import-free file header and append the failing tests**

In `tests/unit/test_chat.py`, replace the first line (`from sales_trainer.chat import split_sentences`) with:

```python
import pytest

from sales_trainer.characters import load_character
from sales_trainer.chat import (
    DEMO_PRODUCT,
    Conversation,
    ConversationStore,
    begin,
    build_system,
    done_reason,
    reply,
    split_sentences,
)
from sales_trainer.llm.base import LLMUnavailable
from sales_trainer.llm.mock import MockLLMProvider
from sales_trainer.voice.stt.base import Word
```

Then append these tests to the end of the file:

```python
def conversation(max_turns: int = 10) -> Conversation:
    card = load_character(1).model_copy(update={"max_turns": max_turns})
    return Conversation(session="s", character=card, product_brief=DEMO_PRODUCT)


def test_begin_appends_the_exchange_and_counts_the_turn() -> None:
    chat = conversation()
    words = [Word(word="hola", start_ms=0, end_ms=100, probability=0.9)]
    exchange = begin(chat, "Hola.", words, 320)
    assert exchange.index == 0
    assert chat.turns == 1
    assert chat.exchanges == [exchange]
    assert exchange.words == words
    assert exchange.audio_ms == 320
    assert begin(chat, "Otra.", [], 320).index == 1


def test_reply_stores_the_answer_and_a_second_turn_changes_it() -> None:
    chat = conversation()
    provider = MockLLMProvider()
    first = begin(chat, "Hola.", [], 320)
    text = reply(chat, first, provider)
    assert first.reply == text
    second = begin(chat, "Ahorro dos horas al día.", [], 320)
    assert reply(chat, second, provider) != text


def test_reply_replays_the_previous_exchanges() -> None:
    class Recorder:
        def __init__(self) -> None:
            self.calls: list[tuple[str, list]] = []

        def complete(self, system: str, messages: list) -> str:
            self.calls.append((system, list(messages)))
            return "Vale."

    chat = conversation()
    recorder = Recorder()
    reply(chat, begin(chat, "Hola.", [], 320), recorder)
    reply(chat, begin(chat, "Más.", [], 320), recorder)

    system, messages = recorder.calls[1]
    assert [message.role for message in messages] == ["user", "assistant", "user"]
    assert [message.content for message in messages] == ["Hola.", "Vale.", "Más."]
    assert "Producto" in system


def test_reply_rejects_an_empty_answer() -> None:
    class Empty:
        def complete(self, system: str, messages: list) -> str:
            return "   "

    chat = conversation()
    with pytest.raises(LLMUnavailable):
        reply(chat, begin(chat, "Hola.", [], 320), Empty())


def test_done_reason_is_turns_at_the_limit() -> None:
    chat = conversation(max_turns=2)
    assert done_reason(chat) is None
    begin(chat, "uno", [], 320)
    assert done_reason(chat) is None
    begin(chat, "dos", [], 320)
    assert done_reason(chat) == "turns"


def test_build_system_carries_the_prompt_the_product_and_the_card() -> None:
    card = load_character(2)
    system = build_system(card, "Rutas más cortas.")
    assert "Javier Soto" in system
    assert "Rutas más cortas." in system
    assert card.objections[0] in system
    assert card.hot_buttons[0] in system
    assert card.prompt_text.splitlines()[0] in system
    assert "temperatura inicial 30" not in system.lower()


def test_the_store_starts_fresh_for_the_same_token() -> None:
    store = ConversationStore()
    card = load_character(1)
    first = store.start("t", card, "p")
    begin(first, "Hola.", [], 320)
    second = store.start("t", card, "p")
    assert second is not first
    assert second.turns == 0
    assert second.exchanges == []
    assert store.get("t") is second
    assert store.get("missing") is None
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_chat.py -v`

Expected: FAIL — exit code 1, `ImportError: cannot import name 'DEMO_PRODUCT' from 'sales_trainer.chat'`.

- [ ] **Step 3: Replace `src/sales_trainer/chat.py` with the complete file**

```python
from dataclasses import dataclass, field

from sales_trainer.characters.loader import Character
from sales_trainer.llm.base import LLMProvider, LLMUnavailable, Message
from sales_trainer.voice.stt.base import Word

DEMO_PRODUCT = (
    "Software de gestión de rutas para empresas de reparto: reduce el tiempo de planificación "
    "de cada ruta un 30 % y cuesta 12 euros por conductor al mes."
)

SENTENCE_ENDINGS = ".!?…"
ABBREVIATIONS = ("Sr.", "Sra.", "Dr.", "Ud.", "Uds.", "p. ej.", "EE. UU.")


@dataclass
class Exchange:
    index: int
    user_text: str
    words: list[Word] = field(default_factory=list)
    audio_ms: int = 0
    reply: str = ""
    interrupted: bool = False


@dataclass
class Conversation:
    session: str
    character: Character
    product_brief: str
    exchanges: list[Exchange] = field(default_factory=list)
    turns: int = 0


class ConversationStore:
    """In-memory conversations per session token; connecting again starts a fresh one."""

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}

    def start(self, session: str, character: Character, product_brief: str) -> Conversation:
        conversation = Conversation(session=session, character=character, product_brief=product_brief)
        self._conversations[session] = conversation
        return conversation

    def get(self, session: str) -> Conversation | None:
        return self._conversations.get(session)


_STORE = ConversationStore()


def get_conversation_store() -> ConversationStore:
    return _STORE


def build_system(character: Character, product_brief: str) -> str:
    card = "\n".join(
        [
            f"## Tu personaje: {character.name} (nivel {character.level})",
            f"Objeciones que puedes plantear: {'; '.join(character.objections)}",
            f"Temas que te interesan: {'; '.join(character.hot_buttons)}",
            f"Temas que te enfrian: {'; '.join(character.cold_buttons)}",
            f"Muletillas que puedes usar: {'; '.join(character.filler_words)}",
        ]
    )
    product = f"## Producto que te está vendiendo el vendedor\n{product_brief.strip()}"
    return f"{character.prompt_text.strip()}\n\n{card}\n\n{product}"


def _inside_abbreviation(text: str, start: int, end: int) -> bool:
    """A boundary that closes or falls inside an abbreviation is not a sentence end.

    Merging two sentences costs one longer TTS call; splitting "EE. UU." is heard at once.
    """
    for abbreviation in ABBREVIATIONS:
        if end - start >= len(abbreviation) and text[end - len(abbreviation) : end] == abbreviation:
            return True
        for offset in range(max(start, end - len(abbreviation)), end):
            if text[offset:end] == abbreviation[: end - offset]:
                return True
    return False


def split_sentences(text: str) -> list[str]:
    """Cut Spanish text after . ! ? … without breaking decimals, thousands or abbreviations."""
    sentences: list[str] = []
    start = 0
    index = 0
    while index < len(text):
        if text[index] not in SENTENCE_ENDINGS:
            index += 1
            continue
        end = index + 1
        while end < len(text) and text[end] in SENTENCE_ENDINGS:
            end += 1
        index = end
        if end < len(text) and not text[end].isspace():
            continue  # a decimal or a thousands separator, not an ending
        if _inside_abbreviation(text, start, end):
            continue
        candidate = text[start:end].strip()
        if candidate:
            sentences.append(candidate)
        start = end
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def begin(conversation: Conversation, text: str, words: list[Word], audio_ms: int) -> Exchange:
    exchange = Exchange(index=len(conversation.exchanges), user_text=text, words=words, audio_ms=audio_ms)
    conversation.exchanges.append(exchange)
    # Counted before the provider is awaited so a barge-in always has a turn to mark.
    conversation.turns += 1
    return exchange


def reply(conversation: Conversation, exchange: Exchange, provider: LLMProvider) -> str:
    messages: list[Message] = []
    for previous in conversation.exchanges:
        messages.append(Message(role="user", content=previous.user_text))
        if previous.reply:
            messages.append(Message(role="assistant", content=previous.reply))
    text = provider.complete(build_system(conversation.character, conversation.product_brief), messages).strip()
    if not text:
        raise LLMUnavailable("the provider returned an empty reply")
    exchange.reply = text
    return text


def done_reason(conversation: Conversation) -> str | None:
    return "turns" if conversation.turns >= conversation.character.max_turns else None
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_chat.py -v`

Expected: exit code 0; `14 passed` (7 from Task 8 plus 7 here).

- [ ] **Step 5: Lint**

Run: `uv run ruff check .`

Expected: exit code 0; `All checks passed!`.

- [ ] **Step 6: Commit**

```bash
git add src/sales_trainer/chat.py tests/unit/test_chat.py
git commit -m "feat: add the conversation, its exchanges and the turn limit"
```

---

## Task 10: `/ws/chat` handshake — Origin, token, level, character, `ready`

**Files:**
- Create: `src/sales_trainer/web/routes/chat_ws.py`
- Modify: `src/sales_trainer/web/app.py`
- Test: `tests/unit/test_chat_ws.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_chat_ws.py`:

```python
import uuid

import pytest
from fastapi.testclient import TestClient

from sales_trainer.web import sessions
from sales_trainer.web.app import app

client = TestClient(app)
ORIGIN = "http://127.0.0.1:8765"
CHUNK = b"\x00\x00" * 512
SPEECH = [0.9] * 8
SILENCE = [0.1] * 22


@pytest.fixture
def session_token() -> str:
    token = f"chat-{uuid.uuid4()}"
    sessions.register(token)
    return token


class ScriptedVAD:
    def __init__(self, script: list[float]) -> None:
        self._script = list(script)

    def probability(self, chunk: bytes) -> float:
        return self._script.pop(0) if self._script else 0.0


def connect_url(token: str, level: str = "1") -> str:
    return f"/ws/chat?session={token}&level={level}"


def test_a_foreign_origin_is_rejected() -> None:
    token = f"chat-{uuid.uuid4()}"
    sessions.register(token)
    with client.websocket_connect(connect_url(token), headers={"origin": "http://evil.example"}) as socket:
        payload = socket.receive_json()
    assert payload["type"] == "error"
    assert payload["code"] == "origin"


def test_a_missing_origin_is_rejected(session_token: str) -> None:
    with client.websocket_connect(connect_url(session_token), headers={}) as socket:
        payload = socket.receive_json()
    assert payload["code"] == "origin"


def test_an_unknown_token_is_rejected() -> None:
    with client.websocket_connect(connect_url(f"nope-{uuid.uuid4()}"), headers={"origin": ORIGIN}) as socket:
        payload = socket.receive_json()
    assert payload["type"] == "error"
    assert payload["code"] == "session"


def test_a_missing_level_is_rejected(session_token: str) -> None:
    with client.websocket_connect(f"/ws/chat?session={session_token}", headers={"origin": ORIGIN}) as socket:
        payload = socket.receive_json()
    assert payload["type"] == "error"
    assert payload["code"] == "level"


def test_an_out_of_range_level_is_rejected(session_token: str) -> None:
    with client.websocket_connect(connect_url(session_token, "9"), headers={"origin": ORIGIN}) as socket:
        payload = socket.receive_json()
    assert payload["code"] == "level"


def test_ready_carries_the_character_and_zero_turns(session_token: str) -> None:
    with client.websocket_connect(connect_url(session_token, "2"), headers={"origin": ORIGIN}) as socket:
        payload = socket.receive_json()
    assert payload["type"] == "ready"
    assert payload["turns"] == 0
    assert payload["character"] == {
        "name": "Javier Soto",
        "level": 2,
        "max_turns": 10,
        "voice": "es-ES-AlvaroNeural",
    }
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_chat_ws.py -v`

Expected: FAIL — exit code 1; `websocket_connect` raises because `/ws/chat` does not exist (403 handshake).

- [ ] **Step 3: Create `src/sales_trainer/web/routes/chat_ws.py`**

```python
import os

from fastapi import APIRouter, WebSocket

from sales_trainer.characters.loader import CharacterUnavailable, load_character
from sales_trainer.chat import DEMO_PRODUCT, get_conversation_store
from sales_trainer.web.sessions import is_known

router = APIRouter()

POLICY_VIOLATION = 1008
MIN_LEVEL = 1
MAX_LEVEL = 3


def allowed_origins() -> set[str]:
    port = os.environ.get("SALES_TRAINER_PORT", "8765")
    return {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}


async def _reject(websocket: WebSocket, code: str, message: str) -> None:
    await websocket.send_json({"type": "error", "code": code, "message": message})
    await websocket.close(code=POLICY_VIOLATION)


@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket, session: str = "", level: str = "", product: str = "") -> None:
    await websocket.accept()
    origin = websocket.headers.get("origin", "")
    if origin not in allowed_origins():
        await _reject(websocket, "origin", f"origin not allowed: {origin or '(missing)'}")
        return
    if not is_known(session):
        await _reject(websocket, "session", "unknown session token")
        return
    try:
        level_number = int(level)
    except ValueError:
        await _reject(websocket, "level", f"level must be 1, 2 or 3, got {level or '(missing)'}")
        return
    if not MIN_LEVEL <= level_number <= MAX_LEVEL:
        await _reject(websocket, "level", f"level must be 1, 2 or 3, got {level_number}")
        return
    try:
        character = load_character(level_number)
    except CharacterUnavailable as error:
        # A broken card means "this level is not available" to the client.
        await _reject(websocket, "level", str(error))
        return

    conversation = get_conversation_store().start(session, character, product.strip() or DEMO_PRODUCT)
    await websocket.send_json(
        {
            "type": "ready",
            "character": {
                "name": character.name,
                "level": character.level,
                "max_turns": character.max_turns,
                "voice": character.voice,
            },
            "turns": conversation.turns,
        }
    )

    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
```

- [ ] **Step 4: Mount the router in `src/sales_trainer/web/app.py`**

Change the import block from:

```python
from sales_trainer.web.routes import stt as stt_routes
from sales_trainer.web.routes import stt_ws as stt_ws_routes
from sales_trainer.web.routes import tts as tts_routes
from sales_trainer.web.sessions import register
```

to:

```python
from sales_trainer.web.routes import chat_ws as chat_ws_routes
from sales_trainer.web.routes import stt as stt_routes
from sales_trainer.web.routes import stt_ws as stt_ws_routes
from sales_trainer.web.routes import tts as tts_routes
from sales_trainer.web.sessions import register
```

And after `app.include_router(stt_ws_routes.router)` add:

```python
app.include_router(chat_ws_routes.router)
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_chat_ws.py -v`

Expected: exit code 0; `6 passed`.

- [ ] **Step 6: Lint**

Run: `uv run ruff check .`

Expected: exit code 0; `All checks passed!`.

- [ ] **Step 7: Commit**

```bash
git add src/sales_trainer/web/routes/chat_ws.py src/sales_trainer/web/app.py tests/unit/test_chat_ws.py
git commit -m "feat: add the chat websocket handshake"
```

---

## Task 11: `/ws/chat` turn loop — VAD, turn boundaries, transcript

**Files:**
- Modify: `src/sales_trainer/web/routes/chat_ws.py`
- Test: `tests/unit/test_chat_ws.py`

- [ ] **Step 1: Append the shared fixture and the failing tests**

Append to `tests/unit/test_chat_ws.py`:

```python
@pytest.fixture
def mock_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SALES_TRAINER_LLM", "mock")
    monkeypatch.setenv("SALES_TRAINER_STT", "mock")
    monkeypatch.setenv("SALES_TRAINER_TTS", "mock")


def read_until(socket, kind: str) -> list[dict]:
    messages: list[dict] = []
    while True:
        message = socket.receive_json()
        messages.append(message)
        if message["type"] == kind:
            return messages


def send_turn(socket, sample: bytes = CHUNK) -> None:
    for _ in range(len(SPEECH) + len(SILENCE)):
        socket.send_bytes(sample)


def test_an_unusable_stt_becomes_stt(
    session_token: str, mock_providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SALES_TRAINER_STT", "azure")
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    with client.websocket_connect(connect_url(session_token), headers={"origin": ORIGIN}) as socket:
        payload = socket.receive_json()
    assert payload["type"] == "error"
    assert payload["code"] == "stt"


def test_one_voice_turn_is_transcribed(
    session_token: str, mock_providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(chat_ws, "_make_vad", lambda: ScriptedVAD(SPEECH + SILENCE))
    with client.websocket_connect(connect_url(session_token), headers={"origin": ORIGIN}) as socket:
        assert socket.receive_json()["type"] == "ready"
        send_turn(socket)
        messages = read_until(socket, "transcript")

    types = [message["type"] for message in messages]
    assert types == ["turn_start", "turn_end", "transcript"]
    transcript = messages[-1]
    assert transcript["text"]
    assert transcript["language"] == "es"
    assert transcript["words"]
    conversation = get_conversation_store().get(session_token)
    assert conversation.turns == 1
    assert conversation.exchanges[0].user_text == transcript["text"]
    assert conversation.exchanges[0].audio_ms == 960


def test_a_blip_counts_no_turn(
    session_token: str, mock_providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(chat_ws, "_make_vad", lambda: ScriptedVAD([0.9] * 2 + SILENCE))
    with client.websocket_connect(connect_url(session_token), headers={"origin": ORIGIN}) as socket:
        assert socket.receive_json()["type"] == "ready"
        for _ in range(2 + len(SILENCE)):
            socket.send_bytes(CHUNK)
        read_until(socket, "turn_end")

    conversation = get_conversation_store().get(session_token)
    assert conversation.turns == 0
    assert conversation.exchanges == []
```

Then add the module import to the import block: change

```python
from sales_trainer.web import sessions
from sales_trainer.web.app import app
```

to

```python
from sales_trainer.chat import get_conversation_store
from sales_trainer.web import sessions
from sales_trainer.web.app import app
from sales_trainer.web.routes import chat_ws
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_chat_ws.py -v`

Expected: FAIL — exit code 1; `test_one_voice_turn_is_transcribed` blocks on `turn_start` because the socket still only sends `ready`.

- [ ] **Step 3: Replace the imports and the handler in `src/sales_trainer/web/routes/chat_ws.py`**

Replace the import block with:

```python
import asyncio
import os

from fastapi import APIRouter, WebSocket

from sales_trainer.characters.loader import CharacterUnavailable, load_character
from sales_trainer.chat import DEMO_PRODUCT, begin, get_conversation_store
from sales_trainer.voice.stt import get_stt_provider
from sales_trainer.voice.stt.base import STTUnavailable
from sales_trainer.voice.turns import CHUNK_MS, SILENCE_MS, TurnDetector
from sales_trainer.voice.vad import CHUNK_BYTES, SileroVAD
from sales_trainer.web.sessions import is_known
```

Add the VAD factory after `allowed_origins`:

```python
def _make_vad() -> SileroVAD:
    return SileroVAD()
```

Then replace everything from `@router.websocket("/ws/chat")` to the end of the file with:

```python
@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket, session: str = "", level: str = "", product: str = "") -> None:
    await websocket.accept()
    origin = websocket.headers.get("origin", "")
    if origin not in allowed_origins():
        await _reject(websocket, "origin", f"origin not allowed: {origin or '(missing)'}")
        return
    if not is_known(session):
        await _reject(websocket, "session", "unknown session token")
        return
    try:
        level_number = int(level)
    except ValueError:
        await _reject(websocket, "level", f"level must be 1, 2 or 3, got {level or '(missing)'}")
        return
    if not MIN_LEVEL <= level_number <= MAX_LEVEL:
        await _reject(websocket, "level", f"level must be 1, 2 or 3, got {level_number}")
        return
    try:
        character = load_character(level_number)
    except CharacterUnavailable as error:
        # A broken card means "this level is not available" to the client.
        await _reject(websocket, "level", str(error))
        return
    try:
        stt = get_stt_provider()
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
    conversation = get_conversation_store().start(session, character, product.strip() or DEMO_PRODUCT)
    await websocket.send_json(
        {
            "type": "ready",
            "character": {
                "name": character.name,
                "level": character.level,
                "max_turns": character.max_turns,
                "voice": character.voice,
            },
            "turns": conversation.turns,
        }
    )

    elapsed_ms = 0
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        chunk = message.get("bytes")
        if chunk is None or len(chunk) != CHUNK_BYTES:
            continue

        elapsed_ms += CHUNK_MS
        probability = vad.probability(chunk)
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
            # Whisper and Azure block for seconds; a worker thread keeps the loop receiving.
            result = await asyncio.to_thread(stt.transcribe, turn.audio)
        except STTUnavailable as error:
            await websocket.send_json({"type": "error", "code": "stt", "message": str(error)})
            continue

        await websocket.send_json(
            {
                "type": "transcript",
                "text": result.text,
                "language": result.language,
                "words": [word.model_dump() for word in result.words],
            }
        )
        begin(conversation, result.text, result.words, turn.audio_ms)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_chat_ws.py -v`

Expected: exit code 0; `9 passed` (6 from Task 10 plus 3 here).

- [ ] **Step 5: Commit**

```bash
git add src/sales_trainer/web/routes/chat_ws.py tests/unit/test_chat_ws.py
git commit -m "feat: transcribe chat turns over the chat socket"
```

---

## Task 12: One reply per turn — provider call, sentence split, one `audio` per sentence

**Files:**
- Modify: `src/sales_trainer/web/routes/chat_ws.py`
- Test: `tests/unit/test_chat_ws.py`

- [ ] **Step 1: Add the imports and append the failing tests**

In `tests/unit/test_chat_ws.py`, change the import block from:

```python
from sales_trainer.chat import get_conversation_store
from sales_trainer.web import sessions
from sales_trainer.web.app import app
from sales_trainer.web.routes import chat_ws
```

to:

```python
from sales_trainer.characters import load_character
from sales_trainer.chat import get_conversation_store
from sales_trainer.llm.base import LLMUnavailable
from sales_trainer.llm.mock import TEMPLATE
from sales_trainer.web import sessions
from sales_trainer.web.app import app
from sales_trainer.web.routes import chat_ws
```

Then append these tests to the end of the file:

```python
def test_an_unusable_llm_becomes_llm_config(
    session_token: str, mock_providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SALES_TRAINER_LLM", "carrier-pigeon")
    with client.websocket_connect(connect_url(session_token), headers={"origin": ORIGIN}) as socket:
        payload = socket.receive_json()
    assert payload["type"] == "error"
    assert payload["code"] == "llm_config"


def test_an_unusable_tts_becomes_tts(
    session_token: str, mock_providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SALES_TRAINER_TTS", "azure")
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    with client.websocket_connect(connect_url(session_token), headers={"origin": ORIGIN}) as socket:
        payload = socket.receive_json()
    assert payload["type"] == "error"
    assert payload["code"] == "tts"


def test_one_turn_produces_one_reply_and_one_audio_per_sentence(
    session_token: str, mock_providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(chat_ws, "_make_vad", lambda: ScriptedVAD(SPEECH + SILENCE))
    with client.websocket_connect(connect_url(session_token), headers={"origin": ORIGIN}) as socket:
        assert socket.receive_json()["type"] == "ready"
        send_turn(socket)
        first_audio = read_until(socket, "audio")
        second_audio = read_until(socket, "audio")

    assert [message["type"] for message in first_audio] == [
        "turn_start",
        "turn_end",
        "transcript",
        "reply",
        "audio",
    ]
    reply_message = first_audio[-2]
    assert reply_message["exchange"] == 0
    assert reply_message["text"] == TEMPLATE.format(turn=1)
    assert reply_message["sentences"] == ["Te sigo.", "Sobre el turno 1, ¿cuánto tiempo ahorraría mi equipo al día?"]
    audio = first_audio[-1]
    assert audio["exchange"] == 0
    assert audio["index"] == 0
    assert audio["mime"] == "audio/wav"
    assert audio["audio_base64"]
    assert audio["visemes"]
    assert [message["type"] for message in second_audio] == ["audio"]
    assert second_audio[-1]["exchange"] == 0
    assert second_audio[-1]["index"] == 1


def test_the_conversation_ends_after_max_turns(
    session_token: str, mock_providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    short = load_character(1).model_copy(update={"max_turns": 2})
    monkeypatch.setattr(chat_ws, "load_character", lambda level: short)
    monkeypatch.setattr(chat_ws, "_make_vad", lambda: ScriptedVAD((SPEECH + SILENCE) * 2))

    with client.websocket_connect(connect_url(session_token), headers={"origin": ORIGIN}) as socket:
        assert socket.receive_json()["type"] == "ready"
        send_turn(socket)
        read_until(socket, "audio")
        read_until(socket, "audio")
        send_turn(socket)
        messages = read_until(socket, "end")

    assert messages[-1] == {"type": "end", "reason": "turns"}
    conversation = get_conversation_store().get(session_token)
    assert conversation.turns == 2
    assert len(conversation.exchanges) == 2
    assert all(exchange.user_text for exchange in conversation.exchanges)
    assert all(exchange.words for exchange in conversation.exchanges)
    assert all(exchange.reply for exchange in conversation.exchanges)


def test_an_llm_failure_keeps_the_socket_usable(
    session_token: str, mock_providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"count": 0}

    def flaky(conversation, exchange, provider) -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise LLMUnavailable("model down")
        return "Primera frase. Segunda frase."

    monkeypatch.setattr(chat_ws, "reply", flaky)
    monkeypatch.setattr(chat_ws, "_make_vad", lambda: ScriptedVAD((SPEECH + SILENCE) * 2))

    with client.websocket_connect(connect_url(session_token), headers={"origin": ORIGIN}) as socket:
        assert socket.receive_json()["type"] == "ready"
        send_turn(socket)
        failures = read_until(socket, "error")
        assert failures[-1] == {"type": "error", "code": "llm", "message": "model down"}
        send_turn(socket)
        reply_messages = read_until(socket, "reply")

    assert reply_messages[-1]["exchange"] == 1
    assert reply_messages[-1]["sentences"] == ["Primera frase.", "Segunda frase."]
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_chat_ws.py -v`

Expected: FAIL — exit code 1; `test_one_turn_produces_one_reply_and_one_audio_per_sentence` blocks on `audio` because the socket only sends `transcript`.

- [ ] **Step 3: Replace the imports**

In `src/sales_trainer/web/routes/chat_ws.py`, replace the import block with:

```python
import asyncio
import base64
import os

from fastapi import APIRouter, WebSocket

from sales_trainer.characters.loader import CharacterUnavailable, load_character
from sales_trainer.chat import (
    DEMO_PRODUCT,
    Conversation,
    Exchange,
    begin,
    done_reason,
    get_conversation_store,
    reply,
    split_sentences,
)
from sales_trainer.llm import get_llm_provider
from sales_trainer.llm.base import LLMProvider, LLMUnavailable
from sales_trainer.voice.stt import get_stt_provider
from sales_trainer.voice.stt.base import STTUnavailable
from sales_trainer.voice.turns import CHUNK_MS, SILENCE_MS, TurnDetector
from sales_trainer.voice.tts import get_provider as get_tts_provider
from sales_trainer.voice.tts.base import TTSProvider, TTSUnavailable
from sales_trainer.voice.vad import CHUNK_BYTES, SileroVAD
from sales_trainer.web.sessions import is_known
```

- [ ] **Step 4: Replace everything from `@router.websocket("/ws/chat")` to the end of the file**

```python
async def _turn(
    websocket: WebSocket,
    conversation: Conversation,
    exchange: Exchange,
    provider: LLMProvider,
    tts: TTSProvider,
) -> None:
    """Answer one exchange: one reply, then one audio per sentence. Never closes the socket."""
    try:
        text = await asyncio.to_thread(reply, conversation, exchange, provider)
    except LLMUnavailable as error:
        await websocket.send_json({"type": "error", "code": "llm", "message": str(error)})
    else:
        sentences = split_sentences(text)
        await websocket.send_json(
            {"type": "reply", "exchange": exchange.index, "text": text, "sentences": sentences}
        )
        for index, sentence in enumerate(sentences):
            try:
                # Azure is a network call; in the loop it would freeze the receive path.
                result = await asyncio.to_thread(tts.synthesize, sentence, conversation.character.voice)
            except TTSUnavailable as error:
                await websocket.send_json({"type": "error", "code": "tts", "message": str(error)})
                continue
            await websocket.send_json(
                {
                    "type": "audio",
                    "exchange": exchange.index,
                    "index": index,
                    "audio_base64": base64.b64encode(result.audio).decode("ascii"),
                    "mime": result.mime,
                    "visemes": [event.model_dump() for event in result.visemes],
                }
            )
    reason = done_reason(conversation)
    if reason is not None:
        await websocket.send_json({"type": "end", "reason": reason})


@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket, session: str = "", level: str = "", product: str = "") -> None:
    await websocket.accept()
    origin = websocket.headers.get("origin", "")
    if origin not in allowed_origins():
        await _reject(websocket, "origin", f"origin not allowed: {origin or '(missing)'}")
        return
    if not is_known(session):
        await _reject(websocket, "session", "unknown session token")
        return
    try:
        level_number = int(level)
    except ValueError:
        await _reject(websocket, "level", f"level must be 1, 2 or 3, got {level or '(missing)'}")
        return
    if not MIN_LEVEL <= level_number <= MAX_LEVEL:
        await _reject(websocket, "level", f"level must be 1, 2 or 3, got {level_number}")
        return
    try:
        character = load_character(level_number)
    except CharacterUnavailable as error:
        # A broken card means "this level is not available" to the client.
        await _reject(websocket, "level", str(error))
        return
    try:
        stt = get_stt_provider()
    except STTUnavailable as error:
        await _reject(websocket, "stt", str(error))
        return
    try:
        llm = get_llm_provider()
    except LLMUnavailable as error:
        await _reject(websocket, "llm_config", str(error))
        return
    try:
        tts = get_tts_provider()
    except TTSUnavailable as error:
        await _reject(websocket, "tts", str(error))
        return
    try:
        vad = _make_vad()
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        await _reject(websocket, "vad", str(error))
        return

    silence_ms = int(os.environ.get("SALES_TRAINER_SILENCE_MS", str(SILENCE_MS)))
    detector = TurnDetector(silence_ms=silence_ms)
    conversation = get_conversation_store().start(session, character, product.strip() or DEMO_PRODUCT)
    await websocket.send_json(
        {
            "type": "ready",
            "character": {
                "name": character.name,
                "level": character.level,
                "max_turns": character.max_turns,
                "voice": character.voice,
            },
            "turns": conversation.turns,
        }
    )

    elapsed_ms = 0
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        chunk = message.get("bytes")
        if chunk is None or len(chunk) != CHUNK_BYTES:
            continue

        elapsed_ms += CHUNK_MS
        probability = vad.probability(chunk)
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
            # Whisper and Azure block for seconds; a worker thread keeps the loop receiving.
            result = await asyncio.to_thread(stt.transcribe, turn.audio)
        except STTUnavailable as error:
            await websocket.send_json({"type": "error", "code": "stt", "message": str(error)})
            continue

        await websocket.send_json(
            {
                "type": "transcript",
                "text": result.text,
                "language": result.language,
                "words": [word.model_dump() for word in result.words],
            }
        )
        exchange = begin(conversation, result.text, result.words, turn.audio_ms)
        await _turn(websocket, conversation, exchange, llm, tts)
```

Task 13 turns that last `await _turn(...)` into a cancellable background task; until then the loop waits for the answer, which is exactly what makes barge-in impossible and what the next task fixes.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_chat_ws.py -v`

Expected: exit code 0; `14 passed` (9 from Task 11 plus 5 here).

- [ ] **Step 6: Lint and commit**

Run: `uv run ruff check .`

Expected: exit code 0; `All checks passed!`.

```bash
git add src/sales_trainer/web/routes/chat_ws.py tests/unit/test_chat_ws.py
git commit -m "feat: answer each chat turn with one reply and one audio per sentence"
```

---

## Task 13: Barge-in and cancellation

**Files:**
- Modify: `src/sales_trainer/web/routes/chat_ws.py`
- Test: `tests/unit/test_chat_ws.py`

- [ ] **Step 1: Add the import and append the failing tests**

In `tests/unit/test_chat_ws.py`, change the first import line from:

```python
import uuid
```

to:

```python
import threading
import uuid
```

Then append these tests to the end of the file:

```python
def test_a_barge_in_fires_inside_the_armed_window(
    session_token: str, mock_providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(chat_ws, "_make_vad", lambda: ScriptedVAD(SPEECH + SILENCE + [0.9]))
    with client.websocket_connect(connect_url(session_token), headers={"origin": ORIGIN}) as socket:
        assert socket.receive_json()["type"] == "ready"
        send_turn(socket)
        read_until(socket, "audio")
        read_until(socket, "audio")
        socket.send_bytes(CHUNK)
        messages = read_until(socket, "barge_in")

    assert [message["type"] for message in messages] == ["barge_in"]
    conversation = get_conversation_store().get(session_token)
    assert conversation.exchanges[0].interrupted is True


def test_played_disarms_the_window(
    session_token: str, mock_providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(chat_ws, "_make_vad", lambda: ScriptedVAD((SPEECH + SILENCE) * 2))
    with client.websocket_connect(connect_url(session_token), headers={"origin": ORIGIN}) as socket:
        assert socket.receive_json()["type"] == "ready"
        send_turn(socket)
        read_until(socket, "audio")
        read_until(socket, "audio")
        socket.send_json({"type": "played"})
        send_turn(socket)
        messages = read_until(socket, "reply")

    assert "barge_in" not in [message["type"] for message in messages]
    assert messages[-1]["exchange"] == 1


def test_a_new_turn_cancels_the_running_reply(
    session_token: str, mock_providers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = threading.Event()

    def slow(conversation, exchange, provider) -> str:
        gate.wait(timeout=5)
        return "Frase uno. Frase dos."

    monkeypatch.setattr(chat_ws, "reply", slow)
    monkeypatch.setattr(chat_ws, "_make_vad", lambda: ScriptedVAD((SPEECH + SILENCE) * 2))

    with client.websocket_connect(connect_url(session_token), headers={"origin": ORIGIN}) as socket:
        assert socket.receive_json()["type"] == "ready"
        send_turn(socket)
        read_until(socket, "transcript")
        send_turn(socket)
        read_until(socket, "transcript")
        gate.set()
        messages = read_until(socket, "reply")

    assert [message.get("exchange") for message in messages if message["type"] in {"reply", "audio"}] == [1]
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/unit/test_chat_ws.py -v`

Expected: FAIL — exit code 1; `test_a_barge_in_fires_inside_the_armed_window` blocks on `barge_in` because the server has no window and never sends it.

- [ ] **Step 3: Replace the module header and the imports**

In `src/sales_trainer/web/routes/chat_ws.py`, replace everything above the `_reject` helper with:

```python
import asyncio
import base64
import json
import os
from dataclasses import dataclass

from fastapi import APIRouter, WebSocket

from sales_trainer.characters.loader import CharacterUnavailable, load_character
from sales_trainer.chat import (
    DEMO_PRODUCT,
    Conversation,
    Exchange,
    begin,
    done_reason,
    get_conversation_store,
    reply,
    split_sentences,
)
from sales_trainer.llm import get_llm_provider
from sales_trainer.llm.base import LLMProvider, LLMUnavailable
from sales_trainer.voice.stt import get_stt_provider
from sales_trainer.voice.stt.base import STTUnavailable
from sales_trainer.voice.turns import CHUNK_MS, SILENCE_MS, THRESHOLD, TurnDetector
from sales_trainer.voice.tts import get_provider as get_tts_provider
from sales_trainer.voice.tts.base import TTSProvider, TTSUnavailable
from sales_trainer.voice.vad import CHUNK_BYTES, SileroVAD
from sales_trainer.web.sessions import is_known

router = APIRouter()

POLICY_VIOLATION = 1008
MIN_LEVEL = 1
MAX_LEVEL = 3


@dataclass
class ChatState:
    """Shared between the receive loop and the reply task; both run in one event loop."""

    armed: bool = False
    ended: bool = False


def allowed_origins() -> set[str]:
    port = os.environ.get("SALES_TRAINER_PORT", "8765")
    return {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}


def _make_vad() -> SileroVAD:
    return SileroVAD()


def _parse(text: str) -> dict:
    try:
        payload = json.loads(text)
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


async def _stop(task: asyncio.Task | None) -> None:
    """Cancel a running reply and wait for it, so it cannot send after this point."""
    if task is None or task.done():
        return
    task.cancel()
    await asyncio.wait([task])
```

Keep `_reject` as it is; then replace everything from `async def _turn(` to the end of the file with Step 4.

- [ ] **Step 4: Replace `_turn` and the handler tail**

```python
async def _turn(
    websocket: WebSocket,
    conversation: Conversation,
    exchange: Exchange,
    provider: LLMProvider,
    tts: TTSProvider,
    state: ChatState,
) -> None:
    """Answer one exchange: one reply, then one audio per sentence. Never closes the socket."""
    try:
        text = await asyncio.to_thread(reply, conversation, exchange, provider)
    except LLMUnavailable as error:
        await websocket.send_json({"type": "error", "code": "llm", "message": str(error)})
    else:
        sentences = split_sentences(text)
        await websocket.send_json(
            {"type": "reply", "exchange": exchange.index, "text": text, "sentences": sentences}
        )
        sent = 0
        for index, sentence in enumerate(sentences):
            try:
                # Azure is a network call; in the loop it would freeze the receive path.
                result = await asyncio.to_thread(tts.synthesize, sentence, conversation.character.voice)
            except TTSUnavailable as error:
                await websocket.send_json({"type": "error", "code": "tts", "message": str(error)})
                continue
            await websocket.send_json(
                {
                    "type": "audio",
                    "exchange": exchange.index,
                    "index": index,
                    "audio_base64": base64.b64encode(result.audio).decode("ascii"),
                    "mime": result.mime,
                    "visemes": [event.model_dump() for event in result.visemes],
                }
            )
            sent += 1
            state.armed = True
        if sent == 0:
            # No audio means no window: a stale one would interrupt a later turn.
            state.armed = False
    reason = done_reason(conversation)
    if reason is not None:
        state.ended = True
        await websocket.send_json({"type": "end", "reason": reason})
```

and, inside `chat_socket`, replace the block from `elapsed_ms = 0` to the end of the file with:

```python
    state = ChatState()
    task: asyncio.Task | None = None
    elapsed_ms = 0
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            await _stop(task)
            return
        if state.ended:
            continue

        text = message.get("text")
        if text is not None:
            if _parse(text).get("type") == "played":
                state.armed = False
            continue
        chunk = message.get("bytes")
        if chunk is None or len(chunk) != CHUNK_BYTES:
            continue

        elapsed_ms += CHUNK_MS
        probability = vad.probability(chunk)
        if state.armed and probability > THRESHOLD:
            # The interruption is also the start of the next user turn, so the detector runs on.
            state.armed = False
            if conversation.exchanges:
                conversation.exchanges[-1].interrupted = True
            await _stop(task)
            task = None
            await websocket.send_json({"type": "barge_in", "t_ms": elapsed_ms})

        update = detector.push(chunk, probability)
        if update.started:
            await websocket.send_json({"type": "turn_start", "t_ms": elapsed_ms})
        if update.ended is None:
            continue

        turn = update.ended
        await websocket.send_json({"type": "turn_end", "t_ms": elapsed_ms, "audio_ms": turn.audio_ms})
        if update.discarded:
            continue

        # A new finished turn drops whatever is left of a stale reply.
        await _stop(task)
        task = None
        try:
            # Whisper and Azure block for seconds; a worker thread keeps the loop receiving.
            result = await asyncio.to_thread(stt.transcribe, turn.audio)
        except STTUnavailable as error:
            await websocket.send_json({"type": "error", "code": "stt", "message": str(error)})
            continue

        await websocket.send_json(
            {
                "type": "transcript",
                "text": result.text,
                "language": result.language,
                "words": [word.model_dump() for word in result.words],
            }
        )
        exchange = begin(conversation, result.text, result.words, turn.audio_ms)
        task = asyncio.create_task(_turn(websocket, conversation, exchange, llm, tts, state))
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_chat_ws.py -v`

Expected: exit code 0; `17 passed` (14 from Task 12 plus 3 here).

- [ ] **Step 6: Run the whole suite and lint**

Run: `uv run pytest -q` then `uv run ruff check .`

Expected: exit code 0 for both; `124 passed` and `All checks passed!`.

- [ ] **Step 7: Commit**

```bash
git add src/sales_trainer/web/routes/chat_ws.py tests/unit/test_chat_ws.py
git commit -m "feat: interrupt the avatar with barge-in over the chat socket"
```

---

## Task 14: `/debug/chat` page — reuse `mic.js`, play the `audio` messages

**Files:**
- Modify: `src/sales_trainer/web/static/js/mic.js`
- Create: `src/sales_trainer/web/static/debug/chat.html`
- Create: `src/sales_trainer/web/static/js/chat-debug.js`
- Modify: `src/sales_trainer/web/app.py`

- [ ] **Step 1: Replace `src/sales_trainer/web/static/js/mic.js`**

```javascript
// Microphone to websocket: PCM16 mono 16 kHz frames of 512 samples (32 ms).

export async function startListening({ session, path = "/ws/stt", params = {}, onMessage, onError }) {
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
  const query = new URLSearchParams({ session, ...params });
  const socket = new WebSocket(`${scheme}://${location.host}${path}?${query}`);
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
    send(payload) {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(payload));
      }
    },
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

The default `path` keeps `/debug/stt` working unchanged; `params` and `send` are what `/debug/chat` needs.

- [ ] **Step 2: Create `src/sales_trainer/web/static/debug/chat.html`**

```html
<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Sales Trainer — Conversación</title>
    <style>
      html,
      body {
        margin: 0;
        min-height: 100%;
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
      #conversation {
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      .bubble {
        padding: 10px 12px;
        border-radius: 8px;
        max-width: 60ch;
        line-height: 1.5;
      }
      #transcript {
        background: #1b2733;
        align-self: flex-end;
      }
      #answer {
        background: #24313d;
      }
      #log {
        color: #8b98a5;
        padding-left: 18px;
      }
    </style>
  </head>
  <body>
    <section id="controls">
      <button id="start" type="button">Hablar</button>
      <button id="stop" type="button">Parar</button>
      <p id="status">listo</p>
      <p>Turnos: <span id="turns">0</span></p>
      <ul id="log"></ul>
    </section>
    <section id="conversation">
      <p class="bubble" id="transcript"></p>
      <p class="bubble" id="answer"></p>
    </section>
    <script type="module" src="/static/js/chat-debug.js"></script>
  </body>
</html>
```

- [ ] **Step 3: Create `src/sales_trainer/web/static/js/chat-debug.js`**

```javascript
import { startListening } from "./mic.js";

const statusEl = document.getElementById("status");
const turnsEl = document.getElementById("turns");
const transcriptEl = document.getElementById("transcript");
const answerEl = document.getElementById("answer");
const logEl = document.getElementById("log");
const startButton = document.getElementById("start");
const stopButton = document.getElementById("stop");

const params = new URLSearchParams(window.location.search);
const session = params.get("session") ?? "";
const level = params.get("level") ?? "";
const product = params.get("product") ?? "";

const state = { ready: false, listening: false, talking: false, turns: 0, lastError: null, ended: false };
window.chatDebug = state;

let connection = null;
let context = null;
let currentExchange = -1;
let expected = 0;
let received = 0;
let playedSent = false;
let queue = [];
let playing = false;
let source = null;

function audioContext() {
  if (context === null) {
    context = new AudioContext();
  }
  return context;
}

function log(text) {
  const item = document.createElement("li");
  item.textContent = text;
  logEl.append(item);
}

function stopAudio() {
  if (source !== null) {
    source.onended = null;
    source.stop();
    source = null;
  }
  queue = [];
  playing = false;
  state.talking = false;
}

function sendPlayed() {
  if (playedSent || connection === null || received < expected) {
    return;
  }
  playedSent = true;
  connection.send({ type: "played" });
}

async function playNext() {
  if (playing || queue.length === 0) {
    return;
  }
  playing = true;
  state.talking = true;
  const message = queue.shift();
  const raw = atob(message.audio_base64);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) {
    bytes[i] = raw.charCodeAt(i);
  }
  const ctx = audioContext();
  await ctx.resume();
  const buffer = await ctx.decodeAudioData(bytes.buffer);
  source = ctx.createBufferSource();
  source.buffer = buffer;
  source.connect(ctx.destination);
  source.onended = () => {
    source = null;
    playing = false;
    if (queue.length > 0) {
      void playNext();
      return;
    }
    state.talking = false;
    sendPlayed();
  };
  source.start();
}

function enqueue(message) {
  received += 1;
  queue.push(message);
  log(`frase ${message.index + 1} de ${expected} recibida`);
  void playNext();
}

function onMessage(message) {
  if (message.type === "ready") {
    state.listening = true;
    const { name, level: characterLevel, max_turns: maxTurns } = message.character;
    statusEl.textContent = `${name} (nivel ${characterLevel}, ${maxTurns} turnos)`;
  } else if (message.type === "turn_start") {
    statusEl.textContent = "te escucho";
  } else if (message.type === "turn_end") {
    statusEl.textContent = "transcribiendo";
  } else if (message.type === "transcript") {
    state.turns += 1;
    turnsEl.textContent = String(state.turns);
    transcriptEl.textContent = message.text;
    statusEl.textContent = "pensando";
  } else if (message.type === "reply") {
    currentExchange = message.exchange;
    expected = message.sentences.length;
    received = 0;
    playedSent = false;
    answerEl.textContent = message.text;
    statusEl.textContent = "contestando";
  } else if (message.type === "audio") {
    if (message.exchange !== currentExchange) {
      return;
    }
    enqueue(message);
  } else if (message.type === "barge_in") {
    stopAudio();
    log("interrumpido");
    statusEl.textContent = "interrumpido";
  } else if (message.type === "end") {
    state.ended = true;
    statusEl.textContent = `fin de la conversación (${message.reason})`;
    stopAudio();
    if (connection !== null) {
      connection.stop();
      connection = null;
    }
    state.listening = false;
  } else if (message.type === "error") {
    state.lastError = message.message;
    statusEl.textContent = `error: ${message.message}`;
  }
}

startButton.addEventListener("click", async () => {
  if (connection !== null) {
    return;
  }
  statusEl.textContent = "conectando";
  try {
    connection = await startListening({
      session,
      path: "/ws/chat",
      params: { level, product },
      onMessage,
      onError: (error) => {
        state.lastError = error.message;
        statusEl.textContent = `error: ${error.message}`;
      },
    });
  } catch (error) {
    state.lastError = error.message;
    statusEl.textContent = `error: ${error.message}`;
  }
});

stopButton.addEventListener("click", () => {
  stopAudio();
  if (connection !== null) {
    connection.stop();
    connection = null;
  }
  state.listening = false;
  statusEl.textContent = "parado";
});

requestAnimationFrame(() => {
  requestAnimationFrame(() => {
    state.ready = true;
  });
});
```

`received < expected` is what stops `played` from leaving before the last sentence has arrived: the client knows how many sentences the `reply` announced.

- [ ] **Step 4: Add the route to `src/sales_trainer/web/app.py`**

Append after the `/debug/stt` handler:

```python
@app.get("/debug/chat")
async def debug_chat(session: str = "", level: str = "") -> HTMLResponse:
    return _page("debug/chat.html", session)
```

The `level` query parameter is read by `chat-debug.js` from `window.location.search`, so the handler only declares it to keep the signature honest about the URL. Ruff's default rules (E4/E7/E9/F) do not flag an unused function argument.

- [ ] **Step 5: Verify the page and its scripts are served**

Run:

```bash
uv run python -c "
from fastapi.testclient import TestClient
from sales_trainer.web import sessions
from sales_trainer.web.app import app
c = TestClient(app)
print('/debug/chat', c.get('/debug/chat?session=manual&level=1').status_code)
print('chat-debug.js', c.get('/static/js/chat-debug.js').status_code)
print('mic.js', c.get('/static/js/mic.js').status_code)
print('session registered', sessions.is_known('manual'))
"
```

Expected: exit code 0; `/debug/chat 200`, `chat-debug.js 200`, `mic.js 200`, `session registered True`.

- [ ] **Step 6: Run the suite and lint**

Run: `uv run pytest -q` then `uv run ruff check .`

Expected: exit code 0 for both; `124 passed` and `All checks passed!`. `/debug/stt` still works because `mic.js` gained defaults, not new requirements.

- [ ] **Step 7: Commit**

```bash
git add src/sales_trainer/web/static/js/mic.js src/sales_trainer/web/static/debug/chat.html src/sales_trainer/web/static/js/chat-debug.js src/sales_trainer/web/app.py
git commit -m "feat: add the chat debug page"
```

---

## Task 15: End-to-end with the fake microphone and the mock providers

**Files:**
- Create: `tests/e2e/test_chat_page.py`

- [ ] **Step 1: Create the test**

```python
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

PORT = 8127
BASE_URL = f"http://127.0.0.1:{PORT}"
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "hola-marta-16k.wav"
TOKEN = "e2e-chat"


def _wait_for_server(timeout_seconds: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = urllib.request.urlopen(f"{BASE_URL}/debug/chat?session={TOKEN}&level=1", timeout=2)
            try:
                if response.status == 200:
                    return
            finally:
                response.close()
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    raise RuntimeError("web server did not become ready in time")


@pytest.mark.e2e
def test_debug_chat_page_answers_a_spoken_turn() -> None:
    env = {
        **os.environ,
        "SALES_TRAINER_LLM": "mock",
        "SALES_TRAINER_STT": "mock",
        "SALES_TRAINER_TTS": "mock",
        "SALES_TRAINER_PORT": str(PORT),
    }
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

            page.goto(f"{BASE_URL}/debug/chat?session={TOKEN}&level=1")
            page.wait_for_function("window.chatDebug && window.chatDebug.ready === true")
            page.click("#start")
            page.wait_for_function("window.chatDebug.listening === true", timeout=15000)
            page.wait_for_function("window.chatDebug.turns > 0", timeout=30000)
            page.wait_for_function("document.getElementById('answer').textContent.trim().length > 0", timeout=30000)
            page.wait_for_function("document.querySelectorAll('#log li').length > 0", timeout=30000)

            assert "Te sigo." in page.inner_text("#answer")
            assert page.evaluate("window.chatDebug.lastError") is None
            assert page.evaluate("window.chatDebug.ended") is False
            assert errors == []
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
```

- [ ] **Step 2: Run it**

Run: `uv run pytest -m e2e -v`

Expected: exit code 0; `5 passed` (the four Phase 1-3 e2e tests plus this one).

If `window.chatDebug.turns > 0` times out, the fake microphone fed no speech: check that `tests/fixtures/hola-marta-16k.wav` is 16 kHz mono 16-bit and that Chromium logs no `getUserMedia` error in `errors`. If `#log li` times out, the mock TTS audio never arrived or `decodeAudioData` rejected it: open `/debug/chat?session=manual&level=1` by hand with `SALES_TRAINER_TTS=mock` and watch the browser console.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_chat_page.py
git commit -m "test: add e2e coverage for a spoken chat turn"
```

---

## Task 16: Full suite and linter

- [ ] **Step 1: Run everything, unit and e2e**

Run: `uv run pytest -q`

Expected: exit code 0; `129 passed`.

The count is: 64 pre-existing unit/integration + 60 new unit tests (8 `test_characters.py` + 21 `test_llm.py` + 14 `test_chat.py` + 17 `test_chat_ws.py`) = 124 unit, plus 5 e2e = 129 collected.

Run: `uv run pytest -m e2e -v`

Expected: exit code 0; `5 passed`.

- [ ] **Step 2: Lint**

Run: `uv run ruff check .`

Expected: exit code 0; `All checks passed!`.

- [ ] **Step 3: Fix anything the three commands flag, then re-run them until green.**

Do not commit a red suite.

---

## Task 17: Close the phase — status and decisions

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/decisions.md`

- [ ] **Step 1: Update the status in `AGENTS.md`**

Before:

```
- Current phase: 4 (characters, LLM and evaluation). In progress: character dialogue and the success gauge.
```

After:

```
- Current phase: 5 (evaluation engine and temperature). In progress: the LLM judge, the delivery metrics and the success gauge.
```

`MEMORY.md` §11 names Phase 5 as "evaluation engine (judge + delivery) and temperature"; do not invent a different topic.

- [ ] **Step 2: Append the decision to `docs/decisions.md`**

```markdown
## 2026-11-10 — Phase 4: YAML character cards, a provider-agnostic LLM and barge-in on `/ws/chat`

- **Decision:** a second WebSocket `/ws/chat?session=&level=&product=` carries the conversation and `/ws/stt` stays a transcription debug tool. Each finished voice turn becomes one exchange, one `LLMProvider.complete()` call in a worker thread, one `reply` message and one TTS call plus one `audio` message per sentence of the answer.
- **Decision:** the three characters are `characters/nivel{1,2,3}.yaml` plus `characters/prompts/nivel{1,2,3}.md`, validated with pydantic v2 at load. The card holds name, voice, start temperature, success threshold, maximum turns and the objection/hot-button/cold-button/filler lists; the Spanish role rules live in the prompt file because they are content, not code.
- **Decision:** `SALES_TRAINER_LLM=openai-compatible|anthropic|mock`, default `openai-compatible` because the project memory asks for a local model by default. `openai_compat` covers Ollama, LM Studio, DeepSeek and OpenAI by changing `OPENAI_BASE_URL` and `SALES_TRAINER_LLM_MODEL`; `OPENAI_API_KEY` is optional so a local server needs no key.
- **Discarded alternative:** extending `/ws/stt` with conversation messages. The STT page must stay a tool for checking transcripts, and the conversation needs its own state, its own errors and its own end condition.
- **Discarded alternative:** extracting the VAD/turn loop shared with `/ws/stt` into a helper. It is 20 lines for two callers; the abstraction would cost more than the duplication.
- **Discarded alternative:** streaming the answer or the TTS. The 2.5 s latency target is measured in Phase 8, and per-sentence playback already starts with the first sentence.
- **Reason for barge-in on the server:** the real VAD probability is only on the server, and the client is the only side that knows when playback ended, so the client reports `{"type":"played"}` and the server decides the interruption inside that window.
- **Deviations from the design:** (1) a card that fails to load for a valid level answers `{"type":"error","code":"level"}` because the documented code set has no `character` code and a broken card means "this level is not available". (2) `build_system` injects the prompt, the product brief and the four card lists but not the temperature, threshold or turn limit, because the prompt forbids the character from revealing them. (3) a TTS provider that cannot be built at connect answers `{"type":"error","code":"tts"}`, the same rule as `llm_config`. (4) `mic.js` gained `path`, `params` and `send(payload)` so `/debug/chat` can reuse it; the spec assumed that reuse but `mic.js` hard-coded `/ws/stt`. (5) after `end` the socket stays open and ignores further audio instead of closing, which avoids a send-after-close race with the receive loop. (6) `end` is sent even when the last turn's provider call failed, so a client waiting for `end` cannot hang.
- **Consequences:** `SALES_TRAINER_LLM`, `SALES_TRAINER_LLM_MODEL` (required by the real providers), `SALES_TRAINER_LLM_TIMEOUT` (30 s), `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`. Conversations live in memory per session token in `chat.ConversationStore`; connecting again with the same token starts a fresh one. `/debug/chat?session=&level=&product=` drives the whole path and exposes `window.chatDebug`.
- **Verified (2026-11-10):** the 124-test unit suite plus the 5 e2e tests pass with `SALES_TRAINER_LLM=mock`, `SALES_TRAINER_STT=mock` and `SALES_TRAINER_TTS=mock`, with no key and no network; the e2e drives a real worklet, socket, VAD and turn detector with the fake microphone and gets a `reply`, its `audio` messages and no console error.
```

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md docs/decisions.md
git commit -m "docs: close out phase 4"
```

---

## Task 18: Known limits — what this phase does not prove

**Files:**
- Modify: `docs/decisions.md`

- [ ] **Step 1: Prove no test needs real LLM configuration**

Run:

```bash
env -u SALES_TRAINER_LLM -u SALES_TRAINER_LLM_MODEL -u OPENAI_BASE_URL -u OPENAI_API_KEY -u ANTHROPIC_API_KEY \
  uv run pytest -q
```

Expected: exit code 0; `129 passed`. Every socket test sets its own provider through `monkeypatch`, so a machine with no LLM configuration at all still runs the whole suite.

- [ ] **Step 2: Record the unverified parts at the end of the Phase 4 entry in `docs/decisions.md`**

```markdown
- **Unverified:** no real model has answered a single turn in this phase. The Anthropic and OpenAI-compatible clients are covered only against `httpx.MockTransport` (URL, headers, body, parsing, HTTP 500, timeout, malformed body), because there is no key for either in this environment; nobody is blocked because the default provider is the OpenAI-compatible one and a local server needs no key. The first real call is a manual check and must record the model, the measured round trip and the answer quality here.
- **Known limit:** `characters/` lives outside the package, like `.env`. The suite runs from the source tree; packaging the cards into a wheel is a Phase 8 concern.
- **Known limit:** one TTS call per sentence multiplies Azure round trips. The prompt caps answers at 1-3 short sentences and playback starts with the first one; a sentence-level cache is not built until Phase 8 measures it.
- **Known limit:** `ConversationStore` keeps every conversation for the life of the process and never expires one. Acceptable for a single local user; revisit with the SQLite history of Phase 7.
- **Known limit:** barge-in only cuts between sentences: a sentence already streaming keeps playing until the client stops it on `barge_in`, and the server drops the rest of the reply. Cutting mid-sentence is deferred.
- **Known limit:** `SAVE_AUDIO` is still unimplemented and no audio touches the disk, as in Phase 3.
```

- [ ] **Step 3: Commit**

```bash
git add docs/decisions.md
git commit -m "docs: record the unverified parts of phase 4"
```

---

## Spec coverage

- Criterion 1 (`/debug/chat?session=&level=` starts a conversation, a missing or out-of-range level rejected on the page and with `code:"level"`): Tasks 10 (`test_a_missing_level_is_rejected`, `test_an_out_of_range_level_is_rejected`), 14 (the page renders `error: <message>` in `#status`), 15 (the e2e loads the page with `level=1`).
- Criterion 2 (`/ws/chat` rejects foreign/missing `Origin` and unknown tokens with `code:"origin"|"session"`): Task 10, the three handshake tests; same `allowed_origins()` and `is_known()` as `/ws/stt`.
- Criterion 3 (one finished turn → one `reply`, then one `audio` per sentence, in order): Task 12 `test_one_turn_produces_one_reply_and_one_audio_per_sentence` asserts the exact message order and the two `audio` indices.
- Criterion 4 (`reply` comes from the configured `LLMProvider`; `SALES_TRAINER_LLM=mock` never touches the network): Tasks 4-7 (the protocol, both real clients, the factory), Task 18 Step 1 (suite green with no LLM configuration), Task 14 Step 6 and Task 16 (green with `mock`).
- Criterion 5 (`{"type":"end","reason":"turns"}` after `max_turns`, every turn kept): Task 9 (`done_reason`, `begin`), Task 12 `test_the_conversation_ends_after_max_turns` asserts the frame and the two stored exchanges with text, words and reply.
- Criterion 6 (barge-in only inside the armed window, exactly one `barge_in`, exchange marked interrupted): Task 12 arms the window on `audio`, Task 13 adds the check and `test_a_barge_in_fires_inside_the_armed_window` / `test_played_disarms_the_window`.
- Criterion 7 (`llm` keeps the socket usable, `llm_config` closes it, `tts` still delivers the reply): Task 11 (`stt`), Task 12 (`llm_config`, `tts`, `test_an_llm_failure_keeps_the_socket_usable`), Task 12's `_turn` continues after a TTS failure so the `reply` already sent stands.
- Criterion 8 (the three cards match `MEMORY.md` §5, each with its own prompt): Tasks 2-3, `test_the_cards_match_the_project_memory` and `test_every_prompt_file_is_loaded_as_text`.
- Criterion 9 (`uv run pytest`, `uv run pytest -m e2e`, `uv run ruff check .` green with no keys, the 68 pre-existing tests intact): Tasks 16-18.
- Non-goals respected: no judge, no delivery metrics, no gauge, no victory/defeat, no streaming, no retries, no result screen, no reports, no SQLite, no partial transcripts, no push-to-talk, no text input, no `SAVE_AUDIO`, no MCP changes.
- Spec "Files to change": every new file is created by a task. One file the spec did not list is modified: `src/sales_trainer/web/static/js/mic.js` (Task 14), because the spec's "the page reuses `mic.js`" is impossible while `mic.js` hard-codes `/ws/stt`. Everything else in the list is covered as written.

## Execution order

Tasks 1-3 lay the ground the rest reads: the dependency, the three cards and prompts, and the pydantic loader. Tasks 4-7 build the LLM layer bottom-up behind one protocol, each provider tested against `httpx.MockTransport` with no key. Tasks 8-9 build the pure conversation core, splitter first, then exchanges and the turn limit. Tasks 10-13 expose it on `/ws/chat` in four green steps: handshake, transcript, reply and audio, then barge-in and cancellation. Task 14 builds the page, reusing `mic.js` with a new path argument. Task 15 proves the whole path with a real worklet, socket and VAD over the fake microphone, with only the providers doubled. Tasks 16-18 verify, close and record what was not proven.
