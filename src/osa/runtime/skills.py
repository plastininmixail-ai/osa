"""Skills — извлечённые паттерны успешных tool call последовательностей.

Skill (variant C по архитектурному решению) — это записанная
последовательность tool calls, которую агент переиспользует.

Формат:
    {
        "name": "list_python_files",
        "description": "Получить список .py файлов в директории",
        "steps": [
            {"tool": "file_list", "args": {"dir": "."}, "result_marker": "Python files"}
        ],
        "trigger": "find .py files"
    }

Skills создаются автоматически через SkillDetector после успешного
выполнения goal (если паттерн интересный).
Skills применяются через SkillLibrary — добавление в system prompt
executor'а как "available_skills".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from osa.db import connect


@dataclass
class SkillStep:
    """Один шаг в skill — вызов tool с аргументами."""

    tool: str
    args: dict[str, Any]
    result_marker: str | None = None  # что ожидаем получить на этом шаге


@dataclass
class Skill:
    """Извлечённый паттерн действий."""

    id: int | None = None
    name: str = ""
    description: str = ""
    steps: list[SkillStep] = field(default_factory=list)
    trigger: str | None = None  # паттерн/keyword при котором skill применим
    status: str = "experimental"  # experimental | promoted | deprecated
    version: int = 1
    success_count: int = 0
    fail_count: int = 0
    source_goal_id: int | None = None
    created_at: datetime | None = None
    last_used_at: datetime | None = None

    def to_prompt_text(self) -> str:
        """Текстовое представление для system prompt."""
        lines = [f"- **{self.name}**: {self.description}"]
        if self.trigger:
            lines.append(f"  When: {self.trigger}")
        if self.steps:
            steps_desc = " → ".join(
                f"{s.tool}({json.dumps(s.args, ensure_ascii=False)})" for s in self.steps
            )
            lines.append(f"  Steps: {steps_desc}")
        return "\n".join(lines)

    def steps_json(self) -> str:
        return json.dumps(
            [{"tool": s.tool, "args": s.args, "result_marker": s.result_marker} for s in self.steps],
            ensure_ascii=False,
        )


class SkillLibrary:
    """CRUD для skills."""

    @staticmethod
    def create(skill: Skill) -> int:
        conn = connect()
        try:
            cur = conn.execute(
                """INSERT INTO skills (name, description, steps_json, trigger_pattern, status, source_goal_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    skill.name,
                    skill.description,
                    skill.steps_json(),
                    skill.trigger,
                    skill.status,
                    skill.source_goal_id,
                ),
            )
            skill.id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        return skill.id or 0

    @staticmethod
    def get(skill_id: int) -> Skill | None:
        conn = connect()
        try:
            row = conn.execute(
                "SELECT * FROM skills WHERE id = ?", (skill_id,)
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return _row_to_skill(row)

    @staticmethod
    def get_by_name(name: str) -> Skill | None:
        conn = connect()
        try:
            row = conn.execute(
                "SELECT * FROM skills WHERE name = ?", (name,)
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return _row_to_skill(row)

    @staticmethod
    def list_all(
        status: str | None = None,
        limit: int = 50,
    ) -> list[Skill]:
        conn = connect()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM skills WHERE status = ? ORDER BY id DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM skills ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        finally:
            conn.close()
        return [_row_to_skill(r) for r in rows]

    @staticmethod
    def delete(skill_id: int) -> None:
        conn = connect()
        try:
            conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def promote(skill_id: int) -> None:
        """Promote skill: experimental → promoted."""
        conn = connect()
        try:
            conn.execute(
                "UPDATE skills SET status = 'promoted' WHERE id = ?", (skill_id,)
            )
            conn.commit()
        finally:
            conn.close()


def _row_to_skill(row: Any) -> Skill:
    steps_data = json.loads(row["steps_json"]) if row["steps_json"] else []
    steps = [SkillStep(**s) for s in steps_data]
    return Skill(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        steps=steps,
        trigger=row["trigger_pattern"],
        status=row["status"],
        version=row["version"],
        success_count=row["success_count"],
        fail_count=row["fail_count"],
        source_goal_id=row["source_goal_id"],
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
    )
