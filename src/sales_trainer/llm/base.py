from __future__ import annotations

from typing import Sequence


class Message:
    """A message in an LLM conversation.

    Attributes:
        role: Either "user" or "assistant".
        content: The text of the message.
    """

    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content


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


class LLMProvider:
    """Interface for an LLM provider.

    Implementers must provide a ``complete`` classmethod (or instance method)
    that returns the model's reply as a plain string.

    .. code-block:: python

        provider = MockProvider()
        reply = provider.complete(
            system="You are helpful.",
            messages=[Message(role="user", content="Hi")]
        )
    """

    def complete(self, system: str, messages: Sequence[Message]) -> str:
        raise NotImplementedError


class LLMUnavailable(RuntimeError):
    """Raised when the provider cannot answer (missing key, network error, etc.)."""
