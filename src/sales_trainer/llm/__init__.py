import os
from sales_trainer.llm.base import LLMProvider, LLMUnavailable, Message, JudgeResult
from sales_trainer.llm.mock import MockProvider
from sales_trainer.llm.openai_compat import OpenAICompatProvider
from sales_trainer.llm.anthropic import AnthropicProvider
__all__ = [
    "LLMProvider",
    "LLMUnavailable",
    "Message",
    "get_llm_provider",
    "OpenAICompatProvider",
    "AnthropicProvider",
    "JudgeResult",
]


def get_llm_provider(name: str = None, mode: str = "general") -> "LLMProvider":
    name = name or os.getenv("SALES_TRAINER_LLM", "openai-compatible")
    name = name.strip().lower()
    if name == "mock":
        return MockProvider(mode=mode)
    if name == "openai-compatible":
        return OpenAICompatProvider()
    if name == "anthropic":
        return AnthropicProvider()
    raise ValueError(f"unknown LLM provider: {name}")


def get_judge_provider(name: str = None) -> "LLMProvider":
    name = name or os.getenv("SALES_TRAINER_JUDGE", "mock")
    name = name.strip().lower()
    if name == "mock":
        return get_llm_provider("mock", mode="judge")
    raise ValueError(f"unknown judge provider: {name}")
