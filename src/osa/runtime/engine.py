"""GoalEngine — orchestrator для goal-driven агента.

Связывает Planner (декомпозиция), TaskStore (БД), TaskExecutor (выполнение).

Цикл:
1. Принять цель → создать goal в БД (status=running)
2. Planner → список задач → записать в БД
3. Для каждой задачи:
   a. Записать task в БД (status=running)
   b. Executor → ReactLoop → результат
   c. Обновить task в БД (status=done/failed, result=...)
   d. Если failed и attempts < MAX → retry с тем же task
   e. Если failed и attempts >= MAX → остановить goal как failed
4. Если все задачи done → goal status=done
"""

from __future__ import annotations

from dataclasses import dataclass

from osa.config import load_config
from osa.db import connect
from osa.db import get_provider_for_goal
from osa.llm.base import LLMProvider
from osa.logging_setup import configure_logging, get_logger
from osa.runtime.planner import MAX_TASK_ATTEMPTS, Plan, Planner, Task, TaskExecutor, TaskStore
from osa.runtime.react import ReactConfig


@dataclass
class GoalResult:
    """Результат выполнения цели."""

    goal_id: int
    status: str  # "done" | "failed"
    plan: Plan
    failed_task: Task | None = None
    failure_reason: str | None = None

    def plan_text_summary(self) -> str:
        """Краткий текстовый отчёт о выполнении."""
        lines = [f"Цель: {self.plan.goal_text}", ""]
        lines.append("План:")
        for i, task in enumerate(self.plan.tasks, 1):
            status_marker = "✓" if task.status == "done" else "✗" if task.status == "failed" else "·"
            lines.append(f"  {status_marker} {i}. {task.description}")
        return "\n".join(lines)


class GoalEngine:
    """Оркестратор: цель → план → выполнение задач → результат."""

    def __init__(
        self,
        provider: LLMProvider,
        react_config: ReactConfig | None = None,
    ) -> None:
        self.provider = provider
        self.react_config = react_config or ReactConfig()
        self.planner = Planner(provider)
        self.executor = TaskExecutor(provider, react_config)
        self.log = get_logger("osa.engine")

    def run(self, goal_text: str, goal_id: int | None = None) -> GoalResult:
        """Выполнить цель: plan → execute tasks.

        Args:
            goal_text: текст цели
            goal_id: если задан, использовать существующую запись goal в БД
                     (для возобновления). Если None — создать новую.
        """
        # 1. Goal в БД
        if goal_id is None:
            goal_id = self._create_goal(goal_text)
        else:
            self._update_goal_status(goal_id, "running")

        # 2. Planner
        plan = self.planner.plan(goal_text)

        # 3. Сохранить задачи в БД (если ещё не сохранены)
        existing_tasks = TaskStore.list_pending_for_goal(goal_id)
        if not existing_tasks:
            for task in plan.tasks:
                TaskStore.create(goal_id, task)

        # 4. Выполнение
        return self._execute_plan(goal_id, plan)

    def resume(self, goal_id: int) -> GoalResult | None:
        """Возобновить незавершённую цель.

        Returns:
            GoalResult если была незавершённая цель, None если нечего возобновлять.
        """
        conn = connect()
        row = conn.execute(
            "SELECT id, description, status FROM goals WHERE id=? AND status IN ('running', 'paused')",
            (goal_id,),
        ).fetchone()
        conn.close()

        if not row:
            return None

        # Перепланировать (если нужно) и продолжить
        plan = self.planner.plan(row["description"])
        return self._execute_plan(goal_id, plan)

    def find_resumable_goals(self) -> list[int]:
        """Найти ID незавершённых целей для возобновления после рестарта."""
        conn = connect()
        rows = conn.execute(
            "SELECT id FROM goals WHERE status IN ('running', 'paused') ORDER BY id ASC"
        ).fetchall()
        conn.close()
        return [r["id"] for r in rows]

    def _execute_plan(self, goal_id: int, plan: Plan) -> GoalResult:
        """Выполнить план."""
        tasks = TaskStore.list_pending_for_goal(goal_id)
        # Индексируем plan.tasks по description для синхронизации статусов
        plan_by_desc = {t.description: t for t in plan.tasks}

        for task in tasks:
            self.log.info(
                "engine_task_start",
                extra={"goal_id": goal_id, "task_id": task.id},
            )

            failed = False
            failure_reason = None

            for attempt in range(MAX_TASK_ATTEMPTS):
                TaskStore.update_status(task.id, "running")

                try:
                    result = self.executor.execute(task)
                except Exception as e:
                    failed = True
                    failure_reason = f"Executor exception: {e}"
                    TaskStore.update_status(
                        task.id, "failed", failure_reason, increment_attempts=True
                    )
                    self.log.warning(
                        "task_attempt_failed",
                        extra={"task_id": task.id, "attempt": attempt + 1, "error": str(e)},
                    )
                    continue

                if result.final_content.startswith("[Reached"):
                    failed = True
                    failure_reason = "Reached max iterations"
                    TaskStore.update_status(
                        task.id, "failed", failure_reason, increment_attempts=True
                    )
                    task.status = "failed"
                    task.result = failure_reason
                    plan_task = plan_by_desc.get(task.description)
                    if plan_task:
                        plan_task.status = "failed"
                        plan_task.result = failure_reason
                    break

                TaskStore.update_status(
                    task.id, "done", result.final_content, increment_attempts=True
                )
                task.status = "done"
                task.result = result.final_content
                task.attempts += 1
                plan_task = plan_by_desc.get(task.description)
                if plan_task:
                    plan_task.status = "done"
                    plan_task.result = result.final_content
                    plan_task.attempts = task.attempts
                self.log.info(
                    "engine_task_done",
                    extra={
                        "goal_id": goal_id,
                        "task_id": task.id,
                        "tokens": result.total_tokens,
                    },
                )
                failed = False
                failure_reason = None
                break

            if failed:
                # Все попытки исчерпаны
                self._update_goal_status(goal_id, "failed", failure_reason or "unknown")
                self.log.error(
                    "engine_goal_failed",
                    extra={
                        "goal_id": goal_id,
                        "task_id": task.id,
                        "reason": failure_reason,
                    },
                )
                task = TaskStore.get(task.id) or task
                return GoalResult(
                    goal_id=goal_id,
                    status="failed",
                    plan=plan,
                    failed_task=task,
                    failure_reason=failure_reason,
                )

        # Все задачи выполнены
        self._update_goal_status(goal_id, "done")
        self.log.info("engine_goal_done", extra={"goal_id": goal_id})

        # M1c: анализ эпизодов — извлечение skills и reflection
        try:
            from osa.runtime.skill_detector import detect_skills_for_goal
            from osa.runtime.reflection import reflect_on_goal

            detect_skills_for_goal(goal_id)
            reflect_on_goal(goal_id)
        except Exception as e:  # noqa: BLE001
            self.log.warning(
                "post_goal_analysis_failed",
                extra={"goal_id": goal_id, "error": str(e)},
            )

        return GoalResult(goal_id=goal_id, status="done", plan=plan)

    @staticmethod
    def _create_goal(description: str) -> int:
        conn = connect()
        cur = conn.execute(
            "INSERT INTO goals (description, status) VALUES (?, 'planning')",
            (description,),
        )
        goal_id = cur.lastrowid
        conn.execute(
            "UPDATE goals SET status='running' WHERE id=?", (goal_id,)
        )
        conn.commit()
        conn.close()
        return goal_id

    @staticmethod
    def _update_goal_status(goal_id: int, status: str, error: str | None = None) -> None:
        conn = connect()
        if status in ("done", "failed"):
            conn.execute(
                "UPDATE goals SET status=?, error=?, updated_at=CURRENT_TIMESTAMP, "
                "finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, error, goal_id),
            )
        else:
            conn.execute(
                "UPDATE goals SET status=?, error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, error, goal_id),
            )
        conn.commit()
        conn.close()


def run_goal(goal_text: str, react_config: ReactConfig | None = None) -> GoalResult:
    """Утилита верхнего уровня: загрузить конфиг, провайдер, запустить engine."""
    config = load_config()
    configure_logging(
        level=config.logging.level,
        json_logs=config.logging.json_logs,
    )
    provider = get_provider_for_goal(config)
    engine = GoalEngine(provider, react_config)
    return engine.run(goal_text)
