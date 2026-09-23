"""Тесты ReAct loop."""

from __future__ import annotations

from osa.llm.base import LLMMessage
from osa.llm.stub import StubProvider, StubResponse
from osa.llm.tool_calls import ToolCallRequest
from osa.runtime.react import ReactConfig, ReactLoop
from osa.tools import builtin, registry
from osa.tools.builtin import FileReadTool, FileWriteTool


def test_react_executes_tool_call_and_returns_final(tmp_osa_home) -> None:
    """Stub вызывает file_read → читает файл → отвечает финально."""
    registry.reset()
    builtin.register_all()

    # Создаём файл для чтения
    FileWriteTool().run(path="data.txt", content="42 is the answer")

    provider = StubProvider(
        scenario=[
            StubResponse(
                tool_calls=[
                    ToolCallRequest(
                        id="c1",
                        name="file_read",
                        arguments={"path": "data.txt"},
                    ),
                ],
            ),
            StubResponse(content="Файл говорит: 42 is the answer"),
        ],
    )
    loop = ReactLoop(provider=provider, config=ReactConfig(auto_approve=True))

    result = loop.run("прочитай data.txt")

    assert "42 is the answer" in result.final_content
    assert result.iterations == 2
    assert len(result.steps) == 2
    assert result.steps[0].tool_calls[0].name == "file_read"
    assert "42 is the answer" in result.steps[0].tool_results[0].content


def test_react_handles_unknown_tool(tmp_osa_home) -> None:
    """LLM вызывает несуществующий инструмент — ошибка в результате."""
    registry.reset()
    builtin.register_all()

    provider = StubProvider(
        scenario=[
            StubResponse(
                tool_calls=[
                    ToolCallRequest(
                        id="c1",
                        name="non_existent_tool",
                        arguments={},
                    ),
                ],
            ),
            StubResponse(content="Инструмент не найден"),
        ],
    )
    loop = ReactLoop(provider=provider, config=ReactConfig(auto_approve=True))

    result = loop.run("test")
    assert result.iterations == 2


def test_react_returns_direct_answer_without_tools(tmp_osa_home) -> None:
    """LLM сразу отвечает content — без tool_calls."""
    registry.reset()
    builtin.register_all()

    provider = StubProvider(
        scenario=[StubResponse(content="Привет, чем могу помочь?")],
    )
    loop = ReactLoop(provider=provider, config=ReactConfig(auto_approve=True))

    result = loop.run("привет")
    assert result.final_content == "Привет, чем могу помочь?"
    assert result.iterations == 1


def test_react_max_iterations(tmp_osa_home) -> None:
    """LLM бесконечно вызывает tool → loop прерывается по max_iterations."""
    registry.reset()
    builtin.register_all()

    # 5 tool calls подряд, потом fallback ответ
    scenario = [
        StubResponse(
            tool_calls=[
                ToolCallRequest(
                    id=f"c{i}",
                    name="file_list",
                    arguments={"dir": "."},
                ),
            ],
        )
        for i in range(10)
    ]
    provider = StubProvider(scenario=scenario)
    loop = ReactLoop(
        provider=provider, config=ReactConfig(max_iterations=3, auto_approve=True)
    )

    result = loop.run("перечисляй файлы вечно")
    assert result.iterations == 3
    assert "max iterations" in result.final_content.lower()


def test_react_system_prompt_sent(tmp_osa_home) -> None:
    """Первое сообщение — system prompt."""
    registry.reset()
    builtin.register_all()

    provider = StubProvider(scenario=[StubResponse(content="ok")])
    loop = ReactLoop(provider=provider, config=ReactConfig(auto_approve=True))
    loop.run("test goal")

    assert provider.call_count == 1
    assert provider.last_messages[0].role == "system"
    assert provider.last_messages[1].role == "user"
    assert provider.last_messages[1].content == "test goal"


def test_react_tool_specs_in_provider(tmp_osa_home) -> None:
    """Tools передаются в LLM через stub (косвенно — через ToolSpec)."""
    registry.reset()
    builtin.register_all()

    provider = StubProvider(scenario=[StubResponse(content="ok")])
    loop = ReactLoop(provider=provider, config=ReactConfig(auto_approve=True))
    loop.run("test")

    # StubProvider не использует tools, но проверяем что loop вызвался без ошибок
    assert provider.call_count == 1
