"""SQLite подключение, миграции и фабрика LLM-провайдера.

Миграции хранятся в src/osa/migrations/*.sql, упаковываются в wheel через
[tool.hatch.build.targets.wheel.force-include] в pyproject.toml.
"""

from __future__ import annotations

import sqlite3
from importlib.resources import files
from pathlib import Path

from osa.config import OSAConfig, load_config
from osa.llm.base import LLMProvider
from osa.paths import db_path


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Подключиться к БД с разумными дефолтами.

    - WAL mode для одновременных читателей
    - row_factory=Row для доступа к колонкам по имени
    - foreign_keys=ON для целостности ссылок
    """
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _migrations_dir() -> Path:
    """Получить путь к директории миграций внутри пакета."""
    traversable = files("osa.migrations")
    return Path(str(traversable))


def migrate(conn: sqlite3.Connection) -> None:
    """Применить все миграции, которых ещё нет в schema_version."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()
    current = row[0] if row else 0

    migrations_path = _migrations_dir()
    sql_files = sorted(p for p in migrations_path.iterdir() if p.suffix == ".sql")

    for sql_file in sql_files:
        # Имя файла: 001_init.sql → version = 1
        version = int(sql_file.stem.split("_")[0])
        if version > current:
            sql = sql_file.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (version,)
            )
            conn.commit()


def init_db() -> None:
    """Инициализировать БД (создать файл, применить миграции).

    Идемпотентна: повторный вызов не падает.
    """
    conn = connect()
    try:
        migrate(conn)
    finally:
        conn.close()


def get_provider_for_goal(config: OSAConfig | None = None) -> LLMProvider:
    """Фабрика LLM-провайдера по конфигу.

    Lazy imports чтобы избежать циклических импортов и не тянуть httpx
    там, где он не нужен (например, в тестах со stub).
    """
    if config is None:
        config = load_config()

    provider_name = config.llm.provider

    if provider_name == "stub":
        from osa.llm.stub import StubProvider
        return StubProvider()

    if provider_name == "minimax":
        from osa.llm.minimax import MinimaxClient
        return MinimaxClient(config.llm)

    if provider_name == "openai_compat":
        from osa.llm.openai_compat import OpenAICompatClient
        return OpenAICompatClient(config.llm)

    raise ValueError(
        f"Unknown LLM provider: {provider_name!r}. "
        f"Expected: minimax, openai_compat, or stub."
    )
