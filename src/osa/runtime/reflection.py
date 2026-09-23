"""Reflection — анализ эпизодов после завершения goal'а.

После успешного (или проваленного) выполнения goal'а reflection pass
формирует запись в таблицу reflections с:
- analysis: что произошло (краткий пересказ эпизодов)
- suggestion: что улучшить (на M1c — статичная рекомендация)

На M1c это ручной review — без auto-apply. В M1d будет рефлексия через
отдельный LLM-вызов с предложением изменений в системный промпт.
"""

from __future__ import annotations

from osa.db import connect
from osa.logging_setup import get_logger


LOGGER = get_logger("osa.reflection")


REFLECTION_PROMPT_TEMPLATE = """Goal: {goal_description}
Status: {status}
Iterations: {iterations}
Tools used: {tools_used}
Tasks planned: {tasks_count}
Tasks done: {tasks_done}

Suggestion for future similar goals:
"""


def record_reflection(
    goal_id: int,
    analysis: str,
    suggestion: str | None = None,
) -> int:
    """Записать reflection в БД. Returns reflection id."""
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO reflections (goal_id, analysis, suggestion) VALUES (?, ?, ?)",
            (goal_id, analysis, suggestion),
        )
        rid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    LOGGER.info("reflection_recorded", extra={"goal_id": goal_id, "reflection_id": rid})
    return rid or 0


def build_simple_analysis(goal_id: int) -> tuple[str, str | None]:
    """Сформировать простой анализ по эпизодам и tasks.

    Returns:
        (analysis, suggestion) — текст для записи в reflections.
    """
    conn = connect()
    try:
        goal = conn.execute(
            "SELECT description, status FROM goals WHERE id = ?", (goal_id,)
        ).fetchone()
        tasks = conn.execute(
            "SELECT status, COUNT(*) as n FROM tasks WHERE goal_id = ? GROUP BY status",
            (goal_id,),
        ).fetchall()
        episodes = conn.execute(
            "SELECT tool_name FROM episodes WHERE goal_id = ? AND tool_name IS NOT NULL",
            (goal_id,),
        ).fetchall()
    finally:
        conn.close()

    if not goal:
        return "No data", None

    from collections import Counter

    tool_counter = Counter(ep["tool_name"] for ep in episodes)
    tools_summary = ", ".join(f"{t}:{n}" for t, n in tool_counter.most_common(5))

    task_summary = ", ".join(f"{t['status']}:{t['n']}" for t in tasks)

    analysis = (
        f"Goal: {goal['description'][:120]}\n"
        f"Status: {goal['status']}\n"
        f"Tasks: {task_summary or 'none'}\n"
        f"Tools: {tools_summary or 'none'}"
    )

    # Простая эвристика для предложения
    suggestion = None
    if goal["status"] == "failed":
        suggestion = (
            "Goal failed. Проверь эпизоды — возможно задача слишком сложная "
            "и нужна декомпозиция на более мелкие шаги, или инструмент не подходит."
        )
    elif tool_counter and tool_counter.most_common(1)[0][1] >= 3:
        most_used = tool_counter.most_common(1)[0][0]
        suggestion = (
            f"Tool '{most_used}' использован {tool_counter.most_common(1)[0][1]} раз. "
            f"Возможно стоит создать skill для этого паттерна."
        )

    return analysis, suggestion


def reflect_on_goal(goal_id: int) -> int:
    """Высокоуровневый helper: анализирует goal и записывает reflection."""
    analysis, suggestion = build_simple_analysis(goal_id)
    return record_reflection(goal_id, analysis, suggestion)
