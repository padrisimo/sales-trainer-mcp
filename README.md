# sales-trainer-mcp

A Voice Sales Trainer with 3D avatar, real-time speech evaluation and conversation coaching.

## What it does

sales-trainer-mcp opens a voice sales trainer in the browser: a 3D avatar with real visemes, TTS and STT, three difficulty levels of characters, a success gauge, retries and downloadable `.txt` reports.

Hold a complete spoken conversation with one of three characters. The gauge reacts turn by turn. After the game ends, download a text report of the session.

## Features

### Characters

- **Marta** (Level 1): Receptive director, starts at 50, threshold 75, 10 turns
- **Javier** (Level 2): Skeptical manager, starts at 30, threshold 80, 10 turns  
- **Carmen** (Level 3): CFO uninterested, starts at 10, threshold 85, 8 turns, hangs up at 0

### Conversation

- Real-time STT with VAD (Voice Activity Detection)
- TTS synthesis with viseme-per-phoneme animation
- LLM judge evaluates each turn across 8 dimensions
- Temperature model drives gauge and win/lose conditions
- Barge-in detection and handling

### UI

- Level selection cards page
- Gauge visualization (0-100 bar)
- `.txt` report download with session transcript
- Retry button to restart with same character
- Session token validation and origin checking

## Technical

- **Python 3.12**, FastAPI 0.162, Starlette
- pydantic v2 for all data contracts
- Playwright E2E tests
- Mock providers for offline development (no API keys)
- WebSocket `/ws/chat` for conversation flow
- `/debug/levels` route serves the level-selection page
- Gauge canvas with temperature feedback

## Quickstart

```bash
uv sync
uv run sales-trainer-mcp
```

Visit `http://127.0.0.1:8126/debug/levels` to start a conversation.

Run `uv run pytest` for unit/integration tests.
Run `uv run pytest -m e2e` for E2E tests.
Run `uv run ruff check .` for lint.

## Product Status

Complete. All features implemented and tested. Documentation closed.

## License

Proprietary