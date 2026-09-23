# O.S.A.

> **О**перационная **С**истема **А**гента. Goal-driven эволюционирующий агент.

**Статус**: MVP (слой 1) готов — каркас + ReAct loop + Goal Engine + Telegram-бот. Bare-metal и mesh — следующие слои.

## Что это

Маленькая LLM + сильный scaffolding-фреймворк = автономный агент, который решает задачи, с которыми сама модель без фреймворка не справляется.

Агент получает глобальную цель, сам декомпозирует её в подзадачи, решает всеми доступными инструментами, накапливает опыт и меняет своё поведение со временем.

В перспективе — bare-metal install на любое устройство (смартфон с разбитым экраном, старый ноут, Raspberry Pi) и mesh из таких устройств, объединённых проводом.

## Документация

- [`docs/VISION.md`](docs/VISION.md) — манифест проекта
- [`docs/PRD.md`](docs/PRD.md) — требования к MVP
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — понедельный план
- [`docs/CHANGELOG.md`](docs/CHANGELOG.md) — история решений

## Стек

Python 3.11+ · SQLite · typer · pydantic · httpx · tomlkit · structlog · python-telegram-bot · uv

## Быстрый старт

```bash
git clone https://github.com/plastininmixail-ai/osa.git
cd osa
uv sync
uv run python -m osa init
uv run python -m osa goal "прочитай note.txt в sandbox и перескажи"
```

## Telegram-бот

```bash
# 1. Создай бота через @BotFather, получи токен
# 2. Узнай свой user_id через @userinfobot
# 3. Заполни в .env:
OSA_TELEGRAM__BOT_TOKEN=123:ABC...
OSA_TELEGRAM__ALLOWED_USERS=123456789

# 4. Запусти:
uv run python -m osa serve --transport=telegram
```

В Telegram напиши боту `/start` или просто любую задачу.

## Команды

```
osa init          # инициализировать OSA_HOME (БД, конфиг, sandbox)
osa goal "..."    # поставить цель агенту (синхронно, с декомпозицией)
osa status        # показать daemon + последние цели
osa logs [-f]     # показать логи (с -f follow)
osa start         # запустить демон в фоне
osa stop          # остановить демон
osa serve         # запустить внешний сервер (telegram)
```

## Лицензия

MIT
