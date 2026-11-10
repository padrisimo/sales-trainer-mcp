from sales_trainer.judge.base import JudgeProvider, JudgeUnavailable, JudgeResult
from sales_trainer.judge.mock import MockJudgeProvider


def get_judge_provider(name: str = None) -> JudgeProvider:
    name = name or __import__("os").getenv("SALES_TRAINER_JUDGE", "mock")
    name = name.strip().lower()
    if name == "mock":
        return MockJudgeProvider()
    raise ValueError(f"unknown judge provider: {name}")


__all__ = ["JudgeProvider", "JudgeUnavailable", "JudgeResult", "get_judge_provider"]
