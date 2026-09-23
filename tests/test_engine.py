"""Тесты runtime.engine — GoalEngine и TaskStore."""

from __future__ import annotations

from osa.llm.stub import StubProvider, StubResponse
from osa.runtime.engine import GoalEngine
from osa.runtime.react import ReactConfig


def test_engine_creates_goal_in_db(tmp_osa_home, initialized_db) -> None:
    """Goal записывается в БД при старте."""
    from osa.db import connect

    provider = StubProvider(scenario=[StubResponse(content="Final answer")])
    engine = GoalEngine(provider, ReactConfig(auto_approve=True))
    result = engine.run("test goal")

    assert result.goal_id > 0
    conn = connect()
    row = conn.execute("SELECT * FROM goals WHERE id=?", (result.goal_id,)).fetchone()
    conn.close()
    assert row is not None
    assert row["description"] == "test goal"


def test_engine_creates_tasks_in_db(tmp_osa_home, initialized_db) -> None:
    """Planner → tasks записаны в БД."""
    from osa.db import connect

    provider = StubProvider(
        scenario=[
            StubResponse(content='{"tasks": [{"description": "task 1"}, {"description": "task 2"}]}'),
            StubResponse(content="task 1 done"),
            StubResponse(content="task 2 done"),
        ]
    )
    engine = GoalEngine(provider, ReactConfig(auto_approve=True))
    result = engine.run("test goal")

    conn = connect()
    tasks = conn.execute(
        "SELECT * FROM tasks WHERE goal_id=? ORDER BY id", (result.goal_id,)
    ).fetchall()
    conn.close()

    assert len(tasks) == 2
    assert tasks[0]["description"] == "task 1"
    assert tasks[1]["description"] == "task 2"


def test_engine_simple_single_task_goal(tmp_osa_home, initialized_db) -> None:
    """Простая цель (1 задача) выполняется."""
    provider = StubProvider(
        scenario=[
            StubResponse(content='{"tasks": [{"description": "do x"}]}'),
            StubResponse(content="x is done"),
        ]
    )
    engine = GoalEngine(provider, ReactConfig(auto_approve=True))
    result = engine.run("do x")

    assert result.status == "done"
    assert result.failed_task is None
    assert len(result.plan.tasks) == 1


def test_engine_status_done_for_successful_goal(tmp_osa_home, initialized_db) -> None:
    """Все задачи done → goal status=done в БД."""
    from osa.db import connect

    provider = StubProvider(
        scenario=[
            StubResponse(content='{"tasks": [{"description": "a"}, {"description": "b"}]}'),
            StubResponse(content="a done"),
            StubResponse(content="b done"),
        ]
    )
    engine = GoalEngine(provider, ReactConfig(auto_approve=True))
    result = engine.run("multi-step goal")

    assert result.status == "done"

    conn = connect()
    row = conn.execute("SELECT status FROM goals WHERE id=?", (result.goal_id,)).fetchone()
    conn.close()
    assert row["status"] == "done"


def test_engine_handles_failed_task(tmp_osa_home, initialized_db) -> None:
    """Если задача провалилась (max iterations), goal = failed."""
    from osa.db import connect
    from osa.llm.tool_calls import ToolCallRequest

    # Planner возвращает 1 задачу, потом stub бесконечно вызывает tool.
    # Каждый вызов complete() возвращает tool_call, потом fallback.
    # ReactLoop с max_iterations=2 быстро упирается в лимит.
    provider = StubProvider(
        scenario=[
            StubResponse(content='{"tasks": [{"description": "hard task"}]}'),
        ]
        + [
            StubResponse(
                tool_calls=[ToolCallRequest("c1", "file_list", {"dir": "."})]
            )
            for _ in range(5)
        ]
        + [StubResponse(content="final")]  # fallback
    )
    engine = GoalEngine(
        provider, ReactConfig(auto_approve=True, max_iterations=2)
    )
    result = engine.run("hard goal")

    assert result.status == "failed", f"Expected failed, got {result.status}"
    assert result.failed_task is not None

    conn = connect()
    row = conn.execute("SELECT status FROM goals WHERE id=?", (result.goal_id,)).fetchone()
    conn.close()
    assert row["status"] == "failed"


def test_engine_plan_text_summary(tmp_osa_home, initialized_db) -> None:
    """plan_text_summary возвращает понятный отчёт."""
    provider = StubProvider(
        scenario=[
            StubResponse(content='{"tasks": [{"description": "first"}, {"description": "second"}]}'),
            StubResponse(content="done 1"),
            StubResponse(content="done 2"),
        ]
    )
    engine = GoalEngine(provider, ReactConfig(auto_approve=True))
    result = engine.run("multi")
    summary = result.plan_text_summary()

    assert "Цель: multi" in summary
    assert "1. first" in summary
    assert "2. second" in summary
    assert "✓" in summary  # done markers


def test_engine_resume_finds_unfinished_goals(tmp_osa_home, initialized_db) -> None:
    """find_resumable_goals возвращает goals со статусом running/paused."""
    from osa.db import connect

    conn = connect()
    conn.execute(
        "INSERT INTO goals (description, status) VALUES ('paused goal', 'paused')"
    )
    conn.execute(
        "INSERT INTO goals (description, status) VALUES ('done goal', 'done')"
    )
    conn.commit()
    conn.close()

    provider = StubProvider(scenario=[])
    engine = GoalEngine(provider)
    resumable = engine.find_resumable_goals()

    assert len(resumable) == 1


def test_engine_logs_iterations_in_db(tmp_osa_home, initialized_db) -> None:
    """При успешном выполнении tasks записывают iterations."""
    from osa.db import connect

    provider = StubProvider(
        scenario=[
            StubResponse(content='{"tasks": [{"description": "x"}]}'),
            StubResponse(content="done"),
        ]
    )
    engine = GoalEngine(provider, ReactConfig(auto_approve=True))
    engine.run("test")

    conn = connect()
    tasks = conn.execute(
        "SELECT * FROM tasks WHERE attempts > 0"
    ).fetchall()
    conn.close()

    assert len(tasks) >= 1
    assert all(t["attempts"] >= 1 for t in tasks)
