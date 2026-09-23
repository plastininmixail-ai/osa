"""Абстракция LLM-провайдера.

Заглушка для CLI-скелета. Полная реализация — в M0.5.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str
    name: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    content: str
    tokens_used: int
    model: str
    reasoning: str | None = None
    raw: dict | None = None


class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Сделать один вызов LLM."""


def resolve_api_key(config_value: str | None) -> str:
    """Получить API-ключ из конфига или env."""
    return (
        config_value
        or os.environ.get("OSA_LLM__API_KEY")
        or os.environ.get("OSA_LLM_API_KEY")
        or ""
    )
