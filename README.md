# sales-trainer-mcp

## Professional Overview

A Python-based Voice Sales Trainer application with 3D avatar, TTS (Text-to-Speech), STT (Speech-to-Text), LLM evaluation, and conversation loop management.

## Project Status: Phase 8 Complete

All 8 phases implemented:
- **Phase 0-3**: Pre-existing MCP skeleton, 3D avatar, TTS with visemes, microphone VAD/STT
- **Phase 4**: Characters, LLM and conversation loop ✅
- **Phase 5**: Evaluation engine and temperature ✅
- **Phase 6**: Full UI, gauge, reports ✅
- **Phase 7-8**: Polish, E2E, README and performance ✅

## Features

### Phase 4: Characters, LLM and Conversation Loop
- Three character cards (Marta, Javier, Carmen) with YAML configuration
- Spanish prompt files with level-specific rules
- LLM provider agnosticism (mock, openai-compatible, anthropic)
- WebSocket `/ws/chat` for conversation flow
- Barge-in detection and handling
- `/debug/chat` debugging page

### Phase 5: Evaluation Engine and Temperature
- Judge LLM evaluating each turn across 8 dimensions
- Temperature model with inertia and moving average
- Win/lose conditions based on threshold reaching
- Report generation in `.txt` format

### Phase 6: Full UI, Gauge, and Reports
- Level selection cards page (`/debug/levels`)
- Gauge visualization of temperature (canvas)
- Report generation and download
- Retry mechanic for continuous conversation

## Technical Details

### Architecture
- **FastAPI** 0.162 + Starlette backend
- **Python 3.12** with `uv` package manager
- **pydantic v2** for all data contracts
- **Playwright** for E2E testing (not Cypress)
- **Mock providers** for offline development (no API keys needed)

### Key Components
| Component | Description |
|-----------|-------------|
| `config/scoring.yaml` | Per-level weights and temperature parameters |
| `TemperatureModel` | Inertia-based temperature model [0-100] |
| `JudgeProvider` | 8-dimensional scoring (rubric) + delivery signals |
| `builder.build_judge_system_prompt()` | Generates system prompt from rubric + product brief |
| `/ws/chat` WebSocket | VAD, turn detection, judge call, gauge messages |
| `/debug/levels` | Level cards UI with gauge and report |

### Provider Agnosticism
All LLM/judge calls go through `get_judge_provider("mock")` by default,
enabling offline development and testing without network or API keys.
Real providers (openai, anthropic) can be configured via environment variables.

## Installation

```bash
uv sync
```

## Usage

```bash
# Start the server
uv run sales-trainer-mcp

# Run unit/integration tests
uv run pytest

# Run E2E tests
uv run pytest -m e2e

# Lint check
uv run ruff check .
```

## Available Scripts

| Command | Description |
|---------|-------------|
| `uv run pytest` | Run unit and integration tests |
| `uv run pytest -m e2e` | Run Playwright E2E tests |
| `uv run ruff check .` | Lint check (clean) |
| `uv run ruff check --fix .` | Auto-fix lint issues |
| `uv run pytest tests/e2e/` | Run specific E2E test file |

## Project Structure

```
sales-trainer-mcp/
├── src/
│   ├── sales_trainer/
│   │   ├── characters/        # YAML cards and Spanish prompts
│   │   ├── llm/               # LLM providers (mock, openai-compatible, anthropic)
│   │   ├── temperature/       # Temperature model with moving average
│   │   ├── eval/              # Judge rubric and builder
│   │   ├── chat.py            # Conversation logic (Conversation, Exchange, done_reason)
│   │   ├── web/
│   │   │   ├── app.py         # FastAPI application with all routes
│   │   │   ├── routes/        # WebSocket and route handlers
│   │   │   │   ├── chat_ws.py # /ws/chat handler
│   │   │   │   ├── stt_ws.py  # /ws/stt handler
│   │   │   │   └── levels.py  # /debug/levels route
│   │   ├── report.py          # .txt report generation
│   │   └── ...
├── config/
│   └── scoring.yaml           # Level-specific weights and thresholds
├── docs/
│   ├── decisions.md           # Phase close-out notes (21 decisions)
│   └── plans/                 # Implementation plans (18 tasks per phase)
├── tests/
│   ├── unit/                  # Unit and integration tests (79+ passing)
│   │   ├── test_judge.py
│   │   ├── test_temperature.py
│   │   ├── test_rubric.py
│   │   ├── test_report.py
│   │   └── test_characters.py
│   └── e2e/                   # End-to-end tests (Playwright)
│       ├── test_stt_page.py
│       ├── test_tts_page.py
│       ├── test_web_server.py
│       └── test_levels_page.py (new)
├── config/
│   └── scoring.yaml           # Level-specific weights and thresholds
└── README.md                  # This file
```

## Screenshots *(add actual screenshots below)*

### Level Selection Page
*(Add screenshot here: `![Level Selection](path/to/levels-screenshot.png)`)*

### Gauge Visualization
*(Add screenshot here: `![Gauge Display](path/to/gauge-screenshot.png)`)*

### Report Output
*(Add screenshot here: `![Report Output](path/to/report-screenshot.png)`)*

## Roadmap

| Phase | Status | Key Deliverables |
|-------|--------|-----------------|
| **Phase 4** | ✅ Complete | Characters, LLM, conversation loop |
| **Phase 5** | ✅ Complete | Judge, temperature model |
| **Phase 6** | ✅ Complete | UI, gauge, reports |
| **Phase 7** | ✅ Complete | Polish and performance |
| **Phase 8** | ✅ Complete | E2E, README, final state |

## Quick Start

```bash
# Install dependencies
uv sync

# Start the server
uv run sales-trainer-mcp

# Run tests
uv run pytest

# Run linter
uv run ruff check .
```

## Development Guide

See `docs/decisions.md` for:
- 21 documented design decisions across Phases 4-8
- Known limits and unverified assumptions
- Close-out notes for each phase

See `docs/superpowers/plans/` for:
- 18-task implementation plans per phase
- Checkbox tracking for task completion

## License

Proprietary - sales-trainer-mcp project