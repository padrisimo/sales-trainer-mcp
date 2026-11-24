from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TurnInfo:
    """Info about one turn in the conversation."""
    user_text: str
    words: list[str]
    audio_ms: int
    temperature: int
    cause: str
    judge_scores: dict[str, int] = field(default_factory=dict)


@dataclass
class Report:
    """Structured report of a conversation session."""
    session_token: str
    character_level: int
    character_name: str
    max_turns: int
    turns: list[TurnInfo] = field(default_factory=list)
    final_temperature: int = 50
    final_cause: str = ""
    won: bool = False


def generate_report(report: Report) -> str:
    """Return a ``.txt`` report string from a ``Report`` dataclass."""
    lines: list[str] = []

    lines.append("=" * 50)
    lines.append("REPORTE DE SESIÓN SALES TRAINER")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"Token de sesión: {report.session_token}")
    lines.append(f"Personaje: Nivel {report.character_level} - {report.character_name}")
    lines.append(f"Límites: max_turns = {report.max_turns}")
    lines.append("")

    lines.append("HISTORIAL DE TURNOS")
    lines.append("-" * 40)
    for i, t in enumerate(report.turns, 1):
        lines.append(f"--- Turno {i} ---")
        lines.append(f"Texto usuario: {t.user_text}")
        lines.append(f"Palabras: {', '.join(t.words) if t.words else '—'}")
        lines.append(f"Audio (ms): {t.audio_ms}")
        lines.append(f"Temperatura: {t.temperature}°C")
        lines.append(f"Causa: {t.cause}")
        if t.judge_scores:
            lines.append("Puntuaciones juez:")
            for dim, score in t.judge_scores.items():
                lines.append(f"  {dim}: {score}/10")
        lines.append("")

    lines.append("RESULTADO FINAL")
    lines.append("-" * 40)
    lines.append(f"Temperatura final: {report.final_temperature}°C")
    lines.append(f"Causa final: {report.final_cause}")
    if report.won:
        lines.append("Resultado: VICTORIA (temperature ≥ umbral 2 turnos consecutivos)")
    else:
        lines.append("Resultado: DERROTA (temperature 0 o turns agotados)")

    lines.append("")
    lines.append("=" * 50)
    return "\n".join(lines)
