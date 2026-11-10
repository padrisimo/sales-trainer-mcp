import os

import httpx

from sales_trainer.llm.base import LLMProvider, LLMUnavailable, Message


class OpenAICompatProvider(LLMProvider):
    """Provider for OpenAI-compatible APIs (Ollama, LM Studio, DeepSeek, OpenAI).

    POST {OPENAI_BASE_URL}/chat/completions
    The model and base URL are required; the API key is optional.
    The HTTP client is injectable via ``transport`` so both real providers
    are tested against ``httpx.MockTransport`` with no key.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
        transport: httpx.Client | httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL", "").rstrip("/")
        self.model = model or os.environ.get("SALES_TRAINER_LLM_MODEL", "").strip()
        self.timeout = timeout
        self._transport = transport

    def _client(self) -> httpx.Client:
        if self._transport is not None:
            # usuario proveyó un transport (síncrono); devolvemos un client que lo usa.
            return httpx.Client(timeout=self.timeout, transport=self._transport)
        return httpx.Client(timeout=self.timeout)

    def complete(self, system: str, messages: list[Message]) -> str:
        if not self.base_url:
            raise LLMUnavailable("OPENAI_BASE_URL is not set")
        if not self.model:
            raise LLMUnavailable("SALES_TRAINER_LLM_MODEL is not set")

        client = self._client()
        try:
            response = client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                    "stream": False,
                    "temperature": 0.7,
                },
            )
            if response.status_code != 200:
                raise LLMUnavailable(
                    f"HTTP {response.status_code}: {response.text}"
                )
            data = response.json()
            choice = data.get("choices", [{}])[0]
            text = choice.get("message", {}).get("content", "")
            if not text:
                raise LLMUnavailable("empty response from provider")
            return text
        except httpx.TimeoutException as exc:
            raise LLMUnavailable(f"timeout: {exc}") from exc
        except (ValueError, KeyError) as exc:
            raise LLMUnavailable(f"unparseable body: {exc}") from exc
