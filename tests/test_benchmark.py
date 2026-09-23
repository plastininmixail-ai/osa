"""Тесты runtime.benchmark."""

from __future__ import annotations

from osa.llm.stub import StubProvider, StubResponse
from osa.runtime.benchmark import (
    BENCHMARK_GOALS,
    BenchmarkGoal,
    BenchmarkReport,
    BenchmarkResult,
)


def test_benchmark_goals_count() -> None:
    """Есть 3 эталонные цели из PRD."""
    assert len(BENCHMARK_GOALS) == 3


def test_benchmark_goals_have_required_fields() -> None:
    for goal in BENCHMARK_GOALS:
        assert goal.id
        assert goal.description
        assert goal.success_criteria


def test_benchmark_goals_have_unique_ids() -> None:
    ids = [g.id for g in BENCHMARK_GOALS]
    assert len(ids) == len(set(ids))


def test_benchmark_goals_match_prd() -> None:
    """Цели соответствуют PRD §9."""
    ids = {g.id for g in BENCHMARK_GOALS}
    assert "create_pyproject" in ids
    assert "weather_api" in ids
    assert "find_todos" in ids


def test_benchmark_report_success_rate() -> None:
    """success_rate считается правильно."""
    goals = [BenchmarkGoal(id="x", description="y", success_criteria="z")]
    results = [
        BenchmarkResult("x", 1, "done", 1.0, 100, 2),
        BenchmarkResult("x", 2, "failed", 1.0, 100, 2, "err"),
        BenchmarkResult("x", 3, "done", 1.0, 100, 2),
    ]
    report = BenchmarkReport(
        results=results, goals=goals, provider="X", model="y", timestamp="t"
    )
    assert report.success_rate("x") == 2 / 3
    assert report.avg_tokens("x") == 100
    assert report.avg_time("x") == 1.0


def test_benchmark_report_format() -> None:
    goals = [BenchmarkGoal(id="test_goal", description="x", success_criteria="z")]
    results = [BenchmarkResult("test_goal", 1, "done", 5.0, 500, 3)]
    report = BenchmarkReport(
        results=results, goals=goals, provider="minimax", model="MiniMax-M3", timestamp="2026-09-23"
    )
    text = report.format_text()
    assert "OSA Benchmark Report" in text
    assert "test_goal" in text
    assert "100%" in text  # success rate
    assert "5.0s" in text
    assert "500" in text


def test_run_osagent_returns_metrics(tmp_osa_home, monkeypatch) -> None:
    """run_osagent возвращает status, elapsed, error."""
    from osa.runtime.benchmark import run_osagent

    monkeypatch.setenv("OSA_HOME", str(tmp_osa_home))
    monkeypatch.setenv("OSA_CONFIG_DIR", str(tmp_osa_home / "config"))
    monkeypatch.setenv("OSA_LOG_DIR", str(tmp_osa_home / "logs"))
    monkeypatch.setenv("OSA_LLM__PROVIDER", "stub")
    monkeypatch.setenv("OSA_LLM__API_KEY", "test")

    from importlib import reload
    from osa import paths as osa_paths, db as osa_db

    reload(osa_paths)
    reload(osa_db)
    osa_db.init_db()

    provider = StubProvider(scenario=[StubResponse(content='{"tasks": [{"description": "x"}]}'), StubResponse(content="done")])
    result = run_osagent(provider, "test goal")

    assert "status" in result
    assert "elapsed" in result
    assert result["status"] in ("done", "failed")


def test_run_baseline_one_shot() -> None:
    """run_baseline_one_shot возвращает (text, tokens) без tools."""
    from osa.runtime.benchmark import run_baseline_one_shot

    provider = StubProvider(
        scenario=[StubResponse(content="baseline answer", tokens=50)]
    )
    text, tokens = run_baseline_one_shot(provider, "test")
    assert text == "baseline answer"
    assert tokens == 50
