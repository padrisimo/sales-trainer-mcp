from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

# The 8 dimensions of the judge's rubric, with Spanish notes for the prompt.
# Each dimension is scored 0-10 by the LLM judge.

@dataclass
class Dimension:
    name: str
    # Spanish prompt note: what the judge should look for
    note: str
    # Weight per level (from config/scoring.yaml); None means "not used for this dimension"
    level_weights: Dict[str, float] = field(default_factory=dict)


# The eight dimensions, in the order the judge should evaluate them.
# The judge's `complete` method must return a dict with these eight keys,
# each mapping to an int 0-10.
DIMENSIONS: List[Dimension] = [
    Dimension(
        name="value proposition",
        note="Proposición de valor: comunica claramente qué beneficios aporta el producto/servicio. "
             "Se diferencia de la competencia?",
    ),
    Dimension(
        name="quantified time savings",
        note="Ahorro de tiempo cuantificado: menciona ahorro de horas por semana/día? "
             "Es un número concreto o una estimación vaga?",
    ),
    Dimension(
        name="quantified money savings",
        note="Ahorro de dinero cuantificado: menciona ahorro en euros/dólares? "
             "ROI, payback period o cifra de coste reducido?",
    ),
    Dimension(
        name="objection handling",
        note="Manejo de objeciones: supera las objeciones del cliente (precio, vendor actual, falta de tiempo)? "
             "Con datos o con argumentos genéricos?",
    ),
    Dimension(
        name="questions and personalization",
        note="Preguntas y personalización: hace preguntas relevativas al cliente? "
             "Referencia necesidades específicas o situación de la empresa?",
    ),
    Dimension(
        name="structure and clarity",
        note="Estructura y claridad: intervención bien organizada? Ideas fluyen lógicamente? "
             "Claridad en el mensaje?",
    ),
    Dimension(
        name="closing or call to action",
        note="Cierre o llamada a la acción: hay un cierre claro? Pide próxima reunión, demo, pedido?",
    ),
    Dimension(
        name="persuasive devices",
        note="Dispositivos persuasivos: usa historias, pruebas sociales, contraste antes/después, figuras o datos concretos? "
        "En level 3 pesa más que en level 1.",
    ),
]


def validate_scores(scores: dict[str, int]) -> None:
    """Validate that the judge returned exactly 8 scores, each 0-10."""
    expected = {d.name for d in DIMENSIONS}
    if set(scores.keys()) != expected:
        raise ValueError(f"Expected 8 dimensions {expected}, got {set(scores.keys())}")
    for k, v in scores.items():
        if not isinstance(v, int) or v < 0 or v > 10:
            raise ValueError(f"Score for {k} must be int 0-10, got {v}")
