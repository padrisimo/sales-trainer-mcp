from pathlib import Path
from typing import TypedDict

from pydantic import BaseModel, Field, validator


class CharacterUnavailable(RuntimeError):
    """Raised when the card cannot be loaded for the given level."""


class CharacterCard(TypedDict):
    level: int
    name: str
    voice: str
    start_temperature: int
    threshold: int
    max_turns: int
    prompt: str
    objections: list[str]
    hot_buttons: list[str]
    cold_buttons: list[str]
    filler_words: list[str]


class _CardData(BaseModel):
    level: int = Field(ge=1, le=3)
    name: str
    voice: str
    start_temperature: int = Field(ge=0, le=100)
    threshold: int = Field(ge=0, le=100)
    max_turns: int = Field(ge=1, le=50)
    prompt: str
    objections: list[str]
    hot_buttons: list[str]
    cold_buttons: list[str]
    filler_words: list[str]

    @validator("prompt")
    def prompt_must_exist(cls, v: str) -> str:
        if not Path(v).is_file():
            raise ValueError(f"prompt file not found: {v}")
        return v


def load_character(level: int) -> CharacterCard:
    """Load and validate a character card by level (1-3)."""
    mapping = {
        "1": {"level": 1, "name": "Marta Ruiz", "voice": "es-ES-ElviraNeural",
              "start_temperature": 50, "threshold": 75, "max_turns": 10,
              "prompt": "characters/prompts/nivel1.md",
              "objections": ["No sé si mi equipo tendrá tiempo para aprender otra herramienta.",
                             "Ahora mismo lo hacemos con hojas de cálculo y nos vale."],
              "hot_buttons": ["Ahorro de tiempo medible por semana",
                            "Casos parecidos en empresas de reparto"],
              "cold_buttons": ["Precios sin cifras de retorno",
                              "Discursos largos y genéricos"],
              "filler_words": ["A ver", "Claro, claro"]},
        "2": {"level": 2, "name": "Javier Soto", "voice": "es-ES-AlvaroNeural",
              "start_temperature": 30, "threshold": 80, "max_turns": 10,
              "prompt": "characters/prompts/nivel2.md",
              "objections": ["Ya trabajo con otro proveedor y cambiar ahora me cuesta dinero.",
                             "No tengo tiempo para migrar los datos.",
                             "Eso suena bien, pero necesito números."],
              "hot_buttons": ["Ejemplos reales con cifras",
                            "Una migración sin parar la operación"],
              "cold_buttons": ["Vaguezas y promesas sin datos",
                              "Presentaciones largas"],
              "filler_words": ["Ya, ya", "Hombre, depende"]},
        "3": {"level": 3, "name": "Carmen Valdés", "voice": "es-ES-XimenaNeural",
              "start_temperature": 10, "threshold": 85, "max_turns": 8,
              "prompt": "characters/prompts/nivel3.md",
              "objections": ["Solo tengo dos minutos, dígame lo esencial.",
                             "No veo por qué debería cambiar nada.",
                             "Eso ya lo he oído antes."],
              "hot_buttons": ["Horas ahorradas por semana y euros al mes",
                            "Retorno de la inversión y plazo de recuperación"],
              "cold_buttons": ["Clichés y palabras de relleno",
                              "Monotonía y discursos largos"],
              "filler_words": ["Mmm", "Vamos al grano"]},
    }
    try:
        data = mapping[str(level)]
        card = _CardData(**data)
    except Exception as exc:
        raise CharacterUnavailable from exc
    base = card.model_dump()
    return {k: base[k] for k in CharacterCard.__annotations__}
