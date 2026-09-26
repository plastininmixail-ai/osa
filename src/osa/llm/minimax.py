"""Minimax клиент (MiniMax-M3).

OpenAI-совместимый endpoint + native tool calling + reasoning_content.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import httpx

from osa.config import LLMConfig
from osa.llm.base import (
    LLMMessage,
    LLMProvider,
    LLMResponse,
    ToolSpec,
    resolve_api_key,
)
from osa.llm.tool_calls import ToolCallRequest


DEFAULT_BASE_URL = "https://api.minimax.io/v1"
DEFAULT_MODEL = "MiniMax-M3"


def _message_to_dict(msg: LLMMessage) -> dict[str, Any]:
    """Сериализация LLMMessage в OpenAI-формат."""
    result: dict[str, Any] = {"role": msg.role}
    if msg.content:
        result["content"] = msg.content
    if msg.name:
        result["name"] = msg.name
    if msg.tool_call_id:
        result["tool_call_id"] = msg.tool_call_id
    if msg.tool_calls:
        result["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                },
            }
            for tc in msg.tool_calls
        ]
    return result


def _tool_spec_to_dict(spec: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        },
    }


def _parse_response(data: dict[str, Any]) -> LLMResponse:
    choice = data["choices"][0]
    message = choice["message"]
    usage = data.get("usage", {})

    # reasoning_content (thinking) если есть
    reasoning = message.get("reasoning_content") or message.get("reasoning")

    # tool_calls
    tool_calls: list[ToolCallRequest] | None = None
    if "tool_calls" in message and message["tool_calls"]:
        tool_calls = []
        for tc in message["tool_calls"]:
            func = tc.get("function", {})
            args_raw = func.get("arguments", "{}")
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = {"_raw": args_raw}
            tool_calls.append(
                ToolCallRequest(
                    id=tc.get("id", ""),
                    name=func.get("name", ""),
                    arguments=args,
                )
            )

    return LLMResponse(
        content=message.get("content", "") or "",
        tokens_used=usage.get("total_tokens", 0),
        model=data.get("model", "unknown"),
        reasoning=reasoning,
        tool_calls=tool_calls,
        finish_reason=choice.get("finish_reason", "stop"),
        raw=data,
    )


class MinimaxClient(LLMProvider):
    """Клиент для MiniMax API (MiniMax-M3 и других моделей)."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.api_key = resolve_api_key(config.api_key)
        if not self.api_key:
            raise ValueError(
                "Minimax API key not found. Set OSA_LLM__API_KEY env var."
            )

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list[ToolSpec] | None = None,
    ) -> LLMResponse:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
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

        # Retry с exponential backoff для transient ошибок (SSL handshake,
        # connection timeout, 5xx).
        import time

        last_error: Exception | None = None
        max_attempts = max(1, self.config.max_retries)

        for attempt in range(1, max_attempts + 1):
            try:
                with httpx.Client(timeout=self.config.timeout) as client:
                    response = client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                return _parse_response(data)
            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.RemoteProtocolError,
                httpx.NetworkError,
            ) as e:
                last_error = e
                if attempt < max_attempts:
                    # Exponential backoff: 1s, 2s, 4s
                    wait = 2 ** (attempt - 1)
                    time.sleep(wait)
                    continue
                raise
            except httpx.HTTPStatusError as e:
                # 5xx — retry, 4xx — fail immediately
                if 500 <= e.response.status_code < 600 and attempt < max_attempts:
                    last_error = e
                    wait = 2 ** (attempt - 1)
                    time.sleep(wait)
                    continue
                raise

        # Не должны сюда дойти, но на всякий случай:
        raise last_error if last_error else RuntimeError("MinimaxClient: unknown error")
