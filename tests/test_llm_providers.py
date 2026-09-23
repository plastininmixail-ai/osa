"""Тесты LLM провайдеров."""

from __future__ import annotations

import json

from osa.llm.base import LLMMessage, ToolSpec
from osa.llm.minimax import _message_to_dict, _parse_response, _tool_spec_to_dict


def test_message_to_dict_basic() -> None:
    msg = LLMMessage(role="user", content="hi")
    d = _message_to_dict(msg)
    assert d == {"role": "user", "content": "hi"}


def test_message_to_dict_tool_call() -> None:
    from osa.llm.tool_calls import ToolCallRequest

    msg = LLMMessage(
        role="assistant",
        content="",
        tool_calls=[ToolCallRequest(id="c1", name="file_read", arguments={"path": "x"})],
    )
    d = _message_to_dict(msg)
    assert d["role"] == "assistant"
    assert d["tool_calls"][0]["function"]["name"] == "file_read"
    args = json.loads(d["tool_calls"][0]["function"]["arguments"])
    assert args == {"path": "x"}


def test_message_to_dict_tool_result() -> None:
    msg = LLMMessage(role="tool", content="file content", tool_call_id="c1")
    d = _message_to_dict(msg)
    assert d == {"role": "tool", "content": "file content", "tool_call_id": "c1"}


def test_tool_spec_to_dict() -> None:
    spec = ToolSpec(
        name="file_read",
        description="read file",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
    )
    d = _tool_spec_to_dict(spec)
    assert d["type"] == "function"
    assert d["function"]["name"] == "file_read"


def test_parse_response_text_only() -> None:
    data = {
        "model": "m",
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "hello"}}],
        "usage": {"total_tokens": 5},
    }
    r = _parse_response(data)
    assert r.content == "hello"
    assert r.finish_reason == "stop"
    assert r.tool_calls is None
    assert r.tokens_used == 5


def test_parse_response_with_tool_calls() -> None:
    data = {
        "model": "m",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "file_read",
                                "arguments": '{"path": "x.txt"}',
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {"total_tokens": 10},
    }
    r = _parse_response(data)
    assert r.tool_calls is not None
    assert len(r.tool_calls) == 1
    assert r.tool_calls[0].name == "file_read"
    assert r.tool_calls[0].arguments == {"path": "x.txt"}


def test_parse_response_with_reasoning() -> None:
    data = {
        "model": "MiniMax-M3",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "Final answer",
                    "reasoning_content": "thinking process",
                },
            }
        ],
    }
    r = _parse_response(data)
    assert r.content == "Final answer"
    assert r.reasoning == "thinking process"


def test_stub_returns_scenario_in_order(tmp_osa_home) -> None:
    from osa.llm.stub import StubProvider, StubResponse
    from osa.llm.tool_calls import ToolCallRequest

    scenario = [
        StubResponse(content="first"),
        StubResponse(tool_calls=[ToolCallRequest("c1", "shell", {})]),
        StubResponse(content="third"),
    ]
    p = StubProvider(scenario=scenario)

    r1 = p.complete([LLMMessage("user", "a")])
    assert r1.content == "first"
    assert r1.tool_calls is None

    r2 = p.complete([LLMMessage("user", "b")])
    assert r2.tool_calls is not None
    assert r2.content == ""

    r3 = p.complete([LLMMessage("user", "c")])
    assert r3.content == "third"

    r4 = p.complete([LLMMessage("user", "d")])
    assert r4.content == "Привет от stub!"
