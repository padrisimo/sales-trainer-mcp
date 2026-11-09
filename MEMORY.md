# Sales Trainer MCP — prompt and memory for opencode / Claude Code

*Sales trainer with a 3D avatar, real-time voice and speech evaluation · Python · 2 November 2026*

How to use it: **Part 1** is the prompt you paste into opencode or Claude Code so it builds the project in phases. **Part 2** is the project memory (`AGENTS.md` for opencode, `CLAUDE.md` for Claude Code) that is stored in the repository root so the agent keeps the rules across sessions.

## Part 1 — Main prompt

### 1. Role and objective

Act as a senior full-stack engineer (Python + WebGL + real-time audio). Build from scratch a Python MCP server called `sales-trainer-mcp`: a **voice sales trainer**. When the user (from opencode or Claude Code) invokes the start tool, a browser window opens with a **3D avatar** acting as a potential customer. The user talks to it through the microphone, the avatar answers with synthesized voice moving its lips with **real visemes**, and the user must **convince it that the product will save it time and money**.

Persuasive content, **diction**, **intonation** and **eloquence** are evaluated. A UI shows a **success temperature gauge** that rises or falls during the conversation. At the end there is a result, options to **retry**, and a **downloadable text report** explaining what went well and what did not.

### 2. Architecture and stack

Organize the system like this:

```
opencode / Claude Code --stdio--> sales_trainer MCP server (FastMCP)
                                   | starts in a thread or child process
                                   v
                        FastAPI + uvicorn (127.0.0.1:PORT)
                                   | static HTTP + WebSocket
                                   v
                 Browser: Three.js + AudioWorklet + UI
```

Critical rule: with the stdio transport, **stdout is reserved for the MCP protocol**. All logs go to stderr or a file.

Proposed stack (check current versions in the official documentation and pin them in `pyproject.toml`; if there is a clearly better alternative, justify it in `docs/decisions.md`):

- **MCP**: official `mcp` SDK (FastMCP), stdio transport.
- **Backend**: FastAPI, uvicorn, WebSockets, pydantic v2, SQLite for the history.
- **STT**: `faster-whisper` (configurable model, CPU int8 by default, GPU if available) with per-word timestamps and probabilities. VAD with Silero.
- **Prosody**: `parselmouth` (Praat) or `librosa` (pyin) for F0, intensity and pauses.
- **TTS**: `TTSProvider` interface with two implementations (see section 3).
- **LLM**: `LLMProvider` interface with Anthropic and an OpenAI-compatible client (covers Ollama, LM Studio, DeepSeek and similar), configurable through environment variables. Structured JSON output validated with pydantic.
- **Frontend**: HTML + JS modules without a heavy framework, Three.js (plus `@pixiv/three-vrm` if VRM avatars are used) and AudioWorklet. JS dependencies pinned and served locally: **no CDN at runtime**, so it works offline.
- **Tooling**: `uv`, `ruff`, `pytest`, `pytest-asyncio`, Playwright.

Target folder structure:

```
sales-trainer-mcp/
  pyproject.toml, README.md, AGENTS.md / CLAUDE.md, .env.example
  config/scoring.yaml
  src/sales_trainer/
    mcp_server.py
    web/ (app.py, ws.py, static/ with index.html, js/, assets/)
    voice/ (stt.py, vad.py, prosody.py, visemes.py, tts/base.py, tts/azure.py, tts/local.py)
    llm/ (base.py, anthropic.py, openai_compat.py)
    characters/ (nivel1.yaml, nivel2.yaml, nivel3.yaml, prompts/)
    scoring/ (judge.py, delivery.py, temperature.py)
    reports/ (builder.py)
    storage/db.py
  tests/ (unit/, integration/, e2e/)
  docs/ (PLAN.md, decisions.md)
```

### 3. Voice: STT, TTS and real visemes

**Audio capture (browser → server)**

- `getUserMedia` with `echoCancellation` and `noiseSuppression` enabled.
- An AudioWorklet converts to PCM16 mono at 16 kHz and sends it over the WebSocket in 20–30 ms binary frames.
- Server-side VAD segments turns: the turn ends after about 700 ms of silence (configurable). Alternative push-to-talk mode. Text input as a fallback for debugging.
- **Barge-in**: if the user speaks while the avatar is talking, the avatar audio is cut and the interruption is recorded.
- Raw audio is **not stored** unless `SAVE_AUDIO=true`.

**STT**

- Transcribe with per-word timestamps and per-word probability. Store per turn: text, words with probability, duration, prosody metrics.

**TTS with real visemes**

- Every avatar line produces **audio + a viseme timeline**: `[{t_ms, viseme, weight}]`.
- "Real" means derived from the **phonemes actually spoken with their real timings in the audio**. Animating the mouth from audio amplitude or with random movement is forbidden.
- Internal viseme set: the 15 Oculus ones (`sil, PP, FF, TH, DD, kk, CH, SS, nn, RR, aa, E, I, O, U`). Implement mapping tables from Azure viseme IDs (0–21) and from Spanish IPA/espeak phonemes.
- Apply coarticulation (interpolation and smoothing between visemes) and mouth closure during silences.
- **Provider A, Azure Speech**: emits viseme events with audio offsets natively. Highest quality option, requires a key.
- **Provider B, local and offline** (Piper or Kokoro or another engine): get phonemes with durations if the library exposes them; if not, apply *forced alignment* over the generated audio (for example `ctc-forced-aligner`, Montreal Forced Aligner or WhisperX) and convert phoneme → viseme. **Before deciding, research in the current documentation what each library exposes and what exists for Spanish**, and document the decision and its limits in `docs/decisions.md`. This is the most delicate technical point of the project: validate it first with a prototype.
- **Synchronization**: the client plays through Web Audio and uses `AudioContext.currentTime` as the master clock. Maximum tolerated offset: 40 ms.
- **Target latency**: under 2.5 s from the moment the user stops speaking to the avatar's first audio. To achieve it: LLM in streaming and TTS per sentence.
- Default language Spain Spanish (`es-ES`), configurable. Voices and phoneme rules per language.

### 4. 3D avatar

- Three.js with GLB or VRM models. They must have Oculus viseme morph targets, or VRM expressions (`aa, ih, ou, ee, oh`) with a mapping table to our visemes.
- Idle animation: blinking, breathing, micro head movements and gaze.
- Reaction to the gauge state: high interest → smiles, nods, leans forward; low interest → serious gesture, averted gaze, crossed arms or a glance at the watch.
- **Three different avatars**, one per character. Do not use assets with dubious licensing: CC0 or own models, or procedural low-poly avatars with the same morph targets. Record the licenses in `assets/LICENSES.md`.
- Debug page `/debug/visemes` with one button per viseme and a test sentence to verify lip sync.

### 5. Characters and difficulty levels

Each character is a YAML card in `characters/` (personality, company context, typical objections, *hot buttons* that warm or cool it, its own filler words, TTS voice, avatar, numeric parameters) with its system prompt in a separate, versioned file. The names are suggestions and can be changed.

- **Level 1 — Easy: Marta Ruiz, receptive operations director.** Initial temperature 50, success threshold 75, maximum 10 turns. Patient and curious, asks reasonable questions and gives buying signals. Forgives a somewhat disorganized pitch but rewards concrete data.
- **Level 2 — Medium: Javier Soto, neutral and skeptical manager.** Start 30, threshold 80, maximum 10 turns. Raises typical objections (price, "I already have a vendor", "I don't have time to change systems"). Asks for examples and figures. Cools down with vagueness.
- **Level 3 — Hard: Carmen Valdés, uninterested CFO.** Start 10, threshold 85, maximum 8 turns. Says she only has two minutes, interrupts and answers curtly. Cools down with clichés, filler words, monotony and long speeches. Only warms up with quantified proposals (hours per week, euros per month, ROI, payback period), credible social proof and good discovery questions. If the temperature reaches 0, she hangs up.

Rules for the LLM playing the character:

- Never breaks character and never reveals the score or the temperature.
- Answers in spoken language: 1–3 short sentences (under 45 words at level 3).
- Knows nothing about the product beyond what the seller has told it.
- The product is defined by the user in a previous form (name, what it does, price, three benefits). There is a default demo product.

### 6. Evaluation engine and gauge

Every user turn is evaluated in **two independent layers**.

**A) Content and persuasion (LLM as judge).** A call **separate** from the character's, so the role does not contaminate the evaluation. The judge receives the transcript, the product brief and a rubric, and returns strict JSON with scores from 0 to 10 in:

- value proposition;
- quantified time savings;
- quantified money savings;
- objection handling;
- questions and personalization;
- structure and clarity;
- closing or call to action;
- persuasive devices (story, social proof, before/after contrast, figures).

**B) Delivery (measured signals, never invented by the LLM).**

- **Diction**: mean and percentage of words with low probability in Whisper; articulation speed.
- **Intonation**: F0 variation (standard deviation in semitones and range), monotony index, intensity dynamics, contour at sentence endings.
- **Pace and fluency**: words per minute (ideal 130–160), pauses over 1.5 s, filler words per minute (per-language list), repetitions and false starts.
- **Eloquence**: lexical diversity and average sentence length, combined with the persuasive devices detected by the judge.

Weights and thresholds live in `config/scoring.yaml`, **per level** (level 3 weights quantification and delivery more heavily).

**Temperature (0–100).** Per turn:

- `delta = (turn_score − 50) / 50 × character_sensitivity × max_delta`, with `max_delta` of ±15 per turn;
- inertia with a moving average to avoid sudden jumps;
- bonuses for hitting *hot buttons* and penalties for rambling, excessive filler words or interrupting the customer.

Every temperature change is stored with its cause in natural language (for example: "−8: generic claim without figures"), so it can be shown in the UI and in the report.

**End of the game.** Victory: reaching the threshold and holding it for two turns, or the character accepting a concrete next step. Defeat: temperature 0 (hangs up), turns exhausted or time exhausted.

### 7. UI flow, retries and reports

**Start screen**

- Three level cards with character, difficulty and tips.
- Product form.
- Microphone test with a level meter and permission handling.

**Session screen**

- Centered avatar and optional subtitles.
- Microphone button or push-to-talk.
- **Animated vertical gauge** with the threshold mark and cold, warm and hot zones.
- Turn and time counters.
- Discreet live indicators: pace, volume and filler words.
- End button.

**Result screen**

- Success or failure, temperature chart per turn and score per dimension.
- Three strengths and three areas to improve.
- Buttons: **Retry same level**, **Change level or character**, **Download report (.txt)** and **View history**.

**`.txt` report** (UTF-8, readable in any editor, not dependent on Markdown). It is always generated, and when the game is lost it focuses on **why it did not work**. Contents:

- header: date, level, character, product, duration, result and final temperature;
- temperature evolution per turn with an ASCII bar;
- score per dimension with its explanation;
- full transcript with timestamps;
- per-turn annotations (what helped and what cooled it down);
- critical moments;
- voice metrics;
- improvement plan with three concrete actions and suggested rewrites of the weakest sentences.

Endpoint: `GET /api/sessions/{id}/report.txt` with `Content-Disposition: attachment`.

**History** in SQLite, with comparison between attempts of the same level (improvement per dimension).

### 8. MCP tools

- `sales_trainer_start(level: 1|2|3, product_brief: str | None, language: str = "es")`: starts the web server if it is not active, opens the browser and returns the URL and the `session_id`.
- `sales_trainer_status(session_id)`: state, current turn and temperature.
- `sales_trainer_get_report(session_id)`: returns the text report and the file path.
- `sales_trainer_list_sessions(limit)`: summarized history.
- `sales_trainer_stop()`: closes the web server.

Each tool with a clear description, a typed input schema and readable errors.

### 9. Configuration, installation and security

- Documented `.env.example`: LLM provider and model, keys, TTS provider, Whisper model, port, language and `SAVE_AUDIO`.
- Registration in **opencode** (`opencode.json`):

```json
{
  "mcp": {
    "sales-trainer": {
      "type": "local",
      "command": ["uv", "run", "sales-trainer-mcp"],
      "enabled": true
    }
  }
}
```

- Registration in **Claude Code**: `claude mcp add sales-trainer -- uv run sales-trainer-mcp`.
- Web server only on `127.0.0.1`, random session token in the URL and `Origin` validation on the WebSocket.
- All processing is local by default; the cloud is only used if the user configures cloud provider keys.

### 10. Quality and testing

- **Unit**: viseme tables, temperature engine (with simulated, deterministic scores), prosody metrics with synthetic audio, report builder and validation of the YAML cards.
- **Integration**: WebSocket with sample audio → transcription → response with a mocked LLM.
- **E2E with Playwright** (Chromium with a fake microphone: `--use-fake-device-for-media-stream` and `--use-file-for-fake-audio-capture=<wav>`), with mocked LLM and TTS providers: full level 1 flow down to the report download.
- **Mock providers** to run everything without keys or network.
- `ruff` and *type hints* across all the code. README with a five-step installation and a troubleshooting section (microphone permissions, ports, models).

### 11. How to work

1. Start by writing `docs/PLAN.md` with architecture, decisions and risks (especially the local visemes). Only stop to ask on a real blocker; for every other doubt, choose the simplest option that meets the criteria and record it in `docs/decisions.md`.
2. Work in vertical phases, one commit per phase and tests green before moving to the next:
   - **Phase 0**: MCP skeleton, FastAPI and browser opening. Criterion: `sales_trainer_start` opens a page and returns the URL.
   - **Phase 1**: 3D avatar with idle and `/debug/visemes` panel. Criterion: every viseme looks correct.
   - **Phase 2**: TTS with a synchronized viseme timeline. Criterion: a Spanish sentence is spoken with coherent lips, offset ≤ 40 ms.
   - **Phase 3**: microphone, VAD and STT with timestamps and probabilities. Criterion: correct Spanish transcription with well-segmented turns.
   - **Phase 4**: characters with LLM and the conversation loop with barge-in.
   - **Phase 5**: evaluation engine (judge + delivery) and temperature.
   - **Phase 6**: full UI (levels, gauge, result, retry).
   - **Phase 7**: `.txt` reports, history and the remaining MCP tools.
   - **Phase 8**: E2E tests, README, polish and performance.
3. Do not invent APIs: read the current documentation of each library and pin versions. At the end of every phase, update the "Status" section of the project memory.

### 12. Acceptance criteria

- From opencode or Claude Code, a call to `sales_trainer_start` opens the browser and allows a complete spoken conversation.
- The lips follow the real phonemes of the audio (no amplitude animation) with an offset ≤ 40 ms.
- The three levels behave in clearly different ways and level 3 is hard to win without figures and good delivery.
- The gauge reacts turn by turn and every change has an explained cause.
- After winning or losing, the user can retry and download the `.txt` report.
- The whole test suite passes without keys or network, and at least one E2E of the full flow exists.
