"""Тесты runtime.planner."""

from __future__ import annotations

from osa.llm.stub import StubProvider, StubResponse
from osa.runtime.planner import Planner


def test_planner_parses_direct_json() -> None:
    """Planner парсит прямой JSON."""
    p = Planner(
        StubProvider(
            scenario=[
                StubResponse(
                    content='{"tasks": [{"description": "a", "rationale": "x"}, {"description": "b"}]}'
                )
            ]
        )
    )
    plan = p.plan("test goal")

    assert len(plan.tasks) == 2
    assert plan.tasks[0].description == "a"
    assert plan.tasks[0].rationale == "x"
    assert plan.tasks[1].description == "b"


def test_planner_parses_markdown_wrapped_json() -> None:
    """Planner парсит JSON внутри ```json ... ```."""
    p = Planner(
        StubProvider(
            scenario=[
                StubResponse(
                    content='Вот план:\n```json\n{"tasks": [{"description": "a"}]}\n```\nУдачи!'
                )
            ]
        )
    )
    plan = p.plan("test goal")
    assert len(plan.tasks) == 1
    assert plan.tasks[0].description == "a"


def test_planner_fallback_on_invalid_json() -> None:
    """Planner делает fallback на single-task plan при мусоре."""
    p = Planner(StubProvider(scenario=[StubResponse(content="не JSON вообще")]))
    plan = p.plan("сделать что-то")

    assert len(plan.tasks) == 1
    assert plan.tasks[0].description == "сделать что-то"
    assert "fallback" in plan.tasks[0].rationale


def test_planner_fallback_on_empty_tasks() -> None:
    """Planner делает fallback на single-task plan при пустом tasks."""
    p = Planner(
        StubProvider(scenario=[StubResponse(content='{"tasks": []}')])
    )
    plan = p.plan("test")
    assert len(plan.tasks) == 1


def test_planner_skips_invalid_entries() -> None:
    """Planner пропускает entries без description."""
    p = Planner(
        StubProvider(
            scenario=[
                StubResponse(
                    content='{"tasks": [{"description": "good"}, {"rationale": "no desc"}, {"description": ""}, "not a dict"]}'
                )
            ]
        )
    )
    plan = p.plan("test")
    assert len(plan.tasks) == 1
    assert plan.tasks[0].description == "good"


def test_planner_extract_json_direct() -> None:
    """_extract_json возвращает строку если она начинается с {."""
    from osa.runtime.planner import Planner

    assert Planner._extract_json('{"a": 1}') == '{"a": 1}'


def test_planner_extract_json_markdown() -> None:
    from osa.runtime.planner import Planner

    assert Planner._extract_json("```json\n{\"a\": 1}\n```") == '{"a": 1}'


def test_planner_extract_json_in_text() -> None:
    from osa.runtime.planner import Planner

    text = 'Сначала текст {"a": 1, "b": 2} и потом ещё'
    assert Planner._extract_json(text) == '{"a": 1, "b": 2}'


def test_planner_extract_json_returns_none() -> None:
    from osa.runtime.planner import Planner

    assert Planner._extract_json("нет json") is None
    assert Planner._extract_json("") is None
