"""Stub LLM-провайдер для тестов и dev-режима.

Может имитировать ответы с tool_calls через предзаданные сценарии.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from osa.llm.base import LLMMessage, LLMProvider, LLMResponse, ToolSpec
from osa.llm.tool_calls import ToolCallRequest


@dataclass
class StubResponse:
    """Один шаг stub-сценария."""

    content: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    tokens: int = 10


class StubProvider(LLMProvider):
    """Stub с предзаданным сценарием ответов.

    Использование:
        provider = StubProvider(scenario=[
            StubResponse(tool_calls=[ToolCallRequest("c1", "file_read", {"path": "x.txt"})]),
            StubResponse(content="Файл прочитан"),
        ])
        r1 = provider.complete(...)  # вернёт tool_calls
        r2 = provider.complete(...)  # вернёт content
    """

    def __init__(
        self,
        scenario: list[StubResponse] | None = None,
        default_response_text: str = "Привет от stub!",
        tokens: int = 10,
    ) -> None:
        self.scenario = scenario or []
        self.default_response_text = default_response_text
        self.tokens = tokens
        self.call_count = 0
        self.last_messages: list[LLMMessage] = []

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list[ToolSpec] | None = None,
    ) -> LLMResponse:
        self.call_count += 1
        self.last_messages = list(messages)

        if self.call_count <= len(self.scenario):
            step = self.scenario[self.call_count - 1]
            return LLMResponse(
                content=step.content,
                tokens_used=step.tokens,
                model="stub-1",
                tool_calls=step.tool_calls or None,
                finish_reason="tool_calls" if step.tool_calls else "stop",
            )

        return LLMResponse(
            content=self.default_response_text,
            tokens_used=self.tokens,
            model="stub-1",
            finish_reason="stop",
        )
