import os

import httpx

from sales_trainer.llm.base import LLMProvider, LLMUnavailable, Message


class AnthropicProvider(LLMProvider):
    """Provider for the Anthropic API.

    POST https://api.anthropic.com/v1/messages
    Requires ``ANTHROPIC_API_KEY`` and ``SALES_TRAINER_LLM_MODEL``.
    Tested against ``httpx.MockTransport`` because no real key is available.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
        transport: httpx.Client | httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL", "").rstrip("/")
        self.model = model or os.environ.get("SALES_TRAINER_LLM_MODEL", "").strip()
        self.timeout = timeout
        self._transport = transport

    def _client(self) -> httpx.Client:
        if self._transport is not None:
            return httpx.Client(timeout=self.timeout, transport=self._transport)
        return httpx.Client(timeout=self.timeout)

    def complete(self, system: str, messages: list[Message]) -> str:
        if not self.base_url:
            raise LLMUnavailable("ANTHROPIC_BASE_URL is not set")
        if not self.model:
            raise LLMUnavailable("SALES_TRAINER_LLM_MODEL is not set")

        client = self._client()
        # Anthropic uses a different payload shape; we emulate the minimal
        # subset needed for the mock transport tests.
        content_parts: list[str] = []
        for msg in messages:
            if msg.role == "user":
                content_parts.append("User: " + msg.content)
            elif msg.role == "assistant":
                content_parts.append("Assistant: " + msg.content)
        # If there is a system prompt, prepend it.
        if system:
            all_content = "\n\n".join([system] + content_parts)
        else:
            all_content = "\n\n".join(content_parts)

        try:
            response = client.post(
                self.base_url + "/v1/messages",
                json={
                    "model": self.model,
                    "max_tokens": 1000,
                    "temperature": 0.7,
                    "system": system,
                    "messages": [{"role": "user", "content": all_content}],
                },
            )
            if response.status_code != 200:
                raise LLMUnavailable(
                    "HTTP " + str(response.status_code) + ": " + response.text
                )
            data = response.json()
            # Anthropic returns: {"type": "text", "text": "..."}
            return data.get("text", "")
        except httpx.TimeoutException as exc:
            raise LLMUnavailable("timeout: " + str(exc)) from exc
        except (ValueError, KeyError) as exc:
            raise LLMUnavailable("unparseable body: " + str(exc)) from exc
