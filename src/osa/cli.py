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


@app.command()
def serve(
    transport: str = typer.Option("telegram", "--transport", "-t", help="Тип транспорта: telegram"),
) -> None:
    """Запустить сервер для внешних клиентов (Telegram бот и т.д.)."""
    from osa.config import load_config
    from osa.logging_setup import configure_logging

    config = load_config()
    configure_logging(
        level=config.logging.level,
        json_logs=config.logging.json_logs,
    )

    if transport == "telegram":
        from osa.transports.telegram import run_telegram_bot
        run_telegram_bot(config)
    else:
        typer.echo(f"Неизвестный transport: {transport!r}. Поддерживается: telegram")
        raise typer.Exit(1)


@app.command()
def skills(
    show_id: int | None = typer.Option(None, "--show", "-s", help="Показать детали skill по ID"),
    status_filter: str | None = typer.Option(
        None, "--status", help="Фильтр по статусу: experimental | promoted | deprecated"
    ),
    limit: int = typer.Option(20, "-n", help="Максимум записей"),
) -> None:
    """Показать извлечённые skills (навыки)."""
    from osa.runtime.skills import SkillLibrary

    if show_id is not None:
        skill = SkillLibrary.get(show_id)
        if not skill:
            typer.echo(f"Skill #{show_id} не найден")
            raise typer.Exit(1)
        typer.echo(f"#{skill.id} **{skill.name}** [{skill.status}]")
        typer.echo(f"  {skill.description}")
        if skill.trigger:
            typer.echo(f"  When: {skill.trigger}")
        if skill.steps:
            typer.echo("  Steps:")
            for i, s in enumerate(skill.steps, 1):
                typer.echo(f"    {i}. {s.tool}({s.args})")
        typer.echo(f"\n  Success: {skill.success_count}, Fail: {skill.fail_count}")
        typer.echo(f"  Source goal: #{skill.source_goal_id}")
        return

    items = SkillLibrary.list_all(status=status_filter, limit=limit)
    if not items:
        typer.echo("Skills пока нет. Запустите goal чтобы они появились автоматически.")
        return

    typer.echo(f"📚 Skills ({len(items)}):\n")
    for s in items:
        status_emoji = {"experimental": "🧪", "promoted": "✅", "deprecated": "⛔"}.get(
            s.status, "·"
        )
        typer.echo(f"{status_emoji} #{s.id} **{s.name}** — {s.description[:80]}")
    typer.echo(f"\nПоказать детали: osa skills --show <id>")


@app.command()
def reflections(
    goal_id: int | None = typer.Option(None, "--goal", "-g", help="Reflection для конкретного goal"),
    limit: int = typer.Option(10, "-n", help="Максимум записей"),
) -> None:
    """Показать reflection (анализ прошлых задач)."""
    from osa.db import connect

    conn = connect()
    try:
        if goal_id is not None:
            rows = conn.execute(
                "SELECT * FROM reflections WHERE goal_id = ? ORDER BY id DESC",
                (goal_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reflections ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
    finally:
        conn.close()

    if not rows:
        typer.echo("Reflections пока нет.")
        return

    typer.echo(f"💡 Reflections ({len(rows)}):\n")
    for r in rows:
        typer.echo(f"--- Reflection #{r['id']} (goal #{r['goal_id']}) ---")
        typer.echo(r["analysis"])
        if r["suggestion"]:
            typer.echo(f"\n💡 Suggestion: {r['suggestion']}")
        typer.echo("")


@app.command()
def benchmark(
    goal_id: str | None = typer.Option(None, "--goal", "-g", help="Запустить только эту цель"),
    attempts: int = typer.Option(1, "-n", help="Попыток на каждую цель"),
    list_only: bool = typer.Option(False, "--list", "-l", help="Только показать список целей"),
    auto_approve: bool = typer.Option(True, "--yes/--no-yes", help="Авто-одобрение shell"),
) -> None:
    """Запустить бенчмарк на эталонных целях.

    Бенчмарк запускает каждую цель attempts раз и собирает метрики:
    success rate, время, токены. Используется для проверки формулы
    'маленькая модель + scaffolding > голая модель'.
    """
    from osa.config import load_config
    from osa.db import get_provider_for_goal
    from osa.logging_setup import configure_logging
    from osa.runtime.benchmark import BENCHMARK_GOALS, run_benchmark

    if list_only:
        typer.echo("📊 Эталонные цели для бенчмарка:\n")
        for goal in BENCHMARK_GOALS:
            typer.echo(f"• {goal.id}")
            typer.echo(f"  {goal.description[:120]}...")
            typer.echo(f"  Expected: {', '.join(goal.expected_files)}")
            typer.echo()
        return

    config = load_config()
    configure_logging(
        level=config.logging.level,
        json_logs=config.logging.json_logs,
    )
    provider = get_provider_for_goal(config)

    goals = BENCHMARK_GOALS
    if goal_id:
        goals = [g for g in goals if g.id == goal_id]
        if not goals:
            typer.echo(f"Цель {goal_id!r} не найдена")
            raise typer.Exit(1)

    typer.echo(f"🏃 Запускаю бенчмарк: {len(goals)} целей × {attempts} попыток")
    typer.echo(f"Провайдер: {config.llm.provider}\n")

    report = run_benchmark(goals, provider, attempts_per_goal=attempts)

    typer.echo("\n" + report.format_text())


@app.command()
def chatlog(
    lines: int = typer.Option(50, "-n", "--lines", help="Количество последних строк"),
    clear: bool = typer.Option(False, "--clear", help="Очистить лог (осторожно)"),
    path: Path | None = typer.Option(None, "--path", help="Путь к файлу лога"),
) -> None:
    """Показать историю переписки (chat_log.txt)."""
    from osa.runtime.chat_logger import ChatLogger

    if path is None:
        path = None  # ChatLogger возьмёт default

    logger = ChatLogger(log_path=path)

    if clear:
        typer.confirm(
            f"Точно очистить {logger.log_path}?", abort=True
        )
        logger.clear()
        typer.echo(f"✅ Очищено: {logger.log_path}")
        return

    if not logger.log_path.exists():
        typer.echo(f"📭 Лог ещё не создан: {logger.log_path}")
        typer.echo("Отправь боту любое сообщение — лог начнёт заполняться.")
        return

    content = logger.read()
    all_lines = content.splitlines()
    last_lines = all_lines[-lines:] if lines > 0 else all_lines
    typer.echo(f"💬 Последние {len(last_lines)} строк из {logger.log_path}:\n")
    typer.echo("\n".join(last_lines))


@app.command()
def baseline(
    goal_id: str | None = typer.Option(None, "--goal", "-g", help="Запустить только эту цель"),
) -> None:
    """Baseline: голая модель без инструментов и scaffolding.

    Используется для сравнения с `osa benchmark` — доказательство
    что фреймворк добавляет ценность.
    """
    from osa.config import load_config
    from osa.db import get_provider_for_goal
    from osa.logging_setup import configure_logging
    from osa.runtime.benchmark import BENCHMARK_GOALS, run_baseline_one_shot

    config = load_config()
    configure_logging(
        level=config.logging.level,
        json_logs=config.logging.json_logs,
    )
    provider = get_provider_for_goal(config)

    goals = BENCHMARK_GOALS
    if goal_id:
        goals = [g for g in goals if g.id == goal_id]
        if not goals:
            typer.echo(f"Цель {goal_id!r} не найдена")
            raise typer.Exit(1)

    typer.echo(f"📊 Baseline (голая модель, {len(goals)} целей)\n")

    for goal in goals:
        typer.echo(f"--- {goal.id} ---")
        typer.echo(f"Goal: {goal.description[:100]}...")
        response, tokens = run_baseline_one_shot(provider, goal.description)
        typer.echo(f"Tokens: {tokens}")
        typer.echo(f"Response (первые 300 chars):\n{response[:300]}")
        typer.echo()
