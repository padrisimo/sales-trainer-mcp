import json
from sales_trainer.judge.base import JudgeProvider, JudgeResult, JudgeUnavailable


class MockJudgeProvider(JudgeProvider):
    """A deterministic judge provider for tests and offline use.

    Returns fixed scores that gradually move toward the character's threshold,
    and delivery signals based on simple heuristics of the user's transcript.
    """

    # Per-level baseline scores that the judge starts from (0-10)
    BASELINE_SCORES = {
        "1": {  # Marta
            "value proposition": 6,
            "quantified time savings": 5,
            "quantified money savings": 5,
            "objection handling": 5,
            "questions and personalization": 7,
            "structure and clarity": 7,
            "closing or call to action": 5,
            "persuasive devices": 4,
        },
        "2": {  # Javier
            "value proposition": 5,
            "quantified time savings": 5,
            "quantified money savings": 5,
            "objection handling": 5,
            "questions and personalization": 5,
            "structure and clarity": 6,
            "closing or call to action": 5,
            "persuasive devices": 5,
        },
        "3": {  # Carmen
            "value proposition": 4,
            "quantified time savings": 4,
            "quantified money savings": 4,
            "objection handling": 4,
            "questions and personalization": 4,
            "structure and clarity": 5,
            "closing or call to action": 4,
            "persuasive devices": 3,
        },
    }

    def complete(self, system: str, messages: list[str]) -> JudgeResult:
        # Determine level from the most recent system prompt or messages
        # For simplicity, assume level 1 (Marta) unless we detect otherwise
        level_key = "1"  # default Marta

        # Extract the last user message
        last_user = ""
        for msg in reversed(messages):
            if "user" in msg.lower() or msg.startswith("User:"):
                # Grab content after "User:" or after the marker
                parts = msg.split(":", 1)
                if len(parts) == 2:
                    last_user = parts[1].strip()
                break

        # Start from baseline and nudge based on user text keywords
        scores = dict(self.BASELINE_SCORES[level_key])

        # Simple keyword nudges (very crude, just to have something move)
        text_lower = last_user.lower()
        if any(w in text_lower for w in ["ahorro", "tiempo", "minutes", "econom"]):
            scores["quantified time savings"] = min(10, scores["quantified time savings"] + 1)
            scores["quantified money savings"] = min(10, scores["quantified money savings"] + 1)
        if any(w in text_lower for w in ["objet", "problema", "solución"]):
            scores["objection handling"] = min(10, scores["objection handling"] + 1)
        if any(w in text_lower for w in ["pregunta", "personal", "interés"]):
            scores["questions and personalization"] = min(10, scores["questions and personalization"] + 1)
        if any(w in text_lower for w in ["figure", "datos", "porcentaje"]):
            scores["persuasive devices"] = min(10, scores["persuasive devices"] + 1)

        # Build a simple cause string
        active = [k for k, v in scores.items() if v >= 7]
        cause = (
            f"Reforzando {' '.join(active) if active else 'ninguna'} "
            f"basado en las señales del usuario."
        )

        # Delivery signals (simulated from "acoustic/transcription signals")
        delivery = {
            "diction": {"mean_prob": 0.85, "low_prob_pct": 12},
            "intonation": {"f0_std_semitones": 4.2, "monotony_index": 0.3},
            "pace": {"wpm": 145, "pauses_over_1p5s": 2},
            "fluency": {"repetitions": 0, "false_starts": 0},
            "eloquence": {"lexical_diversity": 0.42, "avg_sentence_len": 8},
        }

        return JudgeResult(scores=scores, delivery=delivery, cause=cause)
