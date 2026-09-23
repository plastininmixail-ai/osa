"""LLM-провайдеры O.S.A.

Заглушки для CLI-скелета. Реальные реализации — в M0.5.
"""

from osa.llm.base import LLMMessage, LLMProvider, LLMResponse, resolve_api_key

__all__ = [
    "LLMMessage",
    "LLMProvider",
    "LLMResponse",
    "resolve_api_key",
]
