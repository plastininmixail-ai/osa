# ROADMAP — O.S.A.

> Понедельный план до MVP (M1). Сроков жёстких нет, ориентир по объёму работы.

---

## Обзор фаз

| Фаза | Что делаем | Результат |
|------|-----------|-----------|
| **M0** — Каркас | Репо, структура, зависимости, hello-world с Minimax, БД-схема, CLI-скелет | Агент стартует, отвечает на одну цель «hello», пишет в БД и лог |
| **M1a** — Базовый runtime | ReAct loop, 5 инструментов, memory, грациозный shutdown | Агент решает простые задачи через think-act-observe |
| **M1b** — Goal Engine | Декомпозиция цели, планировщик, перепланирование, возобновление | Агент сам разбивает цель на подзадачи |
| **M1c** — Skills + Evolution | Skills library, рефлексия, версионирование промптов | Агент копит опыт и меняет поведение |
| **M1d** — Bench & Polish | Бенчмарк на 3 эталонных целях, полировка, документация | MVP готов, D1–D19 выполнены |

После M1 — пауза. Дальше либо M2 (bare-metal), либо улучшение M1, в зависимости от того, что покажет бенчмарк.

---

## M0 — Каркас (≈1 неделя)

**Цель**: заложить фундамент, чтобы не переписывать. К концу M0 `osa` запускается, отвечает на одну цель «hello» через Minimax, сохраняет всё в SQLite, имеет CLI.

### Задачи

- [ ] M0.1. Инициализировать репо
  - `git init`, `.gitignore` (Python, IDE, venv, `*.db`, `sandbox/`)
  - `pyproject.toml` с метаданными, зависимостями, конфигом для uv
  - `uv.lock` закоммичен
  - `README.md` с названием O.S.A., описанием, статусом «alpha / в разработке»
  - `LICENSE` (MIT)
  - `.github/workflows/ci.yml` — pytest на push
- [ ] M0.2. Структура `src/osa/`
  ```
  src/osa/
  ├── __init__.py
  ├── __main__.py         # python -m osa
  ├── cli.py              # typer app
  ├── config.py           # pydantic Settings, загрузка TOML
  ├── db.py               # SQLModel, миграции через Alembic или своё
  ├── llm/
  │   ├── __init__.py
  │   ├── base.py         # LLMProvider абстракция
  │   └── minimax.py      # Minimax-реализация
  ├── tools/
  │   ├── __init__.py
  │   └── base.py         # Tool абстракция
  ├── runtime/
  │   ├── __init__.py
  │   └── daemon.py       # главный цикл (пока stub)
  └── ...
  ```
- [ ] M0.3. Конфиг через TOML
  - `~/.config/osa/config.toml` (на Windows: `%APPDATA%/osa/config.toml`)
  - секции: `[llm]`, `[paths]`, `[limits]`, `[logging]`
- [ ] M0.4. SQLite-схема по PRD §8, миграция при первом запуске
- [ ] M0.5. CLI-скелет на `typer`
  - `osa init` — создать `$OSA_HOME`, инициализировать БД
  - `osa start` — запустить демон в фоне (subprocess + pid-файл)
  - `osa stop` — SIGTERM демону
  - `osa status` — прочитать статус из БД
  - `osa logs` — читать структурные логи
  - `osa goal "..."` — поставить цель (синхронно, ждёт первый ответ)
- [ ] M0.6. Hello-world агент
  - `osa goal "скажи привет"` → Minimax отвечает → запись в `episodes` и `goals` → печать ответа
- [ ] M0.7. Structlog: JSON-логи в `$OSA_HOME/logs/`
- [ ] M0.8. Smoke-тест: `pytest tests/test_hello.py` — мокаем Minimax, проверяем что ответ записался в БД
- [ ] M0.9. CI: GitHub Actions, зелёный билд

**Definition of Done M0**:
- ✅ `uv run osa init` создаёт БД и конфиг
- ✅ `uv run osa start` запускает демон
- ✅ `uv run osa goal "привет"` возвращает ответ от Minimax
- ✅ `uv run osa logs` показывает структурный лог
- ✅ `uv run osa stop` останавливает за ≤2с
- ✅ pytest зелёный, CI зелёный
- ✅ README + ARCHITECTURE.md (черновик)

---

## M1a — Базовый runtime (≈1–2 недели)

**Цель**: ReAct loop работает, инструменты выполняются, память сохраняется.

### Задачи

- [ ] M1a.1. ReAct loop
  - Класс `ReactLoop` с методами `think()`, `act()`, `observe()`
  - Промпт-шаблон для think-act-observe
  - Парсинг JSON-ответа модели (tool_call / final_answer)
- [ ] M1a.2. Tool abstraction
  - `Tool` абстрактный класс с `name`, `description`, `params_schema`, `run()`
  - Registry: `osa.tools.registry.register(Tool)`
- [ ] M1a.3. Базовые инструменты (5 штук)
  - `file_read`, `file_write`, `file_list` — работают только в `$OSA_HOME/sandbox/`
  - `shell` — выполнение команд в sandbox, с human-in-the-loop по умолчанию
  - `http_get` — простой HTTP GET с timeout
  - `web_search` — через какой-нибудь публичный API (DuckDuckGo HTML или Tavily, если есть ключ)
  - `time` / `date` — текущее время в ISO
- [ ] M1a.4. Human-in-the-loop
  - Перед опасными операциями (shell, file_write вне sandbox) — запрос подтверждения
  - В headless-режиме (для CI) — автоматический отказ
- [ ] M1a.5. Memory
  - `MemoryStore` с методами `add_fact()`, `get_recent()`, `search()`
  - Запись фактов в `memory_facts`
  - Чтение последних N фактов в контекст think-act-observe
- [ ] M1a.6. Episodes лог
  - Каждый шаг (think/act/observe) пишется в `episodes`
  - `osa logs` читает из episodes + structlog
- [ ] M1a.7. Graceful shutdown
  - Signal handler SIGTERM/SIGINT → сохранение состояния → exit
- [ ] M1a.8. Лимиты
  - `MAX_ITERATIONS`, `MAX_TOKENS`, `MAX_TIME` — конфигурируемые
  - При превышении — `GoalStatus.FAILED` с причиной
- [ ] M1a.9. Тесты
  - Unit: каждый инструмент с моками
  - Unit: парсинг JSON-ответов LLM
  - Integration: 2 простые цели («прочитай файл и ответь», «сделай HTTP GET и распарси»)

**Definition of Done M1a**:
- ✅ Агент решает цель «найди файл X и скажи его содержимое» автономно
- ✅ Агент решает цель «сделай GET на URL и найди в ответе слово Y»
- ✅ При попытке выполнить `rm -rf` агент спрашивает подтверждение
- ✅ При SIGTERM агент сохраняет состояние за ≤2с
- ✅ Покрытие тестами ≥60%

---

## M1b — Goal Engine (≈1–2 недели)

**Цель**: агент сам декомпозирует цель в план и перепланирует при сбоях.

### Задачи

- [ ] M1b.1. Планировщик
  - Принимает цель → возвращает `Plan` (дерево `Task`)
  - Использует LLM для декомпозиции (промпт «разбей цель на шаги»)
  - Валидация плана: циклы, зависимости, оценка ресурсов
- [ ] M1b.2. Task executor
  - Берёт следующую подзадачу → запускает ReAct loop → записывает результат
  - Если подзадача упала → пометить failed, попробовать альтернативу (если есть)
- [ ] M1b.3. Replanning
  - Если 3 попытки подряд провалились → вернуть планировщику с контекстом ошибок
  - Планировщик предлагает новый план или эскалирует пользователю
- [ ] M1b.4. Возобновление
  - При старте демона: найти `goals` со статусом `running` или `paused`
  - Продолжить с места остановки
  - Сохранять чекпоинт после каждой подзадачи
- [ ] M1b.5. CLI
  - `osa goal "..." --async` — не ждать ответа
  - `osa task list` — показать дерево подзадач
  - `osa goal pause <id>` / `osa goal resume <id>`
- [ ] M1b.6. Тесты
  - Планировщик: простая цель «установить X» → 3 шага
  - Replanning: цель с заведомо невозможным шагом → 3 retry → эскалация
  - Возобновление: kill демона на середине → перезапуск → продолжает

**Definition of Done M1b**:
- ✅ Цель «настрой проект в sandbox: создай pyproject.toml, напиши hello-world, запусти» декомпозируется на 3+ шага и выполняется
- ✅ Kill демона на середине → перезапуск → продолжает
- ✅ Цель с невозможным шагом → 3 retry → сообщение пользователю

---

## M1c — Skills + Evolution (≈1–2 недели)

**Цель**: агент копит опыт и меняет своё поведение.

### Задачи

- [ ] M1c.1. Skill creation
  - После успешной задачи: анализ эпизодов → если паттерн повторялся или был нетривиальным → предложить skill
  - Skill = `{name, description, params, steps, examples}`
- [ ] M1c.2. Skill retrieval
  - Перед новой задачей: поиск по embedding skill.description → если match > threshold → использовать
- [ ] M1c.3. Skill management
  - `osa skills list` — все skills с success/fail rate
  - `osa skills show <name>` — детали
  - `osa skills forget <name>` — удалить
  - `osa skills promote <name>` — сделать promoted (по умолчанию все experimental)
- [ ] M1c.4. Reflection
  - После каждой цели: промпт «проанализируй эпизоды, что сработало, что нет, что улучшить»
  - Результат → в `prompt_versions` как предложение изменения
- [ ] M1c.5. Prompt evolution
  - Текущий активный промпт → новая версия с изменением
  - Если метрика успешности упала → откат
  - Иначе → активация новой версии
  - Все версии хранятся, можно `osa evolution diff v3 v7`
- [ ] M1c.6. Embedding для поиска
  - Лёгкая модель (sentence-transformers/all-MiniLM-L6-v2) или вызов Minimax embedding API
  - Индексирование: skills, memory_facts, episodes
- [ ] M1c.7. Тесты
  - Skill reuse: решить похожую задачу дважды, проверить hit rate
  - Evolution: провернуть 10 фейковых задач, проверить что появились новые версии промпта

**Definition of Done M1c**:
- ✅ После 5+ задач в библиотеке есть ≥3 skills, из них ≥1 использован повторно
- ✅ Системный промпт имеет ≥3 версии в истории
- ✅ `osa evolution show` показывает историю изменений с метриками

---

## M1d — Bench & Polish (≈1 неделя)

**Цель**: доказать, что формула «маленькая модель + scaffolding > голая модель» работает.

### Задачи

- [ ] M1d.1. Эталонные цели (3 штуки, фиксированные)
  - **Цель 1**: «Создай в sandbox/ проект hello-world на Python с pyproject.toml, инициализируй git, сделай первый коммит, напиши pytest-тест, запусти его»
  - **Цель 2**: «Найди в интернете 3 публичных API погоды без ключа, выбери лучший, напиши скрипт который показывает погоду в Москве, сохрани вывод в sandbox/weather.txt»
  - **Цель 3**: «Прочитай README.md из sandbox/, найди все TODO/FIXME/XXX, составь markdown-таблицу в sandbox/todos.md с колонками: строка, тип, описание»
- [ ] M1d.2. Бенчмарк-раннер
  - Запускает цель N=3 раза, считает success rate, среднее время, среднее количество токенов
  - То же самое для голой Minimax (без scaffolding)
  - Выводит таблицу сравнения
- [ ] M1d.3. Полировка
  - Все CLI-команды с `--help` и `--verbose`
  - Все ошибки — понятные сообщения с предложением следующего шага
  - README с примерами реальных сессий
- [ ] M1d.4. ARCHITECTURE.md
  - Диаграмма компонентов (mermaid или asciidoc)
  - Описание каждого модуля
  - Поток данных: goal → plan → tasks → episodes → memory → skills → evolution
- [ ] M1d.5. Demo recording
  - Скринкаст или текстовый лог реальной сессии с эталонной целью (для README)

**Definition of Done M1d (= полный MVP)**:
- ✅ Все D1–D19 из PRD §9 выполнены
- ✅ Бенчмарк показывает: агент ≥2/3 целей, голая модель ≤1/3
- ✅ README содержит секцию «Demo» с реальным логом
- ✅ ARCHITECTURE.md описывает систему

---

## Сводный чеклист по MVP (M1)

Скопируй в свой трекер или вычёркивай прямо тут:

### M0 — Каркас
- [ ] Репо инициализировано
- [ ] Структура `src/osa/`
- [ ] Конфиг TOML
- [ ] SQLite-схема + миграции
- [ ] CLI-скелет (init, start, stop, status, logs, goal)
- [ ] Hello-world агент с Minimax
- [ ] Structlog
- [ ] Smoke-тест
- [ ] CI зелёный

### M1a — Базовый runtime
- [ ] ReAct loop
- [ ] Tool abstraction
- [ ] 5 базовых инструментов
- [ ] Human-in-the-loop
- [ ] Memory store
- [ ] Episodes лог
- [ ] Graceful shutdown
- [ ] Лимиты (итерации, токены, время)

### M1b — Goal Engine
- [ ] Планировщик
- [ ] Task executor
- [ ] Replanning
- [ ] Возобновление после рестарта
- [ ] CLI: async goal, pause/resume, task list

### M1c — Skills + Evolution
- [ ] Skill creation
- [ ] Skill retrieval
- [ ] Skill management CLI
- [ ] Reflection после задач
- [ ] Prompt versioning
- [ ] Embedding для поиска

### M1d — Bench & Polish
- [ ] 3 эталонные цели зафиксированы
- [ ] Бенчмарк-раннер
- [ ] CLI полировка
- [ ] README + ARCHITECTURE.md
- [ ] Demo в README

---

## Что после M1

Решения принимаются по результатам бенчмарка. Варианты:

- **Если MVP работает и формула подтвердилась** → M2: bare-metal install (минимальный Linux-образ с предустановленной OSA)
- **Если MVP работает, но есть узкие места** → M1.5: оптимизация конкретных компонентов
- **Если MVP не взлетел** → честный ретроспективный разбор, что не так, переделка

Mesh (слой 3) — отдельный разговор, не раньше чем слой 2 начнёт работать.

---

## Принципы планирования

1. **Каждый этап заканчивается работающим артефактом.** Не «почти готово», а «можно запустить и потыкать».
2. **Тесты пишутся параллельно с кодом**, не после. Pytest в CI с первого дня.
3. **Коммиты маленькие и осмысленные.** Один коммит = один логический шаг.
4. **Любая задержка > 2 недель на этапе = сигнал, что скоуп слишком широкий.** Резать.
5. **Никакого кода до утверждения этого ROADMAP.** Иначе будет переделка.
