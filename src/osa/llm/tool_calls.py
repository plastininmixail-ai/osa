"""Tool calling через OpenAI-совместимый API.

OpenAI-style: модель возвращает finish_reason="tool_calls" и
tool_calls[].function = {"name": ..., "arguments": "..."} (JSON-строка).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCallRequest:
    """Запрос на вызов инструмента от LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolCallResult:
    """Результат инструмента для отправки обратно в LLM."""

    tool_call_id: str
    name: str
    content: str  # сериализованный результат
