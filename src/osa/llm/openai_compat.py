"""OpenAI-совместимый клиент.

Используется для:
- OpenRouter (https://openrouter.ai/api/v1)
- Ollama (http://localhost:11434/v1)
- llama.cpp server (http://localhost:8080/v1)
- любой другой OpenAI-style endpoint (включая Minimax в Anthropic-mode)

Минимальная зависимость: только httpx. Без openai/anthropic SDK.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import httpx

from osa.config import LLMConfig
from osa.llm.base import LLMMessage, LLMProvider, LLMResponse, resolve_api_key


class OpenAICompatClient(LLMProvider):
    """Универсальный клиент для OpenAI-совместимых API."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.api_key = resolve_api_key(config.api_key)

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [asdict(m) for m in messages],
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature

        with httpx.Client(timeout=self.config.timeout) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        message = choice["message"]
        usage = data.get("usage", {})

        return LLMResponse(
            content=message.get("content", "") or "",
            tokens_used=usage.get("total_tokens", 0),
            model=data.get("model", self.config.model),
            raw=data,
        )
