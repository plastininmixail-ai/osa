# Развёрнутый план M0 — O.S.A. Каркас проекта (v2, после рецензии)

> Скорректирован по итогам рецензии двух нейронок (23.09.2026). Изменения зафиксированы в `CHANGELOG.md`.

---

## 0. Контекст

**O.S.A. (Операционная Система Агента)** — goal-driven эволюционирующий агент. Маленькая LLM + сильный scaffolding = агент решает задачи, которые сама модель без фреймворка не решает. MVP = runtime на одной машине этого ноута.

**M0** = урезанный каркас. Цель: рабочая цепочка `CLI → LLM → SQLite → лог` за 2–3 дня. Hello-world через `osa goal "привет"`. Без демона, без лишних таблиц.

**Окружение**: Windows 11, MINGW64 bash, Python 3.11, uv 0.12.13, git, без Docker и GPU.

**Trust-модель (красная линия, для всех доков)**: установка OSA на устройства — только при физическом присутствии владельца. Не влияет на M0, но фиксируется.

---

## 1. Что изменилось после рецензии (v1 → v2)

| # | Было в v1 | Стало в v2 |
|---|-----------|------------|
| 1 | Демон: `osa start`/`stop` + PID + heartbeat | **Убрано**. `osa goal` синхронный. Демон → M1a. |
| 2 | 7 таблиц в БД сразу | **3 таблицы**: `goals`, `episodes`, `schema_version`. Остальное — миграциями позже. |
| 3 | Таблицы `skills`, `prompt_versions`, `memory_facts`, `tasks` в M0 | **Убрано**. Не фиксируем схему под непроверенную архитектуру. |
| 4 | Свой TOML-рендерер `_render_default_toml()` | **`tomlkit`** — зависимость, сохраняет комментарии. |
| 5 | `migrations/` рядом с `src/` | **`importlib.resources`**, миграции внутри пакета `osa.migrations`. |
| 6 | `structlog` в M0 | **Stdlib `logging` + JSON formatter**. Structlog → M1a. |
| 7 | LLM: Minimax + Stub | **Minimax + Stub + OpenAI-совместимый** (OpenRouter, Ollama, локальная 1B). |
| 8 | 4 LLM-команды + 2 daemon-команды | **4 команды**: `init`, `goal`, `status`, `logs`. Без демона. |

**Скоуп M0 сократился примерно на 30%** — убрано всё, что не нужно для проверки цепочки `CLI → LLM → SQLite → лог`.

---

## 2. Архитектурные решения, которые надо подтвердить/оптимизировать

### 2.1. Сырой `sqlite3` vs SQLModel

**Сырой `sqlite3`** (рекомендация):
- Зависимость = 0
- Для нашего масштаба (один writer, много readers) — проще и быстрее
- Прямой контроль над SQL

**SQLModel**:
- ORM с типизацией
- Удобнее для сложных запросов
- Но добавляет зависимость и кривую обучения

**Решение**: сырой `sqlite3` на M0. Если в M1b JOIN'ы станут невыносимы — мигрируем на SQLModel.

### 2.2. CLI-фреймворк: typer vs click vs argparse

**Решение**: `typer`. Типизация через аннотации, автогенерация `--help`, меньше кода.

### 2.3. Конфиг: TOML + tomlkit

**Решение**: TOML для конфига (через `tomllib` для чтения, `tomlkit` для записи), `.env` для секретов.

### 2.4. Структура `src/osa/`: плоская

**Решение**: плоская на старте, как в v1. Feature-based — когда файлов станет >30.

---

## 3. Детальные шаги M0

### Шаг M0.1 — Инициализация репо

**Что делаем**:
1. `cd C:\Users\mixai\Desktop\hermes-projects\agent-framework\`
2. `git init`
3. Создать `pyproject.toml`, `.gitignore`, `LICENSE` (MIT), `README.md`
4. Создать `.github/workflows/ci.yml`
5. `uv sync` для проверки зависимостей

**`pyproject.toml`**:
```toml
[project]
name = "osa"
version = "0.0.1"
description = "O.S.A. — Операционная Система Агента. Goal-driven эволюционирующий агент."
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
authors = [
    { name = "Михаил Пластинин" },
]
dependencies = [
    "typer>=0.12",
    "pydantic>=2.5",
    "httpx>=0.27",
    "tomlkit>=0.13",
    "platformdirs>=4.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.1",
    "ruff>=0.5",
    "mypy>=1.8",
]

[project.scripts]
osa = "osa.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/osa"]
include = ["src/osa/migrations/*.sql"]

[tool.hatch.version]
path = "src/osa/__init__.py"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --strict-markers --cov=osa --cov-report=term-missing"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_unused_ignores = true
```

**`.gitignore`**:
```
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.venv/
venv/
.env
.env.*
!.env.example
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.db
*.db-journal
*.db-wal
*.db-shm
sandbox/
logs/
*.log
.idea/
.vscode/
*.swp
.DS_Store
htmlcov/
.coverage
```

**`.env.example`** (для понимания, какие переменные можно задавать):
```
# API-ключ для LLM-провайдера
OSA_LLM__API_KEY=your-key-here

# Провайдер: minimax | openai_compat | stub
OSA_LLM__PROVIDER=minimax

# Endpoint и модель
OSA_LLM__BASE_URL=https://api.minimax.chat/v1
OSA_LLM__MODEL=MiniMax-M3

# Логи
OSA_LOGGING__LEVEL=info
OSA_LOGGING__JSON=true

# Тестовое окружение
OSA_HOME=/tmp/osa-test
```

**`LICENSE`** (MIT, полный текст) — стандартный шаблон.

**`.github/workflows/ci.yml`**:
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: "0.12"

      - name: Set up Python
        run: uv python install ${{ matrix.python-version }}

      - name: Install dependencies
        run: uv sync --all-extras --dev

      - name: Lint with ruff
        run: uv run ruff check src tests

      - name: Type check with mypy
        run: uv run mypy src

      - name: Run tests
        run: uv run pytest

  build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          version: "0.12"
      - run: uv python install 3.11
      - run: uv sync --all-extras
      - run: uv build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
```

**Критерий приёмки**:
- `git status` чистое дерево
- `uv sync` устанавливает все зависимости
- CI зелёный после пуша

---

### Шаг M0.2 — Структура `src/osa/` с минимальным кодом

**Файлы**:
```
src/osa/
├── __init__.py             # version
├── __main__.py             # entry point
├── cli.py                  # typer app
├── paths.py                # OSA_HOME и прочее
├── config.py               # pydantic + tomlkit
├── logging_setup.py        # stdlib logging + JSON
├── db.py                   # sqlite3 connect + migrate
├── llm/
│   ├── __init__.py
│   ├── base.py             # LLMProvider абстракция
│   ├── minimax.py          # MinimaxClient
│   ├── openai_compat.py    # OpenAICompatClient (OpenRouter, Ollama, etc)
│   └── stub.py             # StubProvider для тестов
└── migrations/
    └── 001_init.sql        # goals, episodes, schema_version
```

**`src/osa/__init__.py`**:
```python
"""O.S.A. — Операционная Система Агента."""

__version__ = "0.0.1"
```

**`src/osa/__main__.py`**:
```python
from osa.cli import app

if __name__ == "__main__":
    app()
```

**`src/osa/cli.py`** (4 команды):
```python
"""CLI интерфейс O.S.A."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from osa import __version__
from osa.logging_setup import configure_logging

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
        None, "--version", callback=_version_callback, is_eager=True
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
    """Поставить цель агенту (синхронно, ждёт ответ)."""
    from osa.config import load_config
    from osa.db import connect, get_provider_for_goal
    from osa.logging_setup import get_logger

    config = load_config()
    configure_logging(
        level=config.logging.level,
        json_logs=config.logging.json_logs,
    )
    log = get_logger(__name__)

    provider = get_provider_for_goal(config)

    log.info("goal_started", text=text, provider=config.llm.provider)

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
        log.error("goal_failed", error=str(e), exc_info=True)
        conn.execute(
            "UPDATE goals SET status='failed', error=?, updated_at=CURRENT_TIMESTAMP, "
            "finished_at=CURRENT_TIMESTAMP WHERE id=?",
            (str(e), goal_id),
        )
        conn.commit()
        conn.close()
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

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

    log.info("goal_done", goal_id=goal_id, tokens=response.tokens_used)
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
    follow: bool = typer.Option(False, "--follow", "-f"),
    level: str = typer.Option("info", "--level", "-l"),
    lines: int = typer.Option(50, "-n"),
) -> None:
    """Показать последние лог-записи."""
    import json

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
    import time
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
```

**`src/osa/paths.py`**:
```python
"""Пути к файлам OSA."""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir, user_log_dir

APP_NAME = "osa"
APP_AUTHOR = "osa-project"


def osa_home() -> Path:
    """Корневая директория OSA."""
    base = os.environ.get("OSA_HOME")
    if base:
        return Path(base)
    return Path(user_data_dir(APP_NAME, APP_AUTHOR, roaming=False))


def config_dir() -> Path:
    base = os.environ.get("OSA_CONFIG_DIR")
    if base:
        return Path(base)
    return Path(user_config_dir(APP_NAME, APP_AUTHOR, roaming=False))


def log_dir() -> Path:
    base = os.environ.get("OSA_LOG_DIR")
    if base:
        return Path(base)
    return Path(user_log_dir(APP_NAME, APP_AUTHOR))


def sandbox_dir() -> Path:
    return osa_home() / "sandbox"


def db_path() -> Path:
    return osa_home() / "osa.db"


def config_path() -> Path:
    return config_dir() / "config.toml"
```

**Критерий приёмки**: `uv run osa --help` показывает 4 команды, `uv run osa --version` показывает `0.0.1`.

---

### Шаг M0.3 — Конфиг через pydantic + tomlkit

**`src/osa/config.py`**:
```python
"""Конфигурация OSA."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import tomlkit
from pydantic import BaseModel, Field

from osa.paths import config_path


class LLMConfig(BaseModel):
    provider: Literal["minimax", "openai_compat", "stub"] = "minimax"
    api_key: str | None = None
    base_url: str = "https://api.minimax.io/v1"
    model: str = "MiniMax-M3"
    timeout: float = 30.0
    max_retries: int = 3


class LoggingConfig(BaseModel):
    level: Literal["debug", "info", "warning", "error"] = "info"
    json_logs: bool = True


class OSAConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(path: Path | None = None) -> OSAConfig:
    """Загрузить конфиг из TOML. Если файла нет — вернуть дефолт."""
    path = path or config_path()
    if not path.exists():
        return OSAConfig()
    data = tomlkit.loads(path.read_text(encoding="utf-8"))
    return OSAConfig(**data)


def save_default_config(path: Path) -> None:
    """Сохранить дефолтный конфиг в TOML с комментариями."""
    doc = tomlkit.document()
    doc.add(tomlkit.comment("O.S.A. configuration"))
    doc.add(tomlkit.comment("Документация: docs/CONFIG.md (будет в M1a)"))
    doc.add(tomlkit.nl())

    llm = tomlkit.table()
    llm.add("provider", "minimax")
    llm.add("model", "MiniMax-M3")
    llm.add("base_url", "https://api.minimax.chat/v1")
    llm.add("timeout", 30.0)
    llm.add("max_retries", 3)
    llm.add(tomlkit.comment("API-ключ через env: OSA_LLM__API_KEY"))
    doc.add("llm", llm)
    doc.add(tomlkit.nl())

    logging = tomlkit.table()
    logging.add("level", "info")
    logging.add("json_logs", True)
    doc.add("logging", logging)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
```

**Критерий приёмки**:
- `osa init` создаёт `config.toml` с комментариями
- `load_config()` парсит TOML → pydantic-объект
- Изменение значения в TOML применяется после следующего запуска CLI

---

### Шаг M0.4 — SQLite с 3 таблицами и миграциями

**Структура миграций через `importlib.resources`**:
```
src/osa/
└── migrations/
    ├── __init__.py        # пустой, делает migrations пакетом
    └── 001_init.sql       # goals, episodes, schema_version
```

**`src/osa/migrations/__init__.py`**:
```python
"""SQL-миграции для БД OSA."""

from importlib.resources import files

from osa.migrations import data as _data

MIGRATIONS_DIR = files(_data) if hasattr(_data, "__file__") else None
```

Замечание: с Python 3.12 `importlib.resources.files()` отлично работает. С Python 3.11 для подкаталогов нужно использовать `importlib_resources` (бэкпорт) или положить файлы в `osa.migrations.data`.

**Альтернатива (надёжнее для 3.11)**: использовать `importlib.resources` как Traversable:
```python
from importlib.abc import Traversable
from importlib.resources import files

def get_migrations_dir() -> Traversable:
    """Путь к директории с миграциями внутри пакета."""
    return files("osa.migrations")
```

**`src/osa/migrations/001_init.sql`**:
```sql
-- Goals
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'planning', 'running', 'done', 'failed')),
    result TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
CREATE INDEX IF NOT EXISTS idx_goals_created ON goals(created_at);

-- Episodes
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL REFERENCES goals(id),
    step_type TEXT NOT NULL CHECK (step_type IN ('think', 'act', 'observe', 'reflect')),
    content TEXT NOT NULL,
    tokens_used INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_episodes_goal ON episodes(goal_id);
CREATE INDEX IF NOT EXISTS idx_episodes_created ON episodes(created_at);

-- Schema version
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**`src/osa/db.py`**:
```python
"""SQLite подключение и миграции."""

from __future__ import annotations

import sqlite3
from importlib.resources import files
from pathlib import Path

from osa.config import OSAConfig, load_config
from osa.llm.base import LLMProvider
from osa.llm.minimax import MinimaxClient
from osa.llm.openai_compat import OpenAICompatClient
from osa.llm.stub import StubProvider
from osa.paths import db_path, osa_home


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Подключиться к БД."""
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
    # На dev-режиме (без wheel) это реальный путь
    return Path(str(traversable))


def migrate(conn: sqlite3.Connection) -> None:
    """Применить все миграции, которых ещё нет."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    current = conn.execute(
        "SELECT COALESCE(MAX(version), 0) FROM schema_version"
    ).fetchone()[0]

    migrations_path = _migrations_dir()
    # Берём только SQL-файлы
    sql_files = sorted(p for p in migrations_path.iterdir() if p.suffix == ".sql")

    for sql_file in sql_files:
        version = int(sql_file.stem.split("_")[0])
        if version > current:
            sql = sql_file.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (version,)
            )
            conn.commit()


def init_db() -> None:
    """Инициализировать БД (применить все миграции)."""
    conn = connect()
    try:
        migrate(conn)
    finally:
        conn.close()


def get_provider_for_goal(config: OSAConfig | None = None) -> LLMProvider:
    """Фабрика LLM-провайдера по конфигу."""
    if config is None:
        config = load_config()

    provider_name = config.llm.provider

    if provider_name == "stub":
        return StubProvider()
    if provider_name == "minimax":
        return MinimaxClient(config.llm)
    if provider_name == "openai_compat":
        return OpenAICompatClient(config.llm)

    raise ValueError(f"Unknown LLM provider: {provider_name}")
```

**Критерий приёмки**:
- `osa init` создаёт `osa.db` с 3 таблицами
- `SELECT MAX(version) FROM schema_version` возвращает `1`
- `OSA_LLM__PROVIDER=stub uv run osa goal "test"` работает

---

### Шаг M0.5 — LLM-абстракция с 3 провайдерами

**`src/osa/llm/base.py`**:
```python
"""Абстракция LLM-провайдера."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str
    name: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    content: str
    tokens_used: int
    model: str
    reasoning: str | None = None  # thinking-содержимое (Minimax M3 и подобные)
    raw: dict | None = None


class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Сделать один вызов LLM."""


def resolve_api_key(config_value: str | None) -> str:
    """Получить API-ключ: сначала config, потом env (pydantic-style или обычный)."""
    import os
    return (
        config_value
        or os.environ.get("OSA_LLM__API_KEY")
        or os.environ.get("OSA_LLM_API_KEY")
        or ""
    )
```

**`src/osa/llm/stub.py`** (для тестов):
```python
"""Stub LLM-провайдер для тестов."""

from osa.llm.base import LLMMessage, LLMProvider, LLMResponse


class StubProvider(LLMProvider):
    """Возвращает детерминированный ответ."""

    def __init__(self, response_text: str = "Привет от stub!", tokens: int = 10):
        self.response_text = response_text
        self.tokens = tokens
        self.call_count = 0
        self.last_messages: list[LLMMessage] = []

    def complete(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        self.call_count += 1
        self.last_messages = list(messages)
        return LLMResponse(
            content=self.response_text,
            tokens_used=self.tokens,
            model="stub-1",
        )
```

**`src/osa/llm/openai_compat.py`** (для OpenRouter, Ollama, локальной 1B):
```python
"""OpenAI-совместимый клиент для OpenRouter, Ollama, llama.cpp server, etc."""

from __future__ import annotations

from dataclasses import asdict

import httpx

from osa.config import LLMConfig
from osa.llm.base import LLMMessage, LLMProvider, LLMResponse, resolve_api_key


class OpenAICompatClient(LLMProvider):
    def __init__(self, config: LLMConfig):
        self.config = config
        self.api_key = resolve_api_key(config.api_key)

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.config.model,
            "messages": [asdict(m) for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        with httpx.Client(timeout=self.config.timeout) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})

        return LLMResponse(
            content=choice["message"]["content"],
            tokens_used=usage.get("total_tokens", 0),
            model=data.get("model", self.config.model),
            raw=data,
        )
```

**`src/osa/llm/minimax.py`** (наследник OpenAICompat — специфика только в endpoint/auth если есть):
```python
"""Minimax клиент. OpenAI-совместимый API + специфика M3 (thinking)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import httpx

from osa.config import LLMConfig
from osa.llm.base import LLMMessage, LLMProvider, LLMResponse, resolve_api_key


# Актуальный base_url: https://api.minimax.io/v1 (по официальной документации)
# Альтернативный Anthropic-compatible: https://api.minimax.io/anthropic
# На M0 используем OpenAI-compatible (минимум зависимостей, совместимо с любой
# OpenAI-style библиотекой).
DEFAULT_BASE_URL = "https://api.minimax.io/v1"
DEFAULT_MODEL = "MiniMax-M3"


class MinimaxClient(LLMProvider):
    """Клиент для MiniMax API (MiniMax-M3 и других моделей).

    Использует OpenAI-совместимый формат chat completions.
    Поддерживает thinking-параметр (специфика M3) — reasoning_content
    возвращается в отдельном поле ответа.
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        self.api_key = resolve_api_key(config.api_key)
        if not self.api_key:
            raise ValueError(
                "Minimax API key not found. Set OSA_LLM__API_KEY env var."
            )

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [asdict(m) for m in messages],
            "max_tokens": max_tokens,
            # По умолчанию НЕ включаем thinking, чтобы hello-world был быстрым.
            # В M1a добавим управление через конфиг.
            # "thinking": {"type": "enabled"},
        }
        if temperature is not None:
            payload["temperature"] = temperature

        with httpx.Client(timeout=self.config.timeout) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        message = choice["message"]
        usage = data.get("usage", {})

        # MiniMax M3 может вернуть reasoning_content (thinking)
        # Сохраняем в raw, в content кладём основной ответ
        reasoning = message.get("reasoning_content") or message.get("reasoning")

        return LLMResponse(
            content=message.get("content", "") or "",
            tokens_used=usage.get("total_tokens", 0),
            model=data.get("model", self.config.model),
            raw=data,
            reasoning=reasoning,  # type: ignore[arg-type]
        )
```

## Ключевые правки v3

1. **`base_url` исправлен**: `https://api.minimax.io/v1` (по официальной документации)
2. **Thinking-парсинг в M0**: `LLMResponse` получил поле `reasoning: str | None` — `MinimaxClient` извлекает `reasoning_content` из ответа M3
3. **Thinking выключен по умолчанию** (`hello-world` без него быстрее), управление через конфиг в M1a
4. **`MinimaxClient` больше не наследник `OpenAICompatClient`** — у Minimax свои нюансы (thinking), наследование создаёт ложное впечатление взаимозаменяемости
```

**Критерий приёмки**:
- `OSA_LLM__PROVIDER=stub uv run osa goal "test"` → ответ stub, записан в БД
- С реальным MiniMax ключом: `uv run osa goal "test"` → ответ от Minimax
- С OpenAI-совместимым эндпоинтом: меняем `base_url` + `provider=openai_compat`

---

### Шаг M0.6 — Stdlib logging + JSON

**`src/osa/logging_setup.py`**:
```python
"""Настройка структурного логирования через stdlib logging."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from osa.paths import log_dir

_CONFIGURED = False


class JSONFormatter(logging.Formatter):
    """Простой JSON-форматтер для stdlib logging."""

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        # Дополнительные поля через extra={"key": "value"}
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            }:
                data[key] = value
        return json.dumps(data, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Цветной вывод в stderr через ANSI-коды (минимум зависимостей)."""

    COLORS = {
        "DEBUG": "\033[36m",    # cyan
        "INFO": "\033[32m",     # green
        "WARNING": "\033[33m",  # yellow
        "ERROR": "\033[31m",    # red
        "CRITICAL": "\033[35m", # magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%H:%M:%S")
        msg = record.getMessage()
        extras = ""
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            }:
                extras += f" {key}={value}"
        return f"{color}[{record.levelname}]{self.RESET} {ts} {record.name}: {msg}{extras}"


def configure_logging(level: str = "info", json_logs: bool = True) -> None:
    """Настроить логирование (один раз за процесс)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_path: Path = log_dir() / "osa.jsonl"
    log_dir().mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()

    # File handler — JSON
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(JSONFormatter())
    root.addHandler(file_handler)

    # Console handler — цветной
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(ConsoleFormatter())
    root.addHandler(console_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
```

**Критерий приёмки**:
- После `osa goal "test"` в `$OSA_HOME/logs/osa.jsonl` есть JSON-записи
- В stderr — цветной вывод `[INFO] HH:MM:SS osa.cli: goal_done goal_id=1 tokens=15`
- `osa logs -f` следит за файлом

---

### Шаг M0.7 — Тесты

**Структура тестов**:
```
tests/
├── __init__.py
├── conftest.py
├── test_paths.py
├── test_config.py
├── test_db.py
├── test_llm_stub.py
├── test_llm_openai_compat.py
└── test_cli.py
```

**`tests/conftest.py`**:
```python
"""Общие фикстуры для тестов."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_osa_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Изолированный OSA_HOME в tmp_path."""
    home = tmp_path / "osa_home"
    config_dir = tmp_path / "osa_config"
    log_dir = tmp_path / "osa_logs"
    home.mkdir()
    config_dir.mkdir()
    log_dir.mkdir()

    monkeypatch.setenv("OSA_HOME", str(home))
    monkeypatch.setenv("OSA_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("OSA_LOG_DIR", str(log_dir))
    monkeypatch.setenv("OSA_LLM__PROVIDER", "stub")
    monkeypatch.setenv("OSA_LLM__API_KEY", "test-key")

    return home


@pytest.fixture
def initialized_db(tmp_osa_home: Path) -> Path:
    """БД с применёнными миграциями."""
    from osa.db import init_db
    init_db()
    return tmp_osa_home / "osa.db"


@pytest.fixture
def stub_provider():
    """Stub-провайдер с предсказуемым ответом."""
    from osa.llm.stub import StubProvider
    return StubProvider(response_text="Test response", tokens=42)
```

**`tests/test_cli.py`** (главный интеграционный тест):
```python
"""Интеграционные тесты CLI."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from osa.cli import app


def test_help_shows_all_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "goal" in result.stdout
    assert "status" in result.stdout
    assert "logs" in result.stdout


def test_init_creates_osa_home(tmp_osa_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert tmp_osa_home.exists()
    assert (tmp_osa_home / "osa.db").exists()
    assert (tmp_osa_home / "sandbox").exists()


def test_goal_with_stub(tmp_osa_home: Path, initialized_db) -> None:
    """osa goal возвращает ответ stub и пишет в БД."""
    runner = CliRunner()
    result = runner.invoke(app, ["goal", "привет"])
    assert result.exit_code == 0
    assert "Test response" in result.stdout

    # Проверить БД напрямую
    from osa.db import connect
    conn = connect()
    goals = conn.execute("SELECT * FROM goals").fetchall()
    assert len(goals) == 1
    assert goals[0]["description"] == "привет"
    assert goals[0]["status"] == "done"
    assert goals[0]["result"] == "Test response"

    episodes = conn.execute("SELECT * FROM episodes").fetchall()
    assert len(episodes) == 1
    assert episodes[0]["content"] == "Test response"
    assert episodes[0]["tokens_used"] == 42


def test_status_shows_goals(tmp_osa_home: Path, initialized_db) -> None:
    """osa status показывает поставленные цели."""
    runner = CliRunner()
    runner.invoke(app, ["goal", "первая цель"])
    runner.invoke(app, ["goal", "вторая цель"])

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "первая цель" in result.stdout
    assert "вторая цель" in result.stdout
```

**`tests/test_config.py`**:
```python
"""Тесты конфига."""

from __future__ import annotations

from pathlib import Path

import tomlkit

from osa.config import OSAConfig, load_config, save_default_config


def test_load_returns_defaults_when_no_file(tmp_path: Path) -> None:
    config = load_config(tmp_path / "nonexistent.toml")
    assert isinstance(config, OSAConfig)
    assert config.llm.provider == "minimax"
    assert config.logging.level == "info"


def test_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    save_default_config(path)
    assert path.exists()

    # Проверить, что комментарии сохранились
    text = path.read_text(encoding="utf-8")
    assert "O.S.A." in text

    # Загрузить обратно
    config = load_config(path)
    assert config.llm.provider == "minimax"


def test_environment_override(tmp_path: Path, monkeypatch) -> None:
    """Переменные окружения перекрывают конфиг."""
    monkeypatch.setenv("OSA_LLM__PROVIDER", "stub")
    config = load_config(tmp_path / "nonexistent.toml")
    # OSAConfig загружается из env автоматически через pydantic-settings? Нет.
    # Для override нужно вручную или через pydantic-settings.
    # На M0 это известное ограничение, в M1a добавим pydantic-settings.
    pass  # placeholder
```

**`tests/test_db.py`**:
```python
"""Тесты БД."""

from __future__ import annotations

from osa.db import connect, init_db


def test_init_db_creates_tables(tmp_osa_home) -> None:
    init_db()
    conn = connect()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = {row["name"] for row in tables}

    assert "goals" in table_names
    assert "episodes" in table_names
    assert "schema_version" in table_names

    version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert version == 1


def test_init_db_is_idempotent(tmp_osa_home) -> None:
    """Повторный init не падает."""
    init_db()
    init_db()
    conn = connect()
    versions = conn.execute("SELECT version FROM schema_version").fetchall()
    assert len(versions) == 1


def test_episode_links_to_goal(tmp_osa_home, initialized_db) -> None:
    """FK между episode и goal работает."""
    conn = connect()
    cur = conn.execute("INSERT INTO goals (description, status) VALUES (?, 'done')", ("test",))
    goal_id = cur.lastrowid
    conn.execute(
        "INSERT INTO episodes (goal_id, step_type, content) VALUES (?, 'observe', 'hello')",
        (goal_id,),
    )
    conn.commit()

    episodes = conn.execute("SELECT * FROM episodes WHERE goal_id = ?", (goal_id,)).fetchall()
    assert len(episodes) == 1
    assert episodes[0]["content"] == "hello"
```

**Критерий приёмки**:
- `uv run pytest` — все тесты зелёные
- `uv run pytest --cov=osa --cov-report=term-missing` — coverage ≥70% ядра
- Coverage для `cli.py` и `db.py` обязательно ≥80%

---

## 4. Definition of Done M0

```
M0.1 — Репо
  ☐ git init, .gitignore, pyproject.toml, LICENSE, README.md, .env.example
  ☐ uv sync работает
  ☐ CI файл создан

M0.2 — Структура и CLI-скелет
  ☐ Все файлы из схемы существуют
  ☐ uv run osa --help показывает 4 команды
  ☐ uv run osa --version показывает 0.0.1

M0.3 — Конфиг TOML
  ☐ osa init создаёт config.toml с комментариями
  ☐ load_config() парсит TOML → pydantic

M0.4 — SQLite с 3 таблицами
  ☐ osa init создаёт osa.db
  ☐ В БД таблицы: goals, episodes, schema_version
  ☐ schema_version содержит 1
  ☐ Повторный init не падает (миграции идемпотентны)

M0.5 — LLM-провайдеры
  ☐ StubProvider работает (тест проходит)
  ☐ OpenAICompatClient работает (тест с respx/httpx_mock проходит)
  ☐ MinimaxClient = алиас OpenAICompatClient
  ☐ get_provider_for_goal() фабрика работает

M0.6 — Stdlib logging + JSON
  ☐ После osa goal в логе JSON-запись
  ☐ В stderr цветной вывод
  ☐ osa logs -f следит за файлом

M0.7 — Тесты
  ☐ pytest зелёный
  ☐ Coverage ≥70% ядра
  ☐ Тест test_goal_with_stub проходит
  ☐ Тест test_init_db_creates_tables проходит

CI
  ☐ GitHub Actions зелёный
```

**Когда всё выше ✅** — M0 готов, переходим к M1a (демон + ReAct loop + инструменты).

---

## 5. Известные риски M0

| Риск | Митигация |
|------|-----------|
| **API-ключ ещё не прислан** | Михаил пришлёт ключ после старта. До этого — тесты на stub. |
| `importlib.resources` на 3.11 vs 3.12 | Использовать `importlib.resources.files()` (доступно с 3.9, traversable-интерфейс с 3.12). На 3.11 может потребоваться `importlib_resources` как fallback. Тестировать на обоих Python. |
| Pydantic `BaseModel` не подхватывает env автоматически | На M0 — ручной `os.getenv` в `resolve_api_key()`. В M1a добавим `pydantic-settings`. |
| Wheel не включает SQL-файлы | В `pyproject.toml` указан `include = ["src/osa/migrations/*.sql"]`. Проверить через `python -m build` и `unzip -l dist/*.whl`. |
| `.env` случайно закоммитили | `.gitignore` исключает `.env`, `.env.example` остаётся как шаблон. |
| **Thinking-параметр M3 замедляет ответ** | На M0 по умолчанию НЕ включаем. Управление через конфиг в M1a. |

### Закрытые вопросы (зафиксировано 23.09.2026)

- ✅ **Endpoint**: `https://api.minimax.io/v1` (по официальной документации). Альтернативы: Anthropic-compatible `/anthropic`, China-region `api.minimaxi.com`.
- ✅ **API-ключ**: Михаил пришлёт отдельно.
- ✅ **Pydantic-settings**: в M1a (на M0 хватит `resolve_api_key()`).
- ✅ **Минимальная версия Python**: 3.11. CI тестирует 3.11 и 3.12.
- ✅ **Префикс env-переменных**: `OSA_*`.
- ✅ **Thinking парсинг**: `LLMResponse.reasoning`, по умолчанию выключен.

---

## 6. Что после M0

**M1a — Базовый runtime** (после M0):
- Демон: `osa start`/`stop` + PID + heartbeat + SIGTERM
- ReAct loop с парсингом tool-calls
- 5 базовых инструментов (file, shell, http, web_search, time)
- Structlog вместо stdlib logging
- Миграция 002: таблицы `tasks`, расширение `memory_facts`
- Human-in-the-loop для опасных команд

**M1b — Goal Engine**:
- Plan-and-Execute: декомпозиция цели в дерево подзадач
- Replanning при сбоях
- Возобновление после рестарта
- Миграция 003: расширение `tasks` (parent_id, retries)

**M1c — Skills + Evolution**:
- Skills library
- Reflection после задач
- Версионирование промптов
- Embedding для семантического поиска

**M1d — Bench & Polish**:
- 3 эталонные цели
- Бенчмарк агент vs голая модель
- Документация (CONFIG.md, ARCHITECTURE.md)
- Demo recording

Подробности — в `docs/ROADMAP.md`.

---

## 7. Что нужно для старта разработки

**Готово**:
- ✅ Endpoint Minimax определён (`https://api.minimax.io/v1`)
- ✅ Все архитектурные вопросы закрыты
- ✅ План прошёл двойную рецензию
- ✅ Trust-модель зафиксирована
- ✅ Стек и зависимости определены

**Ждём от Михаила**:
- API-ключ MiniMax (пришлёт отдельно)
- Команду «стартуем M0»

Когда оба пункта есть — начинаем реализацию по шагам M0.1–M0.7.

