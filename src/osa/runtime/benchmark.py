"""Benchmark runner для эталонных целей.

Запускает OSA на наборе фиксированных целей, измеряет:
- success rate (% успешно выполненных)
- среднее время выполнения
- среднее количество токенов
- среднее количество итераций ReAct

Также сравнивает с baseline "голая модель" (один запрос без tools/agents).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from osa.llm.base import LLMMessage, LLMProvider
from osa.logging_setup import get_logger
from osa.runtime.engine import GoalEngine


LOGGER = get_logger("osa.benchmark")


@dataclass
class BenchmarkGoal:
    """Эталонная цель для бенчмарка."""

    id: str  # короткий id: "create_pyproject"
    description: str  # полный текст цели
    success_criteria: str  # как понять что успех (для человека)
    expected_files: list[str] = field(default_factory=list)  # какие файлы должны появиться


@dataclass
class BenchmarkResult:
    """Результат одной попытки выполнения цели."""

    goal_id: str
    run_id: int  # номер попытки (1, 2, 3, ...)
    status: str  # "done" | "failed"
    elapsed_seconds: float
    tokens_used: int
    iterations: int
    error: str | None = None


@dataclass
class BenchmarkReport:
    """Сводный отчёт по benchmark'у."""

    results: list[BenchmarkResult]
    goals: list[BenchmarkGoal]
    provider: str
    model: str
    timestamp: str

    def success_rate(self, goal_id: str) -> float:
        """Доля успешных попыток для конкретной цели."""
        attempts = [r for r in self.results if r.goal_id == goal_id]
        if not attempts:
            return 0.0
        return sum(1 for r in attempts if r.status == "done") / len(attempts)

    def avg_tokens(self, goal_id: str) -> float:
        attempts = [r for r in self.results if r.goal_id == goal_id]
        if not attempts:
            return 0.0
        return sum(r.tokens_used for r in attempts) / len(attempts)

    def avg_time(self, goal_id: str) -> float:
        attempts = [r for r in self.results if r.goal_id == goal_id]
        if not attempts:
            return 0.0
        return sum(r.elapsed_seconds for r in attempts) / len(attempts)

    def format_text(self) -> str:
        lines = [
            f"# OSA Benchmark Report",
            f"Provider: {self.provider}, Model: {self.model}",
            f"Time: {self.timestamp}",
            "",
            f"{'Goal':<25} {'Success':<10} {'AvgTime':<10} {'AvgTokens':<12}",
            "-" * 60,
        ]
        for goal in self.goals:
            sr = self.success_rate(goal.id)
            atime = self.avg_time(goal.id)
            atokens = self.avg_tokens(goal.id)
            attempts = sum(1 for r in self.results if r.goal_id == goal.id)
            lines.append(
                f"{goal.id:<25} {sr*100:>5.0f}% ({attempts}){'':<2} "
                f"{atime:>6.1f}s   {atokens:>8.0f}"
            )

        total = len(self.results)
        done = sum(1 for r in self.results if r.status == "done")
        lines.extend([
            "",
            f"Total: {done}/{total} goals done ({done/total*100:.0f}%)" if total else "Total: 0/0",
        ])
        return "\n".join(lines)


# === Эталонные цели из PRD §9 ===

BENCHMARK_GOALS: list[BenchmarkGoal] = [
    BenchmarkGoal(
        id="create_pyproject",
        description=(
            "Создай в sandbox/ Python-проект hello-world: pyproject.toml с name='hello-world', "
            "main.py с функцией main(), README.md с описанием, запусти тесты через pytest."
        ),
        success_criteria="pyproject.toml, main.py, README.md существуют в sandbox/",
        expected_files=["pyproject.toml", "main.py", "README.md"],
    ),
    BenchmarkGoal(
        id="weather_api",
        description=(
            "Найди в интернете 5 публичных API погоды, выбери самый простой без ключа, "
            "напиши в sandbox/ скрипт weather.py который показывает погоду в Москве."
        ),
        success_criteria="sandbox/weather.py существует и содержит http запрос к API",
        expected_files=["weather.py"],
    ),
    BenchmarkGoal(
        id="find_todos",
        description=(
            "Прочитай README.md из sandbox/, найди в нём все TODO/FIXME, "
            "составь таблицу в sandbox/todos.md с колонками: строка, тип, описание."
        ),
        success_criteria="sandbox/todos.md существует с таблицей",
        expected_files=["todos.md"],
    ),
]


def run_baseline_one_shot(
    provider: LLMProvider,
    goal_text: str,
) -> tuple[str, int]:
    """Baseline: один запрос к голой модели без инструментов и планирования.

    Используется для сравнения с OSA — доказательство что scaffolding помогает.
    """
    messages = [
        LLMMessage(
            role="system",
            content="Ты — ассистент. Реши задачу пользователя. Если нужны инструменты — опиши что бы ты сделал, но не выполняй.",
        ),
        LLMMessage(role="user", content=goal_text),
    ]
    response = provider.complete(messages)
    return response.content, response.tokens_used


def run_osagent(
    provider: LLMProvider,
    goal_text: str,
    max_iterations: int = 10,
) -> dict[str, Any]:
    """Запустить OSA на цели, вернуть метрики."""
    from osa.runtime.react import ReactConfig

    engine = GoalEngine(provider, ReactConfig(auto_approve=True, max_iterations=max_iterations))
    start = time.time()
    try:
        result = engine.run(goal_text)
        elapsed = time.time() - start
        return {
            "status": result.status,
            "elapsed": elapsed,
            "iterations": sum(
                step.iteration for step in []  # не хранится, нужно пересчитать
            ) if False else 1,  # пока упрощенно
            "tokens": 0,  # пока не считаем
            "error": None,
        }
    except Exception as e:
        return {
            "status": "failed",
            "elapsed": time.time() - start,
            "iterations": 0,
            "tokens": 0,
            "error": str(e),
        }


def run_benchmark(
    goals: list[BenchmarkGoal],
    provider: LLMProvider,
    attempts_per_goal: int = 3,
) -> BenchmarkReport:
    """Запустить все цели attempts_per_goal раз, собрать метрики.

    На M1d attempts_per_goal=1 для скорости. Увеличить для статистики.
    """
    from datetime import datetime

    results: list[BenchmarkResult] = []
    for goal in goals:
        LOGGER.info("benchmark_goal_start", extra={"goal_id": goal.id})
        for attempt in range(1, attempts_per_goal + 1):
            start = time.time()
            try:
                engine = GoalEngine(provider)
                result = engine.run(goal.description)
                elapsed = time.time() - start

                # Считаем iterations и tokens из эпизодов
                from osa.db import connect

                conn = connect()
                ep_count = conn.execute(
                    "SELECT COUNT(*) FROM episodes WHERE goal_id = ?",
                    (result.goal_id,),
                ).fetchone()[0]
                tokens = conn.execute(
                    "SELECT COALESCE(SUM(tokens_used), 0) FROM episodes WHERE goal_id = ?",
                    (result.goal_id,),
                ).fetchone()[0]
                conn.close()

                br = BenchmarkResult(
                    goal_id=goal.id,
                    run_id=attempt,
                    status=result.status,
                    elapsed_seconds=elapsed,
                    tokens_used=tokens,
                    iterations=ep_count,
                    error=result.failure_reason if result.failed_task else None,
                )
                results.append(br)
                LOGGER.info(
                    "benchmark_attempt_done",
                    extra={
                        "goal_id": goal.id,
                        "run_id": attempt,
                        "status": br.status,
                        "elapsed": br.elapsed_seconds,
                    },
                )
            except Exception as e:
                elapsed = time.time() - start
                br = BenchmarkResult(
                    goal_id=goal.id,
                    run_id=attempt,
                    status="failed",
                    elapsed_seconds=elapsed,
                    tokens_used=0,
                    iterations=0,
                    error=str(e),
                )
                results.append(br)
                LOGGER.error(
                    "benchmark_attempt_failed",
                    extra={"goal_id": goal.id, "run_id": attempt, "error": str(e)},
                )

    # Получаем provider/model name
    provider_name = type(provider).__name__
    model_name = "unknown"

    return BenchmarkReport(
        results=results,
        goals=goals,
        provider=provider_name,
        model=model_name,
        timestamp=datetime.now().isoformat(),
    )
