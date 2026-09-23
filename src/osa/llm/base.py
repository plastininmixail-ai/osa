"""Абстракция LLM-провайдера с поддержкой tool calling."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from osa.llm.tool_calls import ToolCallRequest


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str
    name: str | None = None
    # Tool message: results of tool execution
    tool_call_id: str | None = None
    # Assistant message: tool calls requested by model
    tool_calls: list[ToolCallRequest] | None = None


@dataclass(frozen=True)
class LLMResponse:
    content: str
    tokens_used: int
    model: str
    reasoning: str | None = None
    tool_calls: list[ToolCallRequest] | None = None
    finish_reason: str = "stop"  # "stop" | "tool_calls" | "length"
    raw: dict | None = None


@dataclass(frozen=True)
class ToolSpec:
    """Описание инструмента для передачи в LLM (OpenAI format)."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list[ToolSpec] | None = None,
    ) -> LLMResponse:
        """Сделать один вызов LLM. Может вернуть tool_calls."""


def resolve_api_key(config_value: str | None) -> str:
    """Получить API-ключ: сначала config, потом env."""
    return (
        config_value
        or os.environ.get("OSA_LLM__API_KEY")
        or os.environ.get("OSA_LLM_API_KEY")
        or ""
    )
