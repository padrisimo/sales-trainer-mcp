from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from sales_trainer.eval.rubric import validate_scores
from sales_trainer.llm import get_judge_provider, Message
from sales_trainer.llm.base import JudgeResult
from sales_trainer.temperature.model import TemperatureModel


class Exchange:
    """One finished turn in the conversation."""
    def __init__(
        self,
        user_text: str,
        words: list[str],
        audio_ms: int,
        reply: str | None = None,
        interrupted: bool = False,
        judge_result: JudgeResult | None = None,
    ) -> None:
        self.user_text = user_text
        self.words = words
        self.audio_ms = audio_ms
        self.reply = reply
        self.interrupted = interrupted
        self.judge_result = judge_result


class Conversation:
    """Hold the conversation state per session."""
    def __init__(self, character: dict, product_brief: str = "") -> None:
        self.character = character
        self.product_brief = product_brief
        self.exchanges: list[Exchange] = []
        self.turns = 0
        self.max_turns = character.get("max_turns", 10)
        self.current_temp = 50
        self.last_cause = "inicio de conversación"

    def add_exchange(
        self,
        user_text: str,
        words: list[str],
        audio_ms: int,
        reply: str | None = None,
        interrupted: bool = False,
    ) -> Exchange:
        """Record a finished user turn and return the Exchange."""
        exchange = Exchange(
            user_text=user_text,
            words=words,
            audio_ms=audio_ms,
            reply=reply,
            interrupted=interrupted,
        )
        self.exchanges.append(exchange)
        self.turns += 1
        return exchange


def split_sentences(text: str) -> list[str]:
    """Cut Spanish text after . ! ? … without breaking decimals, thousands or abbreviations."""
    SENTENCE_ENDINGS = ".!?…"
    ABBREVIATIONS = ("Sr.", "Sra.", "Dr.", "Ud.", "Uds.", "p. ej.", "EE. UU.")

    def _inside_abbreviation(text: str, start: int, end: int) -> bool:
        for abbreviation in ABBREVIATIONS:
            if end - start >= len(abbreviation) and text[end - len(abbreviation) : end] == abbreviation:
                return True
            for offset in range(max(start, end - len(abbreviation)), end):
                if text[offset:end] == abbreviation[: end - offset]:
                    return True
        return False

    sentences: list[str] = []
    start = 0
    index = 0
    while index < len(text):
        if text[index] not in SENTENCE_ENDINGS:
            index += 1
            continue
        end = index + 1
        while end < len(text) and text[end] in SENTENCE_ENDINGS:
            end += 1
        index = end
        if index < len(text) and not text[index].isspace():
            continue  # decimal or thousands separator
        if _inside_abbreviation(text, start, end):
            continue
        candidate = text[start:end].strip()
        if candidate:
            sentences.append(candidate)
        start = index
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def begin(
    conversation: Conversation,
    user_text: str,
    words: list[str],
    audio_ms: int,
) -> Exchange:
    """Start a new exchange: record the user turn.

    Returns the Exchange object. The judge call and temperature update
    should be triggered by the WebSocket handler after turn_end, via
    call_judge_for_exchange().
    """
    exchange = conversation.add_exchange(user_text, words, audio_ms)
    return exchange


def call_judge_for_exchange(
    exchange: Exchange,
    conversation: Conversation,
    temperature_model: TemperatureModel,
) -> None:
    """Call the judge LLM for this exchange, update temperature.

    This is meant to be called from the WebSocket handler after
    turn_end, in a thread or via asyncio.to_thread so it doesn't
    block the receive loop.
    """
    async def _run_judge() -> None:
        try:
            provider = get_judge_provider("mock")
            from sales_trainer.eval.builder import build_judge_system_prompt
            system = build_judge_system_prompt(
                product_brief=conversation.product_brief,
                character_card=conversation.character,
            )
            # Build messages as Message objects
            messages: list[Message] = []
            for ex in conversation.exchanges:
                messages.append(Message(role="user", content=ex.user_text))
            messages.append(Message(role="user", content=exchange.user_text))

            result: JudgeResult = provider.complete(system=system, messages=messages)  # type: ignore
            validate_scores(result.scores)

            conversation.last_cause = result.cause or "sin causa"
            # Simplified temperature update using value proposition score
            vp_score = result.scores.get("value proposition", 5)
            temperature_model.update(vp_score)

            exchange.judge_result = result
        except Exception as exc:  # noqa: BLE001
            exchange.judge_result = None
            conversation.last_cause = f"judge error: {exc}"

    # Schedule the judge call; if we're inside an event loop, create_task,
    # otherwise run it synchronously (for test contexts).
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run_judge())
    except RuntimeError:
        # No running loop — run synchronously for test contexts
        asyncio.run(_run_judge())
