"""Тесты fast path в GoalEngine."""

from __future__ import annotations

from osa.llm.stub import StubProvider, StubResponse


def test_is_informational_returns_true_for_questions() -> None:
    """Вопросительные фразы → True."""
    from osa.runtime.engine import GoalEngine

    assert GoalEngine._is_informational("Как устроена твоя память?") is True
    assert GoalEngine._is_informational("Что такое Goal Engine?") is True
    assert GoalEngine._is_informational("Расскажи про себя") is True
    assert GoalEngine._is_informational("Почему небо голубое?") is True


def test_is_informational_returns_false_for_actions() -> None:
    """Action-глаголы → False (полный путь через planner)."""
    from osa.runtime.engine import GoalEngine

    assert GoalEngine._is_informational("Создай файл hello.txt") is False
    assert GoalEngine._is_informational("Прочитай note.txt") is False
    assert GoalEngine._is_informational("Найди папки на рабочем столе") is False
    assert GoalEngine._is_informational("Установи pytest и запусти тесты") is False
    assert GoalEngine._is_informational("Напиши скрипт weather.py") is False
    assert GoalEngine._is_informational("Покажи какие файлы в sandbox") is False


def test_is_informational_question_mark_only() -> None:
    """Только знак вопроса → True."""
    from osa.runtime.engine import GoalEngine

    assert GoalEngine._is_informational("Python?") is True


def test_fast_path_uses_one_llm_call(tmp_osa_home, monkeypatch) -> None:
    """Fast path делает один запрос к LLM без планировщика."""
    monkeypatch.setenv("OSA_HOME", str(tmp_osa_home))
    monkeypatch.setenv("OSA_CONFIG_DIR", str(tmp_osa_home / "config"))
    monkeypatch.setenv("OSA_LOG_DIR", str(tmp_osa_home / "logs"))
    monkeypatch.setenv("OSA_LLM__PROVIDER", "stub")

    from importlib import reload
    from osa import paths as osa_paths, db as osa_db
    reload(osa_paths)
    reload(osa_db)
    osa_db.init_db()

    from osa.runtime.engine import GoalEngine

    provider = StubProvider(
        scenario=[StubResponse(content="Краткий ответ", tokens=42)]
    )
    engine = GoalEngine(provider)
    result = engine.run("Как устроена твоя память?")

    assert result.status == "done"
    assert provider.call_count == 1  # один вызов, не три
    # В плане одна задача (информационный вопрос)
    assert len(result.plan.tasks) == 1
    assert result.plan.tasks[0].status == "done"
    assert result.plan.tasks[0].result == "Краткий ответ"


def test_full_path_uses_planner_for_actions(tmp_osa_home, monkeypatch) -> None:
    """Action-запросы идут через planner (полный путь)."""
    monkeypatch.setenv("OSA_HOME", str(tmp_osa_home))
    monkeypatch.setenv("OSA_CONFIG_DIR", str(tmp_osa_home / "config"))
    monkeypatch.setenv("OSA_LOG_DIR", str(tmp_osa_home / "logs"))
    monkeypatch.setenv("OSA_LLM__PROVIDER", "stub")

    from importlib import reload
    from osa import paths as osa_paths, db as osa_db
    reload(osa_paths)
    reload(osa_db)
    osa_db.init_db()

    from osa.runtime.engine import GoalEngine

    # Stub: 1) planner возвращает задачу, 2) executor выполняет
    provider = StubProvider(
        scenario=[
            StubResponse(content='{"tasks": [{"description": "test"}]}'),
            StubResponse(content="task done"),
        ]
    )
    engine = GoalEngine(provider)
    result = engine.run("Создай файл test.txt")

    assert result.status == "done"
    # planner (1 вызов) + executor (1 вызов) = 2
    assert provider.call_count >= 2
