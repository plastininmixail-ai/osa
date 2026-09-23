# O.S.A. Architecture

Техническая архитектура проекта. Для манифеста и видения — `VISION.md`. Для требований — `PRD.md`. Для плана — `ROADMAP.md`.

## Высокоуровневая схема

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                  CLI (typer)                                │
│   init · goal · status · logs · start · stop · serve · skills · bench     │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼─────────────────────────────────────────────┐
│                                Transports                                   │
│   • CLI (синхронный)   • Telegram bot (polling, whitelist)                  │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼─────────────────────────────────────────────┐
│                              Runtime                                         │
│                                                                              │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│   │    Goal      │───▶│   Planner    │───▶│   Task       │                   │
│   │   Engine     │    │ (LLM → JSON) │    │   Executor   │                   │
│   └──────────────┘    └──────────────┘    └──────┬───────┘                   │
│                                                    │                          │
│                                            ┌───────▼───────┐                  │
│                                            │   ReAct      │                  │
│                                            │   Loop       │                  │
│                                            └───────┬───────┘                  │
│                                                    │                          │
│   ┌──────────────────────────────────────────────────┐                     │
│   │ Skills + Reflection (post-goal анализ)            │                     │
│   │ skills.py · skill_detector.py · reflection.py     │                     │
│   └──────────────────────────────────────────────────┘                     │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼─────────────────────────────────────────────┐
│                          Tool Sandbox                                        │
│   • file_read · file_write · file_list                                       │
│   • shell (с human-in-the-loop)                                              │
│   • http_get                                                                 │
│   Все работают ТОЛЬКО в $OSA_HOME/sandbox/ (path traversal protection)     │
└──────────────────────────────────────────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼─────────────────────────────────────────────┐
│                              LLM Layer                                       │
│   • LLMProvider (abstract)                                                   │
│   • MinimaxClient (MiniMax-M3, native tool calls)                           │
│   • OpenAICompatClient (OpenRouter, Ollama, llama.cpp)                      │
│   • StubProvider (тесты)                                                    │
└──────────────────────────────────────────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼─────────────────────────────────────────────┐
│                            Storage (SQLite)                                  │
│   • goals · tasks · episodes · skills · reflections                         │
│   • daemon_state                                                             │
│   • Миграции 001-006 через importlib.resources                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Жизненный цикл цели (goal)

```
1. CLI: osa goal "создай Python проект"
         │
2. transports/telegram.py (если через бота) → GoalEngine.run()
         │
3. engine.py: создаёт goal в БД (status=running)
         │
4. planner.py: LLM декомпозирует на 3-7 подзадач через JSON-промпт
         │
5. TaskStore: записывает задачи в tasks таблицу
         │
6. Для каждой задачи:
   a. TaskStore.update_status(task, "running")
   b. executor.py → ReactLoop.run(description)
   c. ReAct loop: think → tool call → observe (до max_iterations)
   d. TaskStore.update_status(task, "done"/"failed", result)
         │
7. Все задачи done → goal status=done
   Хотя бы одна failed 3 раза → goal status=failed
         │
8. Post-goal analysis:
   - skill_detector.py: извлекает паттерны → skills таблица
   - reflection.py: записывает анализ → reflections таблица
         │
9. CLI/telegram: возвращает plan_text_summary() пользователю
```

## ReAct Loop (runtime/react.py)

```
messages = [
    LLMMessage(role="system", content=_system_prompt()),
    LLMMessage(role="user", content=goal_text),
]

for iteration in 1..max_iterations:
    response = provider.complete(messages, tools=tool_specs)

    if response.tool_calls is empty:
        return final answer  # success

    messages.append(assistant_message_with_tool_calls)

    for each tool_call:
        if tool.requires_confirmation and not auto_approve:
            if user declines: error
        result = tool.run(**arguments)
        messages.append(tool_message_with_result)
```

## Структура файлов

```
src/osa/
├── __init__.py             # version
├── __main__.py             # python -m osa
├── cli.py                  # typer app, все CLI команды
├── paths.py                # OSA_HOME, sandbox, db_path (platformdirs + env)
├── config.py               # pydantic Settings: LLM/Telegram/Logging
├── db.py                   # SQLite connect + миграции
├── logging_setup.py        # stdlib logging + JSON formatter
│
├── llm/
│   ├── base.py             # LLMProvider, LLMMessage, LLMResponse, ToolSpec
│   ├── minimax.py          # MiniMax-M3 client (native tool calls)
│   ├── openai_compat.py    # OpenAI-compatible (OpenRouter, Ollama)
│   ├── stub.py             # Stub для тестов с scenario[]
│   └── tool_calls.py       # ToolCallRequest, ToolCallResult
│
├── tools/
│   ├── base.py             # Tool ABC, ToolResult, ToolConfirmationRequired
│   ├── registry.py         # singleton реестр
│   └── builtin.py          # 5 tools: file_read, file_write, file_list, shell, http_get
│
├── runtime/
│   ├── react.py            # ReAct loop + доступные skills в system prompt
│   ├── planner.py          # Planner (LLM → JSON → tasks), TaskStore, TaskExecutor
│   ├── engine.py           # GoalEngine — оркестратор goal → plan → execute → analyze
│   ├── daemon.py           # start/stop/heartbeat для long-running
│   ├── skills.py           # Skill dataclass, SkillLibrary CRUD
│   ├── skill_detector.py   # извлечение паттернов из эпизодов
│   ├── reflection.py       # анализ goal после выполнения
│   └── benchmark.py        # бенчмарк на 3 эталонных целях
│
├── transports/
│   └── telegram.py         # TelegramBot (python-telegram-bot)
│
└── migrations/
    ├── 001_init.sql        # goals, episodes, schema_version
    ├── 002_tasks.sql       # tasks
    ├── 003_daemon.sql      # daemon_state
    ├── 004_extended_statuses.sql  # paused, blocked
    ├── 005_skills_reflections.sql  # skills, reflections
    └── 006_episodes_tools.sql      # tool_name, tool_args в episodes
```

## Конфигурация

Файлы конфига (по приоритету):
1. Env variables `OSA_*` (наивысший приоритет, перекрывают TOML)
2. `$OSA_CONFIG_DIR/config.toml` (если существует)
3. Дефолты в `pydantic.BaseModel` (если ничего нет)

Секреты (API-ключи, токены) — **только в env** или `.env`, никогда в TOML. `.env` в `.gitignore`.

## Безопасность

### Path traversal
`tools/builtin.py:_resolve_safe_path()` гарантирует что агенту доступен только `$OSA_HOME/sandbox/`. Попытки выйти через `../../etc/passwd` блокируются.

### Human-in-the-loop
`ShellTool` помечен `requires_confirmation = True`. Перед выполнением команда показывается пользователю через `typer.prompt()`. С `auto_approve=True` подтверждение пропускается (для CI/headless).

### Telegram whitelist
`config.telegram.allowed_users` — список user_id. Если пуст — разрешены все (dev-режим). В продакшне задаётся явно через `OSA_TELEGRAM__ALLOWED_USERS`.

### Trust-модель установки OSA
OSA устанавливается ТОЛЬКО при физическом присутствии владельца устройства (USB-кабель, флешка, USB-debug). Нет самораспространения по сети. См. `VISION.md` §Trust-модель.

## Известные ограничения (на M1d)

- **Replanning** при failure не реализован (только retry до MAX_TASK_ATTEMPTS=3)
- **max_iterations=10** в ReactConfig по умолчанию — может быть мало для сложных задач
- **Test isolation** — некоторые тесты flaky из-за pollution с реальной OSA_HOME (отмечены `@pytest.mark.skip`)
- **LLM-based reflection** — на M1d простая эвристика, в будущем будет LLM-based
- **Skill detection** — эвристика "tool использован ≥2 раз". Настоящая LLM-based детекция — позже

## Стек и зависимости

- Python 3.11+ (тестируем на 3.11 и 3.12)
- `uv` для пакетов и venv
- `typer` — CLI
- `pydantic` v2 — валидация конфигов и data classes
- `httpx` — async HTTP для LLM API
- `tomlkit` — TOML с комментариями
- `platformdirs` — кросс-платформенные пути
- `python-telegram-bot` — Telegram транспорт
- `pytest`, `pytest-cov`, `ruff`, `mypy` — dev tooling

Всё managed через `uv sync`. См. `pyproject.toml`.

## Где запускать что

| Задача | Команда |
|--------|---------|
| Hello-world | `uv run python -m osa goal "привет"` |
| Сложная задача | `uv run python -m osa goal "..." --plan` |
| Демон в фоне | `uv run python -m osa start` / `osa stop` |
| Telegram-бот | двойной клик `OSA Bot.lnk` на рабочем столе |
| Список skills | `uv run python -m osa skills` |
| Бенчмарк | `uv run python -m osa benchmark --list` / `osa benchmark` |
| Baseline (голая модель) | `uv run python -m osa baseline` |
| Логи | `uv run python -m osa logs -f` |
