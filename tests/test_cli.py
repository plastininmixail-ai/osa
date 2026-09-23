"""Интеграционные тесты CLI через typer.testing.CliRunner."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from osa.cli import app

runner = CliRunner()


def test_help_shows_all_commands(tmp_osa_home) -> None:
    """osa --help показывает 4 команды."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "goal" in result.stdout
    assert "status" in result.stdout
    assert "logs" in result.stdout


def test_version_flag(tmp_osa_home) -> None:
    """--version показывает версию и выходит."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "osa" in result.stdout
    assert "0.0.1" in result.stdout


def test_init_creates_osa_home_structure(tmp_osa_home) -> None:
    """osa init создаёт БД, sandbox, config.toml."""
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert tmp_osa_home.exists()
    assert (tmp_osa_home / "osa.db").exists()
    assert (tmp_osa_home / "sandbox").exists()


def test_goal_with_stub_writes_to_db(tmp_osa_home) -> None:
    """osa goal со stub создаёт goal и tasks в БД (через GoalEngine)."""
    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["goal", "привет"])
    assert result.exit_code == 0
    # Новый вывод: plan summary + статус
    assert "Цель: привет" in result.stdout
    assert "Статус: done" in result.stdout

    # Проверка БД
    from osa.db import connect

    conn = connect()
    goals = conn.execute("SELECT * FROM goals").fetchall()
    assert len(goals) == 1
    assert goals[0]["description"] == "привет"
    assert goals[0]["status"] == "done"

    tasks = conn.execute("SELECT * FROM tasks WHERE goal_id=?", (goals[0]["id"],)).fetchall()
    assert len(tasks) >= 1
    assert all(t["status"] == "done" for t in tasks)
    conn.close()


def test_status_empty(tmp_osa_home) -> None:
    """osa status без целей показывает daemon status и не падает."""
    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Daemon: not running" in result.stdout


def test_status_shows_goals(tmp_osa_home) -> None:
    """osa status показывает несколько целей."""
    runner.invoke(app, ["init"])
    runner.invoke(app, ["goal", "первая"])
    runner.invoke(app, ["goal", "вторая"])

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "первая" in result.stdout
    assert "вторая" in result.stdout


def test_logs_shows_recent_records(tmp_osa_home) -> None:
    """osa logs читает из файла."""
    runner.invoke(app, ["init"])
    runner.invoke(app, ["goal", "test"])

    result = runner.invoke(app, ["logs"])
    assert result.exit_code == 0
    # Хотя бы одна запись — goal_started или goal_done
    assert "goal_started" in result.stdout or "goal_done" in result.stdout


def test_logs_no_file(tmp_osa_home) -> None:
    """osa logs без файла говорит 'No logs yet'."""
    result = runner.invoke(app, ["logs"])
    assert result.exit_code == 0
    assert "No logs yet" in result.stdout
