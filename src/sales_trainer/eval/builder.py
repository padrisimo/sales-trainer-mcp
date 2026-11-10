from __future__ import annotations

from sales_trainer.eval.rubric import DIMENSIONS, validate_scores


def build_judge_system_prompt(
    product_brief: str,
    character_card: dict,
    rubric_notes: bool = True,
) -> str:
    """Build the system prompt for the judge LLM.

    The prompt includes:
      - The character card (name, level, numbers from MEMORY.md §5)
      - The product brief (what the seller told the character)
      - The 8-dimension rubric with Spanish notes
      - Instructions: return strict JSON with scores 0-10 + cause string
    """
    lines: list[str] = []

    # Character info
    name = character_card.get("name", "el vendedor")
    level = character_card.get("level", 1)
    threshold = character_card.get("threshold", 75)
    max_turns = character_card.get("max_turns", 10)

    lines.append(f"Soy {name}, nivel {level}.")
    lines.append(f"Límite de turns: {max_turns}. Umbral de temperatura para ganar: {threshold}.")
    lines.append("")

    # Product brief
    lines.append("BRIEF DEL PRODUCTO:")
    lines.append(product_brief)
    lines.append("")

    # Rubric
    lines.append("RÚBRICA DE EVALUACIÓN (8 dimensiones, 0-10):")
    for i, dim in enumerate(DIMENSIONS, 1):
        lines.append(f"{i}. {dim.name}: {dim.note}")
    lines.append("")

    # Instructions
    lines.append("INSTRUCCIONES:")
    lines.append("- Devuelve SOLO un JSON con las siguientes claves:")
    lines.append("  \"scores\": { \"value proposition\": <0-10>, \"quantified time savings\": <0-10>, ...")
    lines.append("    (todas las 8 dimensiones)")
    lines.append("  \"cause\": \"<cadena natural explicando el resultado, para el gauge>\"")
    lines.append("- Las puntuaciones deben ser enteros de 0 a 10.")
    lines.append("- El campo `cause` debe ser una frase corta en español que explique ")
    lines.append("  por qué se dieron esas puntuaciones (para mostrarse en la gauge).")
    lines.append("")

    return "\n".join(lines)
