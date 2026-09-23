"""SkillDetector — извлечение паттернов из эпизодов.

После успешного выполнения goal анализируем эпизоды (tool calls +
observations) и предлагаем skill если:
- Паттерн нетривиален (>= 2 шагов)
- Использовался один и тот же tool несколько раз
- Или последовательность tool'ов образует логичный workflow

На M1c — простая эвристика:
- Берём последние N эпизодов goal'а
- Группируем по tool name
- Если один tool использовался >= 2 раз → кандидат на skill
- Генерируем описание и сохраняем в БД

Реальная LLM-based детекция будет в M1d (через отдельный reflection pass).
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from osa.db import connect
from osa.logging_setup import get_logger
from osa.runtime.skills import Skill, SkillLibrary, SkillStep


LOGGER = get_logger("osa.skill_detector")

MIN_REPEATS_FOR_SKILL = 2
MIN_DISTINCT_TOOLS = 1


def detect_skills_for_goal(goal_id: int) -> list[Skill]:
    """Анализирует эпизоды goal'а и создаёт skills если находит повторяющиеся паттерны.

    Returns:
        Список созданных Skill объектов.
    """
    conn = connect()
    try:
        # Получаем эпизоды для goal'а (только act и observe)
        episodes = conn.execute(
            """SELECT step_type, content, tool_name, tool_args
               FROM episodes
               WHERE goal_id = ? AND step_type IN ('act', 'observe')
               ORDER BY id ASC""",
            (goal_id,),
        ).fetchall()

        # Получаем описание goal'а для контекста
        goal_row = conn.execute(
            "SELECT description FROM goals WHERE id = ?", (goal_id,)
        ).fetchone()
    finally:
        conn.close()

    if not episodes:
        return []

    goal_desc = goal_row["description"] if goal_row else "unknown"

    # Группируем tool calls по имени
    tool_calls = []
    for ep in episodes:
        if ep["step_type"] == "act" and ep["tool_name"]:
            try:
                args = json.loads(ep["tool_args"]) if ep["tool_args"] else {}
            except json.JSONDecodeError:
                args = {}
            tool_calls.append({"tool": ep["tool_name"], "args": args})

    if not tool_calls:
        return []

    # Подсчитываем повторения
    counter = Counter(tc["tool"] for tc in tool_calls)
    repeated = {tool: count for tool, count in counter.items() if count >= MIN_REPEATS_FOR_SKILL}

    if not repeated:
        return []

    LOGGER.info(
        "skill_detector_repeated_tools",
        extra={"goal_id": goal_id, "tools": repeated},
    )

    # Создаём skill для самого повторяемого tool
    created: list[Skill] = []
    for tool_name, count in sorted(repeated.items(), key=lambda x: -x[1]):
        # Берём первый args как пример
        example_args = next(
            (tc["args"] for tc in tool_calls if tc["tool"] == tool_name),
            {},
        )
        skill = Skill(
            name=f"use_{tool_name}_pattern",
            description=f"Использовать {tool_name} (наблюдалось {count} раз в задаче: {goal_desc[:80]})",
            steps=[SkillStep(tool=tool_name, args=example_args, result_marker=None)],
            trigger=f"когда нужно {tool_name}",
            source_goal_id=goal_id,
            status="experimental",
        )
        try:
            SkillLibrary.create(skill)
            created.append(skill)
            LOGGER.info(
                "skill_created",
                extra={"skill_id": skill.id, "name": skill.name, "source_goal": goal_id},
            )
        except Exception as e:
            LOGGER.warning(
                "skill_creation_failed",
                extra={"name": skill.name, "error": str(e)},
            )

    return created
