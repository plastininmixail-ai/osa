"""CLI интерфейс O.S.A.

Команды на M0 (4 штуки):
    osa init   — инициализировать OSA_HOME
    osa goal   — поставить цель (синхронно, через LLM)
    osa status — показать последние цели
    osa logs   — показать логи
"""

from __future__ import annotations

from typing import Optional

import typer

from osa import __version__

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
def goal(text: str = typer.Argument(..., help="Текст цели")) -> None:
    """Поставить цель агенту (синхронно, ждёт первый ответ)."""
    from osa.config import load_config
    from osa.db import connect, get_provider_for_goal
    from osa.logging_setup import configure_logging, get_logger

    config = load_config()
    configure_logging(
        level=config.logging.level,
        json_logs=config.logging.json_logs,
    )
    log = get_logger("osa.cli")

    provider = get_provider_for_goal(config)

    log.info("goal_started", extra={"text": text, "provider": config.llm.provider})

    conn = connect()
    cur = conn.execute(
        "INSERT INTO goals (description, status) VALUES (?, 'running')",
        (text,),
    )
    goal_id = cur.lastrowid
    conn.commit()

    try:
        from osa.llm.base import LLMMessage

        messages = [
            LLMMessage(
                role="system",
                content="Ты — Урс, автономный агент OSA. Отвечай кратко и по делу.",
            ),
            LLMMessage(role="user", content=text),
        ]
        response = provider.complete(messages)
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
        (goal_id, response.content, response.tokens_used),
    )
    conn.execute(
        "UPDATE goals SET status='done', result=?, updated_at=CURRENT_TIMESTAMP, "
        "finished_at=CURRENT_TIMESTAMP WHERE id=?",
        (response.content, goal_id),
    )
    conn.commit()
    conn.close()

    log.info("goal_done", extra={"goal_id": goal_id, "tokens": response.tokens_used})
    typer.echo(response.content)


@app.command()
def status() -> None:
    """Показать последние цели."""
    from osa.db import connect

    conn = connect()
    goals = conn.execute(
        "SELECT id, description, status, created_at, finished_at "
        "FROM goals ORDER BY id DESC LIMIT 10"
    ).fetchall()
    conn.close()

    if not goals:
        typer.echo("No goals yet")
        return

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

    # Follow mode
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
