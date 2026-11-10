"""Judge provider test: mock judge against MockTransport."""
import pytest

from sales_trainer.judge import JudgeResult, get_judge_provider, JudgeProvider
from sales_trainer.judge.mock import MockJudgeProvider


def test_judge_result_has_scores_and_cause() -> None:
    provider = get_judge_provider("mock")
    result = provider.complete(
        system="You are a judge.",
        messages=["User: Hola, quiero ahorrar tiempo."],
    )
    assert isinstance(result, JudgeResult)
    assert isinstance(result.cause, str)
    assert len(result.scores) == 8
    for k, v in result.scores.items():
        assert 0 <= v <= 10, f"score {k}={v} out of range"


def test_judge_returns_eight_scores() -> None:
    provider = get_judge_provider("mock")
    result = provider.complete(
        system="You are a judge.",
        messages=[
            "User: Hola.",
            "User: Quiero ahorrar tiempo.",
            "User: Tengo objeciones al precio.",
        ],
    )
    assert len(result.scores) == 8
    for k, v in result.scores.items():
        assert isinstance(v, int) and 0 <= v <= 10


def test_unknown_judge_provider_raises() -> None:
    with pytest.raises(ValueError):
        get_judge_provider("nonexistent")
