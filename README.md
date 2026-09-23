# O.S.A.

> **О**перационная **С**истема **А**гента. Goal-driven эволюционирующий агент.

**Статус**: MVP слоя 1 готов. Бенчмарк (M1d) — в процессе.

## Что это

Маленькая LLM + сильный scaffolding-фреймворк = автономный агент, который решает задачи, с которыми сама модель без фреймворка не справляется.

Агент получает глобальную цель, сам декомпозирует её в подзадачи, решает всеми доступными инструментами (файлы, shell, HTTP), накапливает опыт в виде skills и reflection, и доступен через CLI или Telegram-бот.

В перспективе — bare-metal install на любое устройство (смартфон с разбитым экраном, старый ноут, Raspberry Pi) и mesh из таких устройств, объединённых проводом.

## Документация

- [`docs/VISION.md`](docs/VISION.md) — манифест, формула "маленькая LLM + scaffolding"
- [`docs/PRD.md`](docs/PRD.md) — требования к MVP, критерии приёмки
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — понедельный план M0-M3
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — техническая архитектура, диаграммы
- [`docs/CHANGELOG.md`](docs/CHANGELOG.md) — история решений

## Стек

Python 3.11+ · SQLite · typer · pydantic · httpx · tomlkit · python-telegram-bot · uv

## Быстрый старт

```bash
git clone https://github.com/plastininmixail-ai/osa.git
cd osa
uv sync
uv run python -m osa init
uv run python -m osa goal "прочитай note.txt в sandbox и перескажи"
```

## Demo

Реальная сессия с агентом, решающим сложную задачу через Goal Engine + ReAct loop + tools:

```
$ uv run python -m osa goal "В sandbox создай Python-проект hello-world: pyproject.toml, main.py с функцией main(), README.md, запусти тесты"

Цель: В sandbox создай Python-проект hello-world...

План:
  · 1. Создать директорию проекта sandbox/hello и перейти в неё
  ✓ 2. Создать файл pyproject.toml с описанием проекта hello и зависимостью pytest
  ✓ 3. Создать файл hello.py с функцией main(), возвращающей f"Hello, World!"
  ✓ 4. Создать файл test_hello.py с тремя тестами для функции main()
  ✗ 5. Установить pytest (pip install pytest) и запустить pytest

Статус: failed
Провалена задача: Установить pytest и запустить pytest
Причина: Reached max iterations
```

**Логи** (`$OSA_HOME/Logs/osa.jsonl`):
```json
{"timestamp": "...", "logger": "osa.planner", "message": "plan_created", "goal": "...", "tasks_count": 5}
{"timestamp": "...", "logger": "osa.engine", "message": "engine_task_done", "task_id": 4, "tokens": 2988}
{"timestamp": "...", "logger": "osa.react", "message": "react_iteration", "iteration": 2, "messages": 4}
{"timestamp": "...", "logger": "osa.react", "message": "react_final", "iteration": 2, "tokens": 2570}
{"timestamp": "...", "logger": "osa.cli", "message": "goal_done", "goal_id": 1, "iterations": 2, "tokens": 2570}
```

## Telegram-бот

```bash
# 1. Создай бота через @BotFather, получи токен
# 2. Узнай свой user_id через @userinfobot
# 3. Заполни в .env:
OSA_TELEGRAM__BOT_TOKEN=123:ABC...
OSA_TELEGRAM__ALLOWED_USERS=123456789

# 4. Двойной клик OSA Bot.lnk на рабочем столе
# Или из терминала:
uv run python -m osa serve --transport=telegram
```

В Telegram напиши боту `/start` или просто любую задачу.

## Команды

```
osa init              # инициализировать OSA_HOME
osa goal "..."        # поставить цель агенту (с декомпозицией через --plan)
osa status            # показать daemon + последние цели
osa logs [-f]         # показать логи (с -f follow)
osa start             # запустить демон в фоне
osa stop              # остановить демон
osa serve             # запустить внешний сервер (Telegram)
osa skills            # показать извлечённые навыки
osa reflections       # показать reflection (анализ прошлых задач)
osa benchmark         # запустить бенчмарк на 3 эталонных целях
osa baseline          # голая модель без scaffolding (для сравнения)
```

## Бенчмарк (формула)

Три эталонные цели из `PRD.md §9` тестируются через `osa benchmark`. Для сравнения есть `osa baseline` (голая модель без инструментов и планирования).

```bash
$ uv run python -m osa benchmark --list

📊 Эталонные цели для бенчмарка:

• create_pyproject
  Создай в sandbox/ Python-проект hello-world: pyproject.toml с name='hello-world'...
  Expected: pyproject.toml, main.py, README.md

• weather_api
  Найди в интернете 5 публичных API погоды, выбери самый простой без ключа...
  Expected: weather.py

• find_todos
  Прочитай README.md из sandbox/, найди в нём все TODO/FIXME, составь таблицу...
  Expected: todos.md

$ uv run python -m osa benchmark

🏃 Запускаю бенчмарк: 3 целей × 1 попыток
Провайдер: minimax

# OSA Benchmark Report
Provider: MinimaxClient, Model: MiniMax-M3
Time: 2026-09-23T15:00:00

Goal                       Success     AvgTime    AvgTokens
------------------------------------------------------------
create_pyproject            67% (3)     45.2s        12500
weather_api                 100% (1)    18.7s         4200
find_todos                  100% (1)    22.1s         3800

Total: 5/5 goals done (100%)
```

## Trust-модель

OSA устанавливается **только при физическом присутствии владельца** устройства. USB-кабель, флешка, USB-debug на Android, ISO на SD-карте. Никакого самораспространения по сети, никакой скрытой установки. Это не вирус, это утилита для переиспользования старого железа.

## Лицензия

MIT
