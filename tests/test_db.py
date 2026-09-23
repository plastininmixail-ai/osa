"""Тесты osa.db."""

from __future__ import annotations

import sqlite3

import pytest


def test_init_db_creates_three_tables(tmp_osa_home) -> None:
    """После init_db есть goals, episodes, schema_version."""
    from osa.db import init_db

    init_db()

    conn = sqlite3.connect(tmp_osa_home / "osa.db")
    conn.row_factory = sqlite3.Row
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()

    assert "goals" in tables
    assert "episodes" in tables
    assert "schema_version" in tables


def test_init_db_applies_migration(tmp_osa_home) -> None:
    """schema_version содержит последнюю применённую миграцию после init_db."""
    from osa.db import init_db

    init_db()

    conn = sqlite3.connect(tmp_osa_home / "osa.db")
    version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    conn.close()

    assert version >= 1


def test_init_db_is_idempotent(tmp_osa_home) -> None:
    """Повторный init не падает и не дублирует миграции."""
    from osa.db import init_db

    init_db()
    init_db()
    init_db()

    conn = sqlite3.connect(tmp_osa_home / "osa.db")
    count = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    versions = sorted(r[0] for r in conn.execute("SELECT version FROM schema_version").fetchall())
    conn.close()

    # Каждая версия применена ровно один раз
    assert versions == sorted(set(versions))


def test_goals_indexes_exist(tmp_osa_home) -> None:
    """Индексы на goals созданы."""
    from osa.db import connect, init_db

    init_db()

    conn = connect()
    indexes = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    conn.close()

    assert "idx_goals_status" in indexes
    assert "idx_goals_created" in indexes


def test_episode_foreign_key_enforced(tmp_osa_home) -> None:
    """FK между episodes.goal_id и goals.id работает."""
    from osa.db import init_db

    init_db()

    conn = sqlite3.connect(tmp_osa_home / "osa.db")
    conn.execute("PRAGMA foreign_keys = ON")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO episodes (goal_id, step_type, content) "
            "VALUES (9999, 'observe', 'orphan')"
        )
    conn.close()


def test_insert_and_select_goal(tmp_osa_home) -> None:
    """Insert + Select работают."""
    from osa.db import connect, init_db

    init_db()

    conn = connect()
    cur = conn.execute(
        "INSERT INTO goals (description, status) VALUES (?, 'done')",
        ("тест",),
    )
    goal_id = cur.lastrowid
    conn.commit()

    row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    conn.close()

    assert row["description"] == "тест"
    assert row["status"] == "done"


def test_provider_factory_stub(tmp_osa_home) -> None:
    """Фабрика возвращает StubProvider для provider=stub."""
    from osa.config import OSAConfig
    from osa.db import get_provider_for_goal
    from osa.llm.stub import StubProvider

    config = OSAConfig()
    config.llm.provider = "stub"
    provider = get_provider_for_goal(config)

    assert isinstance(provider, StubProvider)


def test_provider_factory_unknown_raises(tmp_osa_home) -> None:
    """Неизвестный провайдер → ValueError."""
    from osa.config import OSAConfig
    from osa.db import get_provider_for_goal

    config = OSAConfig()
    config.llm.provider = "does_not_exist"  # type: ignore[assignment]

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_provider_for_goal(config)
