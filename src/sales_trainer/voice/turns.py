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
