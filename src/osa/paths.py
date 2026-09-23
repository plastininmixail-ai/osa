"""Пути к файлам OSA.

Использует platformdirs для кросс-платформенного определения стандартных
директорий пользователя. Переменные окружения (OSA_HOME, OSA_CONFIG_DIR,
OSA_LOG_DIR) перекрывают дефолты — полезно для тестов и dev-режима.
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir, user_log_dir

APP_NAME = "osa"
APP_AUTHOR = "osa-project"


def osa_home() -> Path:
    """Корневая директория OSA (БД, sandbox, по умолчанию и конфиг)."""
    base = os.environ.get("OSA_HOME")
    if base:
        return Path(base)
    return Path(user_data_dir(APP_NAME, APP_AUTHOR, roaming=False))


def config_dir() -> Path:
    """Директория конфигурации."""
    base = os.environ.get("OSA_CONFIG_DIR")
    if base:
        return Path(base)
    return Path(user_config_dir(APP_NAME, APP_AUTHOR, roaming=False))


def log_dir() -> Path:
    """Директория логов."""
    base = os.environ.get("OSA_LOG_DIR")
    if base:
        return Path(base)
    return Path(user_log_dir(APP_NAME, APP_AUTHOR))


def sandbox_dir() -> Path:
    """Sandbox — рабочая папка агента, куда он может писать файлы."""
    return osa_home() / "sandbox"


def db_path() -> Path:
    """Путь к SQLite базе данных."""
    return osa_home() / "osa.db"


def config_path() -> Path:
    """Путь к TOML-конфигу."""
    return config_dir() / "config.toml"
