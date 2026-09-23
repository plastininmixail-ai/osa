"""OpenAI-совместимый клиент (OpenRouter, Ollama, llama.cpp, ...)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import httpx

from osa.config import LLMConfig
from osa.llm.base import LLMMessage, LLMProvider, LLMResponse, ToolSpec, resolve_api_key
from osa.llm.minimax import _message_to_dict, _parse_response, _tool_spec_to_dict


class OpenAICompatClient(LLMProvider):
    """Универсальный клиент для OpenAI-совместимых API с tool calling."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.api_key = resolve_api_key(config.api_key)

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list[ToolSpec] | None = None,
    ) -> LLMResponse:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [_message_to_dict(m) for m in messages],
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if tools:
            payload["tools"] = [_tool_spec_to_dict(t) for t in tools]
            payload["tool_choice"] = "auto"

        with httpx.Client(timeout=self.config.timeout) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        return _parse_response(data)
