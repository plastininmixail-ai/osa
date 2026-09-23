# O.S.A.

> **О**перационная **С**истема **А**гента. Goal-driven эволюционирующий агент.

**Статус**: в разработке, MVP (слой 1) в процессе.

## Что это

Маленькая LLM + сильный scaffolding-фреймворк = автономный агент, который решает задачи, с которыми сама модель без фреймворка не справляется.

Агент получает глобальную цель, сам декомпозирует её в подзадачи, решает всеми доступными инструментами, накапливает опыт и меняет своё поведение со временем.

## Документация

- [`docs/VISION.md`](docs/VISION.md) — манифест проекта
- [`docs/BRIEF.md`](docs/BRIEF.md) — заполненный бриф
- [`docs/PRD.md`](docs/PRD.md) — требования к MVP
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — понедельный план

## Стек

Python 3.11+ · SQLite · typer · pydantic · httpx · structlog · uv

## Быстрый старт (после M0)

```bash
git clone https://github.com/<user>/osa.git
cd osa
uv sync
uv run osa init
uv run osa start
uv run osa goal "создай в sandbox/ hello-world на Python"
```

## Лицензия

MIT
