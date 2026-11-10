from collections.abc import Sequence

from sales_trainer.llm.base import LLMProvider, Message


class MockProvider(LLMProvider):
    """A deterministic LLM provider for tests and offline use."""

    def complete(self, system: str, messages: Sequence[object]) -> str:
        # Normalise dict-style messages to Message objects
        normalized: list[Message] = []
        for msg in messages:
            if isinstance(msg, Message):
                normalized.append(msg)
            elif isinstance(msg, dict):
                normalized.append(Message(role=msg["role"], content=msg["content"]))
            else:
                raise TypeError(f"unexpected message type: {type(msg)}")

        # Use the last user message to build a deterministic reply
        last_user = ""
        for msg in reversed(normalized):
            if msg.role == "user":
                last_user = msg.content
                break

        if "hello" in last_user.lower():
            return "Hello, how can I help you today?"
        if "cómo" in last_user.lower() or "how are" in last_user.lower():
            return "I'm doing well, thank you for asking!"
        return "I understand. Please tell me more."
