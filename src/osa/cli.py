"""CLI интерфейс O.S.A."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer

from osa import __version__

# Загрузка .env из текущей директории при импорте CLI
# (нужно для подхвата OSA_LLM__API_KEY и других секретов)
_CLAVE_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
if _CLAVE_ENV_PATH.exists():
    for line in _CLAVE_ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Не перезаписываем уже установленные переменные
        if key and key not in os.environ:
            os.environ[key] = value

app = typer.Typer(
    name="osa",
    help="O.S.A. — Операционная Система Агента",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"osa {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", callback=_version_callback, is_eager=True, help="Показать версию"
    ),
) -> None:
    """O.S.A. CLI."""


@app.command(hidden=True)
def daemon_run() -> None:
    """Внутренняя команда — запускает демон. Не для пользователей."""
    from osa.runtime.daemon import run_forever

    run_forever()


@app.command()
def init() -> None:
    """Инициализировать OSA_HOME (БД, конфиг, директории)."""
    from osa.config import save_default_config
    from osa.db import init_db
    from osa.paths import config_path, db_path, log_dir, osa_home, sandbox_dir

    home = osa_home()
    home.mkdir(parents=True, exist_ok=True)
    sandbox_dir().mkdir(parents=True, exist_ok=True)
    log_dir().mkdir(parents=True, exist_ok=True)

    config_path().parent.mkdir(parents=True, exist_ok=True)
    if not config_path().exists():
        save_default_config(config_path())

    init_db()

    typer.echo(f"OSA initialized at {home}")
    typer.echo(f"  DB:       {db_path()}")
    typer.echo(f"  Config:   {config_path()}")
    typer.echo(f"  Sandbox:  {sandbox_dir()}")
    typer.echo(f"  Logs:     {log_dir()}")


@app.command()
def goal(
    text: str = typer.Argument(..., help="Текст цели"),
    auto_approve: bool = typer.Option(
        False, "--yes", "-y", help="Автоматически подтверждать опасные инструменты"
    ),
    plan: bool = typer.Option(
        True, "--plan/--no-plan", help="Декомпозировать цель на подзадачи"
    ),
) -> None:
    """Поставить цель агенту (синхронно, ждёт первый ответ)."""
    from osa.config import load_config
    from osa.db import connect, get_provider_for_goal
    from osa.logging_setup import configure_logging, get_logger
    from osa.runtime.engine import GoalEngine, run_goal
    from osa.runtime.react import ReactConfig
    from osa.tools import builtin as builtin_tools
    from osa.tools import registry as tool_registry

    config = load_config()
    configure_logging(
        level=config.logging.level,
        json_logs=config.logging.json_logs,
    )
    log = get_logger("osa.cli")
    react_config = ReactConfig(auto_approve=auto_approve)

    log.info(
        "goal_started",
        extra={
            "text": text,
            "provider": config.llm.provider,
            "auto_approve": auto_approve,
            "use_planner": plan,
        },
    )

    if plan:
        # Декомпозиция через GoalEngine
        try:
            result = run_goal(text, react_config)
        except Exception as e:
            log.error("goal_failed", extra={"error": str(e)}, exc_info=True)
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1) from e

        typer.echo(result.plan_text_summary())
        typer.echo(f"\nСтатус: {result.status}")
        if result.failed_task:
            typer.echo(f"Провалена задача: {result.failed_task.description[:80]}")
            typer.echo(f"Причина: {result.failure_reason}")
        return

    # Старый путь — без декомпозиции, прямой ReAct loop
    tool_registry.reset()
    builtin_tools.register_all()
    provider = get_provider_for_goal(config)

    conn = connect()
    cur = conn.execute(
        "INSERT INTO goals (description, status) VALUES (?, 'running')",
        (text,),
    )
    goal_id = cur.lastrowid
    conn.commit()

    try:
        from osa.runtime.react import ReactLoop

        loop = ReactLoop(
            provider=provider,
            tools=tool_registry.all_tools(),
            config=react_config,
        )
        result = loop.run(text)
    except Exception as e:
        log.error("goal_failed", extra={"error": str(e)}, exc_info=True)
        conn.execute(
            "UPDATE goals SET status='failed', error=?, updated_at=CURRENT_TIMESTAMP, "
            "finished_at=CURRENT_TIMESTAMP WHERE id=?",
            (str(e), goal_id),
        )
        conn.commit()
        conn.close()
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e

    conn.execute(
        "INSERT INTO episodes (goal_id, step_type, content, tokens_used) "
        "VALUES (?, 'observe', ?, ?)",
        (goal_id, f"step_{1}: {result.steps[0].thought[:500] if result.steps else ''}", 0),
    )
    conn.execute(
        "INSERT INTO episodes (goal_id, step_type, content, tokens_used) "
        "VALUES (?, 'observe', ?, ?)",
        (goal_id, result.final_content[:5000], result.total_tokens),
    )

    status = "done" if not result.final_content.startswith("[Reached") else "failed"
    conn.execute(
        "UPDATE goals SET status=?, result=?, updated_at=CURRENT_TIMESTAMP, "
        "finished_at=CURRENT_TIMESTAMP WHERE id=?",
        (status, result.final_content, goal_id),
    )
    conn.commit()
    conn.close()

    log.info(
        "goal_done",
        extra={
            "goal_id": goal_id,
            "iterations": result.iterations,
            "tokens": result.total_tokens,
        },
    )
    typer.echo(result.final_content)


@app.command()
def start() -> None:
    """Запустить демон в фоне."""
    from osa.runtime.daemon import is_running, start

    running, existing_pid = is_running()
    if running:
        typer.echo(f"OSA уже запущен (pid={existing_pid})")
        raise typer.Exit(1)

    pid = start()
    typer.echo(f"OSA daemon started (pid={pid})")
    typer.echo("Логи: osa logs --follow")


@app.command()
def stop() -> None:
    """Остановить демон (graceful)."""
    from osa.runtime.daemon import is_running, stop

    running, existing_pid = is_running()
    if not running:
        typer.echo("OSA не запущен")
        return

    typer.echo(f"Останавливаю демон (pid={existing_pid})...")
    ok = stop()
    if ok:
        typer.echo("Остановлен")
    else:
        typer.echo("Остановлен через SIGKILL (не отвечал)")


@app.command()
def status() -> None:
    """Показать состояние демона и последние цели."""
    import sqlite3

    from osa.db import connect
    from osa.runtime.daemon import is_running

    # Daemon status
    conn = connect()
    daemon = conn.execute(
        "SELECT * FROM daemon_state WHERE id=1"
    ).fetchone()
    running, pid = is_running()

    if daemon and daemon["status"] != "stopped":
        uptime = ""
        if daemon["started_at"]:
            started = daemon["started_at"]
            typer.echo(
                f"Daemon: pid={daemon['pid']}, status={daemon['status']}, "
                f"started={started}, heartbeat={daemon['last_heartbeat']}"
            )
        else:
            typer.echo(f"Daemon: pid={daemon['pid']}, status={daemon['status']}")
    elif running:
        typer.echo(f"Daemon: running pid={pid}")
    else:
        typer.echo("Daemon: not running")

    # Goals
    goals = conn.execute(
        "SELECT id, description, status, created_at, finished_at "
        "FROM goals ORDER BY id DESC LIMIT 10"
    ).fetchall()
    conn.close()

    if goals:
        typer.echo("")
        typer.echo(f"{'ID':<6} {'Status':<10} {'Created':<20} Description")
        typer.echo("-" * 80)
        for g in goals:
            desc = g["description"][:50] + ("..." if len(g["description"]) > 50 else "")
            typer.echo(f"{g['id']:<6} {g['status']:<10} {g['created_at']:<20} {desc}")


@app.command()
def logs(
    follow: bool = typer.Option(False, "--follow", "-f", help="Следить за новыми записями"),
    level: str = typer.Option("info", "--level", "-l", help="Минимальный уровень"),
    lines: int = typer.Option(50, "-n", help="Количество последних строк"),
) -> None:
    """Показать последние лог-записи."""
    import json
    import time

    from osa.paths import log_dir

    log_file = log_dir() / "osa.jsonl"
    if not log_file.exists():
        typer.echo("No logs yet")
        return

    levels = {"debug": 10, "info": 20, "warning": 30, "error": 40}
    min_level = levels.get(level.lower(), 20)

    def show_line(line: str) -> bool:
        try:
            record = json.loads(line)
            return levels.get(record.get("level", "info").lower(), 20) >= min_level
        except json.JSONDecodeError:
            return True

    if not follow:
        with log_file.open("r", encoding="utf-8") as f:
            recent = f.readlines()[-lines:]
        for line in recent:
            if show_line(line):
                typer.echo(line.rstrip())
        return

    with log_file.open("r", encoding="utf-8") as f:
        existing = f.readlines()[-lines:]
        for line in existing:
            if show_line(line):
                typer.echo(line.rstrip())
        while True:
            line = f.readline()
            if line:
                if show_line(line):
                    typer.echo(line.rstrip())
            else:
                time.sleep(0.5)
