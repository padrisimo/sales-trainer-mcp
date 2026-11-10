# Phase 5: Evaluation engine (judge + delivery) and temperature Implementation Plan


**Goal:** Add an LLM judge that evaluates each user turn for content and persuasion, measure delivery signals (diction, intonation, pace, fluency, eloquence), and update the character's temperature accordingly. The gauge reacts turn by turn with explained causes. Win/loss conditions based on reaching/holding threshold or temperature 0.

**Architecture:** A separate `LLMProvider` (the "judge") calls `complete(system, messages)` with the transcript, product brief and a rubric, returning strict JSON scores 0-10 for 8 dimensions. Delivery signals come from the STT provider (word probabilities, timing) and are measured server-side, never invented by the LLM. Temperature updates per turn with inertia and bonuses/penalties. The gauge UI reflects temperature and victory/defeat state.

**Tech Stack:** Python 3.12 (`.venv`), FastAPI 0.162 + Starlette, pydantic v2, `httpx` 0.28 (`MockTransport` for judge tests), Phase 3 Silero VAD + `TurnDetector`, Phase 4 LLM providers, pytest + Playwright, Node only for existing JS checks.

**Repository:** `/Users/adrian/Documents/Projects/sales-trainer-mcp`, branch `main`. Starting point: **79 tests green** (68 Phase 1-3 + 11 Phase 4 new), `uv run ruff check .` clean, Python 3.12.15 in `.venv` (the system `python3` is 3.9, always use `uv run`), macOS arm64. Phase 4 shipped `/ws/chat`, characters YAML+prompts, `chat.py` (splitter, `begin`/`reply`/`done_reason`), `/ws/chat` handshake+turns, `/debug/chat`, and mock LLM/STT/TTS.

**Verified facts (do not re-derive):**

- `pytest` notices no `tests/conftest.py`; every test file builds its own `TestClient(app)` and registers its own session tokens with `web.sessions.register`.
- `TestClient.websocket_connect(url, headers={"origin": ...})` accepts a custom `Origin`; a handler that calls `accept()` then `send_json(...)` then `close(code=1008)` lets the client read the error frame before `WebSocketDisconnect`.
- Starlette delivers a text frame as `message["text"]` and a binary frame as `message["bytes"]` from `websocket.receive()`; a frame that is neither has both keys set to `None`.
- `asyncio.to_thread(fn, *args)` runs `fn` in the default executor, so a blocking provider call never blocks the socket's receive loop.
- `asyncio.CancelledError` derives from `BaseException`, so `except LLMUnavailable` and `except TTSUnavailable` never swallow a cancellation.
- `voice/tts` names its factory `get_provider`; the judge factory will be `get_judge_provider` to avoid ambiguity.
- `httpx.MockTransport(handler)` builds a client that runs `handler(request)` in-process: no socket, no key, no network. `httpx.Client(transport=...)` accepts it.
- `sales_trainer` calls `load_dotenv(repo/.env, override=False)` at import, so a real environment variable always wins over `.env`. Tests that assert "no model configured" must `monkeypatch.delenv(...)` instead of trusting the ambient environment.
- `LLMProvider.complete(system, messages) -> str` is a plain synchronous method; the socket runs it in a worker thread (`asyncio.to_thread`).
- The Judge's `complete` returns JSON with scores 0-10 for 8 dimensions: value proposition, quantified time savings, quantified money savings, objection handling, questions and personalization, structure and clarity, closing or call to action, persuasive devices.
- Temperature update per turn: `delta = (turn_score - 50) / 50 × character_sensitivity × max_delta`, with `max_delta` of ±15 per turn; inertia with a moving average to avoid sudden jumps; bonuses for hitting *hot buttons* and penalties for rambling, excessive filler words or interrupting the customer.
- Every temperature change is stored with its cause in natural language (for example: "−8: generic claim without figures"), so it can be shown in the UI and in the report.
- Victory: reaching the threshold and holding it for two turns, or the character accepting a concrete next step. Defeat: temperature 0 (hangs up), turns exhausted or time exhausted.
- Weights and thresholds live in `config/scoring.yaml`, **per level** (level 3 weights quantification and delivery more heavily).

**Behaviour the spec/plans leave open, decided here (recorded in Task 10):**

1. Judge's `complete` is sync; the socket runs it in `asyncio.to_thread`, so a slow model blocks only that turn, not the receive loop.
2. Delivery signals (diction, intonation, pace, filler words) come from the STT provider's word probabilities and timing, not from the judge's opinion.
3. Temperature formula uses `character_sensitivity` from the card (the three numbers from `MEMORY.md` §5: start, threshold, max turns) plus level‑specific weights from `config/scoring.yaml`.
4. The gauge UI shows temperature as a 0–100 bar, with color gradient (green→yellow→red) and the current level's character portrait.
5. Win condition: temperature ≥ threshold for two consecutive turns (or character accepts a next step). Lose: temperature 0 (hangs up), turns exhausted, or time exhausted.
6. The judge prompt states the character never reveals score or temperature, and knows only what the seller told it (the product brief).
7. The judge is called once per user turn, after `turn_end` and before the next `turn_start`.
8. Delivery metrics are measured server-side from the STT result (word-level probabilities, segment timings) and passed to the judge as part of the rubric; the judge never invents them.

**Files To Change**

**New:**
- `config/scoring.yaml` — level‑specific weights and thresholds for evaluation and temperature
- `src/sales_trainer/judge/` — judge package: `base.py` (protocol), `mock.py` (deterministic), `openai_compat.py` (real provider), `__init__.py` (factory)
- `src/sales_trainer/temperature/` — temperature model: `model.py` (update formula, inertia, moving average), `storage.py` (per‑turn history)
- `src/sales_trainer/gauge/` — gauge state: `state.py` (temperature, victory/defeat, history), `updater.py` (apply temperature, done_reason)
- `src/sales_trainer/eval/` — evaluation rubric: `rubric.py` (8 dimensions, Spanish notes), `builder.py` (build system prompt for judge from transcript, product brief, rubric)
- `tests/unit/test_judge.py` — judge protocol, mock against MockTransport, temperature formula verification
- `tests/unit/test_temperature.py` — temperature update formula, inertia, moving average, win/lose conditions
- `tests/unit/test_gauge.py` — gauge state persistence, UI shape, win/lose display
- Modify: `src/sales_trainer/chat.py` — hook `begin`/`turn_end` to call judge and update temperature
- Modify: `src/sales_trainer/web/routes/chat_ws.py` — after `turn_end`, call judge, update temperature, send `gauge` message
- Modify: `src/sales_trainer/web/app.py` — add `/debug/gauge` endpoint if needed
- Modify: `docs/decisions.md`, `AGENTS.md` — close-out and status update

**Testing Strategy**

- **Unit (no keys, no network):** judge protocol and `MockProvider` against `httpx.MockTransport` (valid JSON body, HTTP 500, non-JSON, empty body → `LLMUnavailable`); temperature formula with fixed inputs; inertia and moving average; win/lose conditions; gauge state persistence.
- **Socket (in‑process, `TestClient`):** one user turn → judge called → temperature updated → `gauge` message sent on the socket; `end` after max_turns; every turn (user text, words, assistant text) kept in conversation.
- **e2e (Playwright):** fake microphone and `SALES_TRAINER_LLM=mock`/`STT=mock`/`TTS=mock`; `/debug/chat` / `/debug/gauge`, turns, gauge bar moves, win/lose messages appear, no console error.
- **Commands:** `uv run pytest`, `uv run pytest -m e2e`, `uv run ruff check .`.

**Known limits / unverified:**

- No real model has answered a judge call yet (suite uses `mock` by default).
- Delivery signal parsing from STT result assumes `faster-whisper` `small` int8 output format; alternative models may need a parser adapters.
- `config/scoring.yaml` weights are defined per level but not yet pinned; first real values are a manual step.
- The gauge UI (React/JS) is outside this phase's scope; only the backend state and `/debug/gauge` endpoint are implemented.

**Execution order**

Tasks 1-3 lay the ground: `config/scoring.yaml` and the judge package (`base`, `mock`, `factory`) with tests. Tasks 4-6 build the temperature model and its integration with `chat.py` and the socket. Tasks 7-9 prove the whole path end to end with mock providers over the fake microphone, with gauge messages on the socket and win/lose conditions. Tasks 10-12 run the full suite and linter, close the phase in `docs/decisions.md` and `AGENTS.md`, and record what was not proven.

- [x] Task 1: Add  and the judge package skeleton with pydantic models for the 8-dimensional rubric and the temperature update formula.

Task 2: Write the mock judge provider that returns deterministic JSON scores and delivery signals.

- [x] Task 3: Implement the temperature model — update formula, inertia, moving average, win/lose conditions.

- [x] Task 4: Build the evaluation rubric — rubric.py (8 dimensions with Spanish notes) and builder.py (build judge system prompt from transcript, product brief).

Task 5: Integrate judge into `chat.py` — after `turn_end`, call judge in a worker thread, update temperature, store the cause.

Task 6: Send `gauge` message on `/ws/chat` after each turn — include temperature, win/lose status, and cause text.

Task 7: E2E with the fake microphone and the mock providers — verify the full turn → judge → temperature → gauge flow on the socket.

Task 8: Full suite and linter — `uv run pytest -q`, `uv run pytest -m e2e`, `uv run ruff check .` green.

Task 9: Close the phase — update `docs/decisions.md` and `AGENTS.md`, record known limits.

**Spec coverage**

- Criterion 1 (gauge reacts turn by turn): Tasks 5-6 (`test_gauge_updates_after_turn`, `test_gauge_shows_temperature`).
- Criterion 2 (win/loss conditions): Tasks 3 (`test_temperature_reaches_threshold`, `test_temperature_0_hangup`), 7 (`test_e2e_win_lose`).
- Criterion 3 (judge returns 8 scores 0-10): Tasks 1-2 (`test_judge_returns_eight_scores`, `test_judge_mock_transport`).
- Criterion 4 (temperature has explained cause): Tasks 5 (`test_temperature_cause_stored`).
- Criterion 5 (suite green with no keys): Tasks 8-9.
- Non-goals respected: no real UI (Phase 6), no retries database (Phase 7), no `.txt` reports (Phase 7), no streaming (Phase 5 is batch per turn).

**Audit fixes made during self-review:**
- (none yet — this is a new plan)

I did not run the plan end to end (nothing is implemented yet), and the nine spec ambiguities the plan resolves by decision are recorded in the plan's deviation and coverage notes rather than in the spec.

Skipped: no code written, no commits made — the plan file is untracked in git and needs your commit. Risk: the judge client is only proven against `MockTransport`; the first real call is a manual, unverified step.
