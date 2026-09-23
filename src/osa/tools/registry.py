"""Tool registry.

Реестр инструментов. На старте — singleton со встроенными инструментами.
"""

from __future__ import annotations

from osa.tools.base import Tool

_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    """Зарегистрировать инструмент. Бросает если имя уже занято."""
    if tool.name in _REGISTRY:
        raise ValueError(f"Tool {tool.name!r} already registered")
    _REGISTRY[tool.name] = tool


def get(name: str) -> Tool:
    """Получить инструмент по имени. Бросает если не найден."""
    if name not in _REGISTRY:
        raise KeyError(f"Tool {name!r} not found. Available: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def all_tools() -> list[Tool]:
    """Вернуть список всех зарегистрированных инструментов."""
    return list(_REGISTRY.values())


def reset() -> None:
    """Очистить реестр (для тестов)."""
    _REGISTRY.clear()
