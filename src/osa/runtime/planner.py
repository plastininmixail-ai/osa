"""Goal Engine — декомпозиция цели в дерево подзадач и выполнение.

Архитектура:
    GoalEngine.run(goal_text)
        ├─ Planner.plan(goal_text)              # LLM возвращает список задач
        ├─ TaskExecutor.execute(task)            # для каждой задачи запускает ReactLoop
        │     └─ ReAct loop с tools
        ├─ Replanner.replan(failed_task)         # если задача провалилась
        └─ StatusReporter                        # обновляет status в tasks/goals
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from osa.db import connect
from osa.llm.base import LLMMessage, LLMProvider
from osa.logging_setup import get_logger
from osa.runtime.react import ReactConfig, ReactLoop, ReactResult
from osa.tools import builtin as builtin_tools
from osa.tools import registry as tool_registry


PLANNER_SYSTEM_PROMPT = """Ты — планировщик задач для автономного агента OSA.

Твоя задача: разбить глобальную цель пользователя на 3-7 конкретных подзадач.

Правила:
1. Каждая подзадача — конкретное действие, которое агент может выполнить.
2. Подзадачи должны быть в логическом порядке (зависимости).
3. Если задача простая и не требует разбивки — верни одну подзадачу с полным описанием.
4. Используй те же инструменты что описаны в goal (если указаны).
5. Формат ответа — ТОЛЬКО JSON, без пояснений до или после.

Схема ответа (строго JSON):
{
  "tasks": [
    {"description": "что нужно сделать", "rationale": "почему это нужно"},
    ...
  ]
}

ВАЖНО: ответ должен быть валидным JSON. Никакого текста вне JSON.
"""


MAX_TASK_ATTEMPTS = 3


@dataclass
class Task:
    """Описание одной подзадачи."""

    description: str
    rationale: str = ""
    # DB fields (заполняются после insert)
    id: int | None = None
    status: str = "pending"  # pending, running, done, failed, blocked
    result: str | None = None
    attempts: int = 0


@dataclass
class Plan:
    """Декомпозиция цели."""

    goal_text: str
    tasks: list[Task] = field(default_factory=list)


class Planner:
    """Разбивает цель на список подзадач через LLM."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        self.log = get_logger("osa.planner")

    def plan(self, goal_text: str) -> Plan:
        """Запросить у LLM декомпозицию цели."""
        messages = [
            LLMMessage(role="system", content=PLANNER_SYSTEM_PROMPT),
            LLMMessage(role="user", content=f"Цель: {goal_text}"),
        ]

        response = self.provider.complete(
            messages,
            temperature=0.3,
            max_tokens=2000,
        )

        tasks = self._parse_plan(response.content, goal_text)
        self.log.info(
            "plan_created",
            extra={
                "goal": goal_text[:100],
                "tasks_count": len(tasks),
            },
        )
        return Plan(goal_text=goal_text, tasks=tasks)

    def _parse_plan(self, content: str, goal_text: str) -> list[Task]:
        """Парсить JSON-ответ от LLM в список Task. С fallback на single-task plan."""
        json_str = self._extract_json(content)
        if not json_str:
            self.log.warning("planner_no_json", extra={"content": content[:200]})
            return [Task(description=goal_text, rationale="Single-task fallback")]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            self.log.warning(
                "planner_json_error", extra={"error": str(e), "json": json_str[:200]}
            )
            return [Task(description=goal_text, rationale="JSON parse error fallback")]

        raw_tasks = data.get("tasks", [])
        if not raw_tasks:
            return [Task(description=goal_text, rationale="Empty plan fallback")]

        tasks = []
        for raw in raw_tasks:
            if not isinstance(raw, dict):
                continue
            desc = raw.get("description", "").strip()
            if not desc:
                continue
            tasks.append(
                Task(
                    description=desc,
                    rationale=raw.get("rationale", "").strip(),
                )
            )

        if not tasks:
            return [Task(description=goal_text, rationale="Empty tasks fallback")]

        return tasks

    @staticmethod
    def _extract_json(content: str) -> str | None:
        """Найти JSON-объект в ответе."""
        content = content.strip()
        if content.startswith("{"):
            return content

        if "```" in content:
            parts = content.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    return part

        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            return content[start : end + 1]

        return None


class TaskStore:
    """CRUD для таблицы tasks в БД."""

    @staticmethod
    def create(goal_id: int, task: Task, parent_id: int | None = None) -> int:
        conn = connect()
        cur = conn.execute(
            "INSERT INTO tasks (goal_id, parent_id, description, status) "
            "VALUES (?, ?, ?, 'pending')",
            (goal_id, parent_id, task.description),
        )
        task.id = cur.lastrowid
        conn.commit()
        conn.close()
        return task.id

    @staticmethod
    def update_status(
        task_id: int,
        status: str,
        result: str | None = None,
        increment_attempts: bool = False,
    ) -> None:
        conn = connect()
        if status == "done" or status == "failed":
            finished_clause = ", finished_at=CURRENT_TIMESTAMP"
        else:
            finished_clause = ""
        attempts_clause = (
            ", attempts = attempts + 1" if increment_attempts else ""
        )
        conn.execute(
            f"UPDATE tasks SET status=?, result=?, "
            f"updated_at=CURRENT_TIMESTAMP{finished_clause}{attempts_clause} "
            f"WHERE id=?",
            (status, result, task_id),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get(task_id: int) -> Task | None:
        conn = connect()
        row = conn.execute(
            "SELECT * FROM tasks WHERE id=?", (task_id,)
        ).fetchone()
        conn.close()
        if not row:
            return None
        return Task(
            id=row["id"],
            description=row["description"],
            rationale=(row["rationale"] if "rationale" in row.keys() else None) or "",
            status=row["status"],
            result=row["result"],
            attempts=(row["attempts"] if "attempts" in row.keys() else None) or 0,
        )

    @staticmethod
    def list_pending_for_goal(goal_id: int) -> list[Task]:
        conn = connect()
        rows = conn.execute(
            "SELECT * FROM tasks WHERE goal_id=? AND status IN ('pending', 'failed') "
            "ORDER BY id ASC",
            (goal_id,),
        ).fetchall()
        conn.close()
        return [
            Task(
                id=r["id"],
                description=r["description"],
                rationale=(r["rationale"] if "rationale" in r.keys() else None) or "",
                status=r["status"],
                result=r["result"],
                attempts=(r["attempts"] if "attempts" in r.keys() else None) or 0,
            )
            for r in rows
        ]


class TaskExecutor:
    """Выполняет одну подзадачу через ReactLoop."""

    def __init__(
        self,
        provider: LLMProvider,
        config: ReactConfig | None = None,
    ) -> None:
        self.provider = provider
        self.config = config or ReactConfig()
        self.log = get_logger("osa.executor")

    def execute(self, task: Task) -> ReactResult:
        """Запустить ReactLoop для одной подзадачи."""
        self.log.info(
            "task_executing",
            extra={"task_id": task.id, "description": task.description[:100]},
        )

        # Регистрируем встроенные инструменты
        tool_registry.reset()
        builtin_tools.register_all()

        loop = ReactLoop(
            provider=self.provider,
            tools=tool_registry.all_tools(),
            config=self.config,
        )
        result = loop.run(task.description)

        self.log.info(
            "task_executed",
            extra={
                "task_id": task.id,
                "iterations": result.iterations,
                "tokens": result.total_tokens,
                "finished": not result.final_content.startswith("[Reached"),
            },
        )
        return result
