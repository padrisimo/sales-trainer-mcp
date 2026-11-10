# Design — Phase 4: characters, LLM and the conversation loop

- **Date:** 2026-11-10
- **Topic:** fase4-personajes-llm-conversacion
- **Status:** Approved by the user (design)

## Context

Phases 0-3 are closed: a browser page opens from the MCP tool, a procedural avatar plays a viseme timeline, Azure or the mock synthesizes speech, and `/ws/stt` turns microphone audio into Spanish transcripts with per-word timings and probabilities. Turns live in memory per session (`TurnStore`) and are readable at `GET /api/turns`. The suite is at 68 unit/integration tests plus 4 e2e tests, green with no keys and no network.

Nothing replies yet. There is no character, no LLM, no conversation state and no barge-in: `MEMORY.md` §11 places those in Phase 4 ("characters with LLM and the conversation loop with barge-in"), and §5 fixes the three cards, their numbers and the rules the model must obey while playing them.

## Goal

Let the user hold a spoken conversation with one of three characters: each finished voice turn is sent to an LLM that answers in character, the answer is synthesized sentence by sentence and played by the browser, the user can interrupt the avatar while it speaks, and the conversation ends when the turn limit is reached.

## Acceptance Criteria

1. `/debug/chat?session=<token>&level=<1|2|3>` starts a conversation with that level's character, and a missing or out-of-range `level` is rejected with a readable error on the page and with `{"type":"error","code":"level"}` on the socket, instead of falling back silently.
2. `/ws/chat` rejects a foreign or missing `Origin` and an unknown session token with `{"type":"error","code":"origin"|"session"}`, exactly like `/ws/stt`.
3. One finished voice turn produces exactly one `reply` message followed by one `audio` message per sentence of that reply, in order.
4. The `reply` text comes from the configured `LLMProvider`; with `SALES_TRAINER_LLM=mock` the suite never touches the network.
5. The conversation ends with `{"type":"end","reason":"turns"}` after `max_turns` user turns, and every turn (user text, words, assistant text) is kept in the conversation.
6. While the barge-in window is armed (from the first `audio` message until `{"type":"played"}`), a microphone chunk whose VAD probability exceeds the threshold produces exactly one `{"type":"barge_in"}` and marks the current exchange as interrupted.
7. A failure while calling the provider becomes `{"type":"error","code":"llm"}` and the socket stays usable for the next turn; a provider that cannot be built when the socket connects becomes `{"type":"error","code":"llm_config"}` and the socket closes, like `stt` today; a TTS failure becomes `{"type":"error","code":"tts"}` and the `reply` text is still delivered.
8. The three cards match `MEMORY.md` §5: Marta 50/75/10, Javier 30/80/10, Carmen 10/85/8, each with its own prompt file.
9. `uv run pytest`, `uv run pytest -m e2e` and `uv run ruff check .` are green with no keys and no network; the 68 + 4 existing tests stay green.

## Non-Goals

- The LLM judge, the delivery metrics, temperature, the gauge and victory/defeat. That is Phase 5.
- Streaming the LLM answer or the TTS. The latency target of 2.5 s is measured in Phase 8.
- The real UI (level cards, product form, gauge, result screen) and retries. Phase 6.
- `.txt` reports, SQLite history and the remaining MCP tools. Phase 7.
- Partial transcripts, push-to-talk and text input as a fallback.
- Storing audio. `SAVE_AUDIO` stays unimplemented until the configuration phase.

## Proposed Architecture

**Chat socket.** `src/sales_trainer/web/routes/chat_ws.py` exposes `/ws/chat?session=&level=&product=`. It reuses the handshake of `/ws/stt` (accept, check `Origin` against `http://127.0.0.1:PORT` and `http://localhost:PORT`, check the session token against `web/sessions.py`, reject a missing or out-of-range `level` with `{"type":"error","code":"level"}`), then runs the same capture loop — `SileroVAD` + `TurnDetector` over 32 ms PCM16 chunks — and, for each finished turn, the conversation turn. Reason for a second socket instead of extending `/ws/stt`: the STT page must stay a transcription debug tool, and the conversation needs its own messages and state. The 20-line VAD/turn loop is duplicated rather than extracted; an abstraction for two callers costs more than it saves.

**Barge-in.** The server cannot know when playback ends, so the client says it. The window opens when the first `audio` message of a reply is sent and closes on `{"type":"played"}` from the client or on the `barge_in` itself; if a reply produced no audio (TTS failed for every sentence), the server closes the window itself so a stale window cannot interrupt a later turn. Inside the window, a chunk whose VAD probability is above the same `voice.turns.THRESHOLD` (0.5) that starts a turn sends `{"type":"barge_in"}` once, marks the exchange as interrupted, and lets the normal turn detection proceed — the interruption is also the start of the next user turn. The client stops its audio on `barge_in`.

**Characters.** `characters/nivel{1,2,3}.yaml` hold the card; `characters/prompts/nivel{1,2,3}.md` hold the versioned system prompt, because the role rules (1-3 short sentences, never reveal score or temperature, knows only what the seller told it) are content, not code. `src/sales_trainer/characters/loader.py` validates a card with pydantic v2 (`level` 1-3, `name`, `voice`, temperatures and threshold 0-100, `max_turns` 1-50, `prompt` pointing at an existing file under `characters/prompts/`) and exposes `load_character(level)`. The card also carries `objections`, `hot_buttons`, `cold_buttons` and `filler_words`: this phase injects them into the system prompt, Phase 5 uses them to move the temperature; the avatar appearance the cards will also need belongs to Phase 6. Cards keep the field names and comments in English; the prompt text is Spanish, because it is what the character says.

**LLM.** `src/sales_trainer/llm/base.py` defines `Message {role: "user"|"assistant", content}`, `LLMProvider.complete(system, messages) -> str` (a plain synchronous method; the socket runs it in a worker thread) and `LLMUnavailable`. No JSON mode yet; the judge's structured output arrives with Phase 5.

- `openai_compat.py`: `POST {OPENAI_BASE_URL}/chat/completions` with `httpx`. Covers Ollama, LM Studio, DeepSeek and OpenAI by changing `OPENAI_BASE_URL` and `SALES_TRAINER_LLM_MODEL`. The model and the base URL are required (no invented default); `OPENAI_API_KEY` is optional so local servers work.
- `anthropic.py`: `POST https://api.anthropic.com/v1/messages`, requires `ANTHROPIC_API_KEY` and `SALES_TRAINER_LLM_MODEL`.
- `mock.py`: deterministic reply per turn, no network.
- `__init__.py`: `SALES_TRAINER_LLM=mock|openai-compatible|anthropic`, default `openai-compatible` (local by default, as `MEMORY.md` requires), unknown value raises `LLMUnavailable`.
- The HTTP client is injectable (`transport`) so both real providers are tested against `httpx.MockTransport` with no key.
- A provider that cannot be built (missing model, missing base URL or key, unknown `SALES_TRAINER_LLM`) is rejected when the socket connects with `error {code:"llm_config"}` and the socket closes, exactly like `stt` does today.
- Both real clients use one `httpx` timeout built from `SALES_TRAINER_LLM_TIMEOUT` (default 30 s), and an HTTP error, a timeout or an unparsable body become `LLMUnavailable`.

**Conversation.** `src/sales_trainer/chat.py` holds `Exchange {index, user_text, words, audio_ms, reply, interrupted}`, `Conversation {session, character, product_brief, exchanges, turns}` (`turns` counts finished user turns), `ConversationStore` (in memory, per session token; connecting again with the same token starts a fresh conversation), `build_system(character, product_brief)`, `split_sentences(text)` (Spanish `.!?…`, keeps `¿`/`¡`, never splits on decimals or on the fixed list `Sr. Sra. Dr. Ud. Uds. p. ej. EE. UU.`) and the two halves of a turn: `begin(conversation, text, words, audio_ms) -> Exchange` appends the exchange and bumps `turns` **before** the provider is awaited, so a barge-in already has an exchange to mark; `reply(conversation, exchange, provider) -> str` builds the messages from the previous exchanges, calls the provider, stores the answer in `exchange.reply` and returns it. `done_reason(conversation)` returns `"turns"` once `turns >= max_turns`, else `None`. The product brief comes from `?product=`, with a demo product constant as fallback; the MCP `product_brief` argument stays unused until Phase 6 gives it a real page to feed (`start()` already accepts it today).

**Turn flow.** finished turn → `begin()` with the user text/words/audio_ms → background task: provider call in a worker thread (`asyncio.to_thread`, a local model blocks for seconds) → `split_sentences` → `reply {exchange, text, sentences}` → per sentence, `get_provider().synthesize(sentence, character.voice)` also in `asyncio.to_thread` (Azure is a network call; in the loop it would freeze the receive loop and with it barge-in) → `audio {exchange, index, audio_base64, mime, visemes}` → `end {reason}` if `done_reason` is set. The task is the only sender of `reply`/`audio`; `transcript` is sent by the loop before starting it, so the order is fixed. At most one task runs at a time: a new finished turn, or a `barge_in`, cancels the running one — dropping the rest of a stale reply is what interrupting means — and a cancelled task sends nothing more. Errors never close the socket: `error {code:"llm"|"tts", message}` and the next turn works.

**Debug page.** `/debug/chat` serves `static/debug/chat.html` + `static/js/chat-debug.js`: microphone button, the user's transcript, the character's answer, the interruption notice and the turn counter. It reuses `mic.js` for capture and the same TTS playback shape as `speak.js`; `window.chatDebug` exposes `{ready, listening, talking, turns, lastError, ended}` for the e2e. It tracks the current `exchange` and drops any `audio` that arrives for an older one, and sends `{"type":"played"}` once the last sentence of the current exchange has finished playing.

## WebSocket Protocol

Server → client:

| Type | Fields |
|---|---|
| `ready` | `character` (name, level, max_turns, voice), `turns` |
| `turn_start` | `t_ms` |
| `turn_end` | `t_ms`, `audio_ms` |
| `transcript` | `text`, `language`, `words[]` |
| `reply` | `exchange` (int), `text`, `sentences` (`list[str]`) |
| `audio` | `exchange` (int), `index` (int), `audio_base64`, `mime`, `visemes[]` |
| `barge_in` | `t_ms` |
| `end` | `reason` |
| `error` | `code` (`origin`, `session`, `level`, `stt`, `vad`, `llm_config`, `llm`, `tts`), `message` |

Client → server: binary PCM16 mono 16 kHz frames of 32 ms, and `{"type":"played"}` when the playback of the last `audio` finishes.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `SALES_TRAINER_LLM` | `openai-compatible` | `mock`, `openai-compatible`, `anthropic` |
| `SALES_TRAINER_LLM_MODEL` | — required | model id for the real providers |
| `SALES_TRAINER_LLM_TIMEOUT` | 30 | seconds for one provider call |
| `OPENAI_BASE_URL` | — required | OpenAI-compatible endpoint (`http://127.0.0.1:11434/v1` for Ollama) |
| `OPENAI_API_KEY` | empty | only for servers that need it |
| `ANTHROPIC_API_KEY` | empty | required by the Anthropic provider |
| `SALES_TRAINER_SILENCE_MS` | 700 | inherited from Phase 3 |

`.env` at the repository root is already loaded at import (`override=False`), so keys placed there reach both providers.

## Files To Change

**New:**
- `characters/nivel1.yaml`, `characters/nivel2.yaml`, `characters/nivel3.yaml`
- `characters/prompts/nivel1.md`, `characters/prompts/nivel2.md`, `characters/prompts/nivel3.md`
- `src/sales_trainer/characters/__init__.py`, `loader.py`
- `src/sales_trainer/llm/__init__.py`, `base.py`, `openai_compat.py`, `anthropic.py`, `mock.py`
- `src/sales_trainer/chat.py`
- `src/sales_trainer/web/routes/chat_ws.py`
- `src/sales_trainer/web/static/debug/chat.html`, `src/sales_trainer/web/static/js/chat-debug.js`
- `tests/unit/test_characters.py`, `test_llm.py`, `test_chat.py`, `test_chat_ws.py`
- `tests/e2e/test_chat_page.py`

**Modified:**
- `src/sales_trainer/web/app.py` — mount the chat router and serve `/debug/chat`.
- `pyproject.toml` — add `pyyaml` (the cards are YAML; nothing reads YAML today).
- `docs/decisions.md`, `AGENTS.md` — close-out.

## Testing Strategy

- **Unit (no keys, no network):** card loading and validation errors; the three numbers from `MEMORY.md`; prompt files exist and are not empty; `build_system` contains role and product; `split_sentences` against Spanish cases (including `¿?`, `¡!`, ellipsis, `3,5`, `1.200`, and every abbreviation in the fixed list); `begin`/`reply`/`done_reason`; the factory and its unknown-value error; both real providers against `httpx.MockTransport` (URL, headers, body with the timeout applied, parse, HTTP 500 and a bad body → `LLMUnavailable`); the mock is deterministic.
- **Socket (in-process, `TestClient`):** origin, token, and missing/out-of-range level rejection; one voice turn with a scripted VAD, mock STT, mock LLM and mock TTS → `transcript`, one `reply`, N `audio` in order with matching `exchange`; `end` after `max_turns`; barge-in fires only inside the armed window and `played` disarms it; a new finished turn while a reply is in flight cancels the old task; LLM failure becomes an `error` and the socket keeps working. Every test sets `SALES_TRAINER_LLM`/`STT`/`TTS` through `monkeypatch`, so no default provider is ever constructed.
- **e2e (Playwright):** fake microphone and `SALES_TRAINER_LLM=mock`/`STT=mock`/`TTS=mock`; `/debug/chat`, one turn, the character's text appears, audio is produced, no console error.
- **Commands:** `uv run pytest`, `uv run pytest -m e2e`, `uv run ruff check .`.

## Risks And Mitigations

1. **No Anthropic key, so that client cannot be verified against the real API.** Mitigation: its payload and parsing are covered with `httpx.MockTransport`; the decision log records it as unverified. Nobody is blocked because the default provider is the OpenAI-compatible one.
2. **A local model can take longer than the 2.5 s target for a turn.** Mitigation: the turn is not blocked by anything else (TTS runs per sentence), the timeout is explicit, and latency is measured and recorded in Phase 8; `SALES_TRAINER_LLM_MODEL` allows a smaller model.
3. **Barge-in only works if the client reports `played`.** Mitigation: without it the window stays armed, so any speech still interrupts; the failure mode is an extra interruption, never a stuck socket.
4. **Sentence splitting is the seam between LLM and TTS, so a bad split is heard.** Mitigation: an explicit Spanish test with `¿?`, `¡!`, ellipsis, decimals and abbreviations.
5. **The character can hallucinate the product.** Mitigation: the system prompt states it knows only what the seller told it, and the brief is injected verbatim; the mock keeps the suite deterministic.
6. **`characters/` lives outside the package**, like `.env`. Mitigation: documented as a known limit; the suite runs from the source tree, and packaging the cards is a Phase 8 concern.
7. **The loop and the turn task both write to one socket.** Mitigation: the loop sends `transcript` and hands the turn over before the task starts, the task is the only sender of `reply`/`audio`, and `/ws/chat` does not send `level` at all, so no two paths write the same kind of message.
8. **One TTS call per sentence multiplies Azure round trips.** Mitigation: the prompt caps answers at 1-3 short sentences, playback starts with the first one, and the per-sentence cost is measured in Phase 8; a sentence-level cache is not built until then.

## Decision Summary

- A second socket `/ws/chat` carries the conversation; `/ws/stt` stays a transcription tool.
- Barge-in is decided by the server from the real VAD, inside a window the client opens and closes with `played`.
- Three YAML cards plus versioned prompt files, validated with pydantic at load.
- `LLMProvider` with `openai-compatible` (default), `anthropic` and `mock`; the two real clients are tested with an injected transport.
- One LLM reply per finished turn, split into sentences, one TTS call and one `audio` message per sentence.
- A new finished turn or a `barge_in` cancels the running reply task; `exchange` ids let the client drop audio it no longer wants.
- `product_brief` from the MCP tool and the level cards of the real page wait for Phase 6; this phase feeds `?product=` and `/debug/chat`.
- No streaming, no judge, no gauge: those belong to Phases 5 and 8.

## Open Questions

None blocking. Deferred: whether Phase 5 needs the LLM reply in streaming to keep the gauge responsive, and whether barge-in should also cut a sentence mid-audio or only between sentences.
