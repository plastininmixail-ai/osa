"""Minimax клиент (MiniMax-M3).

Использует OpenAI-совместимый endpoint https://api.minimax.io/v1.
Поддерживает thinking-параметр: модель возвращает reasoning_content
в отдельном поле message.

На M0 thinking выключен по умолчанию (hello-world без него быстрее).
Управление через LLMConfig появится в M1a.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import httpx

from osa.config import LLMConfig
from osa.llm.base import LLMMessage, LLMProvider, LLMResponse, resolve_api_key


DEFAULT_BASE_URL = "https://api.minimax.io/v1"
DEFAULT_MODEL = "MiniMax-M3"


class MinimaxClient(LLMProvider):
    """Клиент для MiniMax API.

    OpenAI-совместимый формат + специфика M3 (reasoning_content).
    """

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.api_key = resolve_api_key(config.api_key)
        if not self.api_key:
            raise ValueError(
                "Minimax API key not found. Set OSA_LLM__API_KEY env var "
                "or llm.api_key in config.toml."
            )

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [asdict(m) for m in messages],
            "max_tokens": max_tokens,
            # thinking выключен на M0, чтобы hello-world был быстрым.
            # "thinking": {"type": "enabled"},
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

        # M3 возвращает reasoning_content если thinking включён.
        # Сохраняем в LLMResponse.reasoning для последующего использования в M1a.
        reasoning = message.get("reasoning_content") or message.get("reasoning")

        return LLMResponse(
            content=message.get("content", "") or "",
            tokens_used=usage.get("total_tokens", 0),
            model=data.get("model", self.config.model),
            reasoning=reasoning,
            raw=data,
        )
