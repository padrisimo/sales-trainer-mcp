import os

from sales_trainer.llm.anthropic import AnthropicProvider
from sales_trainer.llm.base import LLMProvider, LLMUnavailable, Message
from sales_trainer.llm.mock import MockProvider
from sales_trainer.llm.openai_compat import OpenAICompatProvider

__all__ = [
    "AnthropicProvider",
    "LLMProvider",
    "LLMUnavailable",
    "Message",
    "OpenAICompatProvider",
    "get_llm_provider",
]


def get_llm_provider(name: str = None) -> "LLMProvider":
    name = name or os.getenv("SALES_TRAINER_LLM", "openai-compatible")
    name = name.strip().lower()
    if name == "mock":
        return MockProvider()
    if name == "openai-compatible":
        return OpenAICompatProvider()
    if name == "anthropic":
        return AnthropicProvider()
    raise ValueError(f"unknown LLM provider: {name}")
