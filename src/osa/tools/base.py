"""Базовый класс Tool.

Tool — это callable с метаданными для LLM:
- name: уникальный идентификатор
- description: что делает (LLM читает это, чтобы решить когда вызвать)
- params_schema: JSON Schema для параметров (LLM валидирует свой tool_call)
- requires_confirmation: если True, CLI спрашивает пользователя перед run()

Реальные инструменты (FileRead, Shell, ...) живут в src/osa/tools/builtin.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Результат выполнения инструмента."""

    success: bool
    output: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Tool(ABC):
    """Базовый класс инструмента."""

    name: str
    description: str
    params_schema: dict[str, Any]
    requires_confirmation: bool = False

    @abstractmethod
    def run(self, **params: Any) -> ToolResult:
        """Выполнить инструмент с заданными параметрами.

        Должен вернуть ToolResult(success=True/False, output=...).
        При исключении — оборачивает в ToolResult(success=False, error=...).
        """


class ToolConfirmationRequired(Exception):
    """Поднимается если требуется подтверждение, но пользователь отказал."""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"User declined confirmation for tool: {tool_name}")
