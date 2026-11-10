from collections.abc import Sequence
from sales_trainer.llm.base import LLMProvider, Message, JudgeResult


class MockProvider(LLMProvider):
    """A deterministic LLM provider for tests and offline use.

    Two modes:
    - General mode: returns a string reply (used by the character conversation).
    - Judge mode: returns a JudgeResult with scores 0-10 and a cause string
      (used by the evaluation pipeline).
    """

    def __init__(self, mode: str = "general") -> None:
        self.mode = mode

    def complete(self, system: str, messages: Sequence[object]) -> str | JudgeResult:
        # Normalise dict-style messages to Message objects
        normalized: list[Message] = []
        for msg in messages:
            if isinstance(msg, Message):
                normalized.append(msg)
            elif isinstance(msg, dict):
                normalized.append(Message(role=msg["role"], content=msg["content"]))
            else:
                raise TypeError(f"unexpected message type: {type(msg)}")

        # Use the last user message to build a response
        last_user = ""
        for msg in reversed(normalized):
            if msg.role == "user":
                last_user = msg.content
                break

        if self.mode == "judge":
            # Return structured judge result
            text = last_user.lower()
            # Simple keyword-based scoring for demo purposes
            scores = {
                "value proposition": 6,
                "quantified time savings": 5 if "ahorro" in text or "time" in text else 4,
                "quantified money savings": 5 if "econom" in text or "money" in text else 4,
                "objection handling": 5 if "objet" in text or "problema" in text else 4,
                "questions and personalization": 7 if "pregunta" in text or "personal" in text else 5,
                "structure and clarity": 7,
                "closing or call to action": 5,
                "persuasive devices": 4 if any(w in text for w in ["figura", "dato", "%"]) else 3,
            }
            delivery = {
                "diction": {"mean_prob": 0.85, "low_prob_pct": 12},
                "intonation": {"f0_std_semitones": 4.2, "monotony_index": 0.3},
                "pace": {"wpm": 145, "pauses_over_1p5s": 2},
                "fluency": {"repetitions": 0, "false_starts": 0},
                "eloquence": {"lexical_diversity": 0.42, "avg_sentence_len": 8},
            }
            cause = (
                f"Basado en las señal{'s' if len(text) > 5 else ''} del usuario: "
                f"'{text[:40]}...'. "
                f"Puntuaciones: {', '.join(f'{k}={v}' for k, v in scores.items())}."
            )
            return JudgeResult(scores=scores, delivery=delivery, cause=cause)

        # General mode: return a string
        if "hello" in last_user.lower() or last_user.strip() == "Hello":
            return "Hello, how can I help you today?"
        if "cómo" in last_user.lower() or "how are" in last_user.lower():
            return "I'm doing well, thank you for asking!"
        return "I understand. Please tell me more."
