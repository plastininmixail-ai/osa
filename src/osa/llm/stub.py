"""Stub LLM-провайдер для тестов.

Возвращает детерминированный ответ, не делает сетевых вызовов.
Используется в pytest и для локальной разработки без API-ключа.
"""

from __future__ import annotations

from osa.llm.base import LLMMessage, LLMProvider, LLMResponse


class StubProvider(LLMProvider):
    """Детерминированный провайдер для тестов и dev-режима."""

    def __init__(
        self,
        response_text: str = "Привет от stub!",
        tokens: int = 10,
    ) -> None:
        self.response_text = response_text
        self.tokens = tokens
        self.call_count = 0
        self.last_messages: list[LLMMessage] = []

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        self.call_count += 1
        self.last_messages = list(messages)
        return LLMResponse(
            content=self.response_text,
            tokens_used=self.tokens,
            model="stub-1",
        )
