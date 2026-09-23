"""Настройка структурного логирования через stdlib logging.

Файлы пишутся в JSON (для машинной обработки), в stderr — человекочитаемый
вывод с цветами. На M1a при необходимости переедем на structlog.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from osa.paths import log_dir

_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    """JSON-форматтер для лог-файлов.

    Каждая запись — одна строка JSON с фиксированным набором полей.
    Дополнительные поля через logger.info("...", extra={"key": "value"})
    попадают в корневой объект.
    """

    _RESERVED_KEYS = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "message",
        "taskName",
    })

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
        # extras
        for key, value in record.__dict__.items():
            if key not in self._RESERVED_KEYS and not key.startswith("_"):
                data[key] = value
        return json.dumps(data, ensure_ascii=False)


class _ConsoleFormatter(logging.Formatter):
    """Цветной вывод в stderr. Минимум зависимостей (только stdlib)."""

    COLORS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[35m",  # magenta
    }
    RESET = "\033[0m"
    DIM = "\033[2m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%H:%M:%S")
        msg = record.getMessage()

        extras_parts: list[str] = []
        for key, value in record.__dict__.items():
            if key in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            } or key.startswith("_"):
                continue
            extras_parts.append(f"{key}={value}")
        extras = (" " + " ".join(extras_parts)) if extras_parts else ""

        return (
            f"{color}[{record.levelname}]{self.RESET} "
            f"{self.DIM}{ts}{self.RESET} "
            f"{record.name}: "
            f"{msg}{extras}"
        )


def configure_logging(level: str = "info", json_logs: bool = True) -> None:
    """Настроить логирование (идемпотентно — повторный вызов игнорируется).

    Создаёт два handler:
    - FileHandler в $OSA_LOG_DIR/osa.jsonl (JSON)
    - StreamHandler в stderr (цветной текст)

    Уровень логирования берётся из аргумента или env OSA_LOGGING__LEVEL.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_path: Path = log_dir() / "osa.jsonl"
    log_dir().mkdir(parents=True, exist_ok=True)

    # Уровень из env или аргумента
    import os
    level_str = os.environ.get("OSA_LOGGING__LEVEL", level)
    level_int = getattr(logging, level_str.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level_int)
    # Очищаем handlers на случай повторной конфигурации в тестах
    root.handlers.clear()

    # File handler — JSON
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(_JsonFormatter())
    root.addHandler(file_handler)

    # Console handler — цветной
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(_ConsoleFormatter())
    root.addHandler(console_handler)

    _CONFIGURED = True


def reset_logging() -> None:
    """Сбросить флаг (для тестов). Не для прода."""
    global _CONFIGURED
    _CONFIGURED = False


def get_logger(name: str) -> logging.Logger:
    """Получить logger. configure_logging() должен быть вызван раньше."""
    return logging.getLogger(name)
