from __future__ import annotations

from typing import Sequence


class JudgeResult:
    """Result of a judge call.

    Attributes:
        scores: dict mapping dimension name (str) to int 0-10
        delivery: dict with measured signals (diction, intonation, pace, fluency, eloquence)
        cause: natural language explanation of the result (for the gauge UI)
    """

    def __init__(
        self,
        scores: dict[str, int],
        delivery: dict[str, object | float | int | None] | None = None,
        cause: str | None = None,
    ) -> None:
        self.scores = scores
        self.delivery = delivery or {}
        self.cause = cause


class JudgeProvider:
    """Interface for a judge LLM provider.

    The judge evaluates a completed user turn and returns scores 0-10 for
    eight dimensions of content and persuasion, plus delivery signals and
    a natural-language cause string for the gauge UI.

    Implementations must provide a ``complete`` method that receives:
      - system: the system prompt (character card + product brief + rubric)
      - messages: the conversation messages so far
    And returns a ``JudgeResult`` instance.
    """

    def complete(self, system: str, messages: Sequence[str]) -> JudgeResult:
        raise NotImplementedError("Subclasses must implement complete()")


class JudgeUnavailable(RuntimeError):
    """Raised when the judge provider cannot answer (missing key, network error, etc.)."""
