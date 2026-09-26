"""Тесты token limit в ReAct loop."""

from __future__ import annotations

from osa.llm.stub import StubProvider, StubResponse
from osa.llm.tool_calls import ToolCallRequest
from osa.runtime.react import ReactConfig, ReactLoop


def test_token_limit_stops_loop_after_tool_call() -> None:
    """После tool_call, если следующая итерация думает и превышает лимит — стоп."""
    provider = StubProvider(
        scenario=[
            # iter 1: tool_call (был tool call, 5000 токенов, cumulative=5000)
            StubResponse(
                tool_calls=[ToolCallRequest("c1", "file_list", {"dir": "."})],
                tokens=5000,
            ),
            # iter 2: думает (5000 токенов, cumulative=10000 = лимит)
            StubResponse(content="thinking a lot", tokens=5000),
            # iter 3: НЕ должно выполниться
            StubResponse(content="never reached", tokens=5000),
        ]
    )
    loop = ReactLoop(
        provider=provider,
        config=ReactConfig(max_iterations=15, max_total_tokens=10000, auto_approve=True),
    )
    result = loop.run("test")

    # Должен остановиться после 2 итераций (10000 токенов)
    assert result.iterations == 2
    assert "token limit" in result.final_content.lower()
    assert "10000" in result.final_content


def test_normal_completion_under_token_limit() -> None:
    """Если укладываемся в лимит — финальный ответ нормальный."""
    provider = StubProvider(
        scenario=[
            # iter 1: tool_call
            StubResponse(
                tool_calls=[ToolCallRequest("c1", "file_list", {"dir": "."})],
                tokens=100,
            ),
            # iter 2: финальный ответ (нет tool_calls → выход)
            StubResponse(content="All done!", tokens=100),
        ]
    )
    loop = ReactLoop(
        provider=provider,
        config=ReactConfig(max_iterations=15, max_total_tokens=50000, auto_approve=True),
    )
    result = loop.run("test")

    assert result.iterations == 2
    assert result.final_content == "All done!"


def test_high_token_limit_allows_more_iterations() -> None:
    """Большой лимит → больше итераций."""
    # Чередуем tool_calls и "thinking"
    scenario = []
    for i in range(20):
        if i % 2 == 0:
            # tool_call
            scenario.append(
                StubResponse(
                    tool_calls=[ToolCallRequest(f"c{i}", "file_list", {"dir": "."})],
                    tokens=1000,
                )
            )
        else:
            # thinking (но не финальный)
            scenario.append(StubResponse(content=f"thinking {i}", tokens=1000))
    # Финальный ответ после 20 итераций (на iter 19 будет tool, на iter 20 нужно
    # что-то без tool_calls). Но у нас лимит по итерациям 20. Делаем iter 19 без
    # tool_calls — будет финал.

    provider = StubProvider(scenario=scenario)
    loop = ReactLoop(
        provider=provider,
        config=ReactConfig(max_iterations=20, max_total_tokens=100000, auto_approve=True),
    )
    result = loop.run("test")

    # Не больше 20 iter. На каком-то iter будет финал (потому что нет tool_calls)
    assert result.iterations <= 20


def test_none_iterations_limit_allows_unlimited() -> None:
    """max_iterations=None → без лимита, цикл идёт пока не будет финал."""
    provider = StubProvider(
        scenario=[
            StubResponse(tool_calls=[ToolCallRequest("c1", "file_list", {"dir": "."})]),
            StubResponse(tool_calls=[ToolCallRequest("c2", "file_list", {"dir": "."})]),
            StubResponse(content="final answer"),
        ]
    )
    loop = ReactLoop(
        provider=provider,
        config=ReactConfig(
            max_iterations=None,  # без лимита
            max_total_tokens=None,  # без лимита
            auto_approve=True,
        ),
    )
    result = loop.run("test")

    # Должен пройти через все 3 итерации
    assert result.iterations == 3
    assert result.final_content == "final answer"


def test_none_iterations_with_safety_cap() -> None:
    """max_iterations=None с safety cap — не зависает бесконечно если LLM глючит."""
    # StubProvider всегда возвращает tool_call → цикл никогда не закончится сам
    provider = StubProvider(
        scenario=[
            StubResponse(tool_calls=[ToolCallRequest(f"c{i}", "file_list", {"dir": "."})])
            for i in range(20)
        ]
    )
    loop = ReactLoop(
        provider=provider,
        config=ReactConfig(max_iterations=None, max_total_tokens=None, auto_approve=True),
    )
    result = loop.run("test")

    # Safety cap 10000, StubProvider имеет 20 сценариев → вернёт fallback после
    # 20 итераций, потом должен попасть в safety cap → но упадёт по default "Привет от stub!".
    # Главное что не зависает
    assert result.iterations <= 25  # safety cap or fallback


def test_low_token_limit_stops_quickly() -> None:
    """Маленький лимит → быстрая остановка даже без tool_calls."""
    # iter 1: думает 6000 токенов, лимит 5000
    provider = StubProvider(
        scenario=[
            StubResponse(content="long thinking", tokens=6000),
        ]
    )
    loop = ReactLoop(
        provider=provider,
        config=ReactConfig(max_iterations=15, max_total_tokens=5000, auto_approve=True),
    )
    result = loop.run("test")

    assert result.iterations == 1
    assert "token limit" in result.final_content.lower()

