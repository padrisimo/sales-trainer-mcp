"""Rubric and builder test."""
import pytest

from sales_trainer.eval.rubric import DIMENSIONS, validate_scores


def test_eight_dimensions() -> None:
    assert len(DIMENSIONS) == 8


def test_dimension_names() -> None:
    expected = [
        "value proposition",
        "quantified time savings",
        "quantified money savings",
        "objection handling",
        "questions and personalization",
        "structure and clarity",
        "closing or call to action",
        "persuasive devices",
    ]
    actual = [d.name for d in DIMENSIONS]
    assert actual == expected


def test_validate_scores() -> None:
    validate_scores({
        "value proposition": 6,
        "quantified time savings": 5,
        "quantified money savings": 5,
        "objection handling": 5,
        "questions and personalization": 7,
        "structure and clarity": 7,
        "closing or call to action": 5,
        "persuasive devices": 4,
    })


def test_validate_scores_bad_keys() -> None:
    with pytest.raises(ValueError):
        validate_scores({"bad": 5})


def test_validate_scores_out_of_range() -> None:
    with pytest.raises(ValueError):
        validate_scores({"value proposition": 15})


def test_builder_prompt_has_key_elements() -> None:
    from sales_trainer.eval.builder import build_judge_system_prompt
    prompt = build_judge_system_prompt(
        product_brief="Venta de software de gestión para pymes",
        character_card={"name": "Marta", "level": 1, "threshold": 75, "max_turns": 10},
    )
    assert "Marta" in prompt
    assert "nivel 1" in prompt
    assert "75" in prompt
    assert "Venta de software" in prompt
    assert "value proposition" in prompt
    assert "persuasive devices" in prompt
