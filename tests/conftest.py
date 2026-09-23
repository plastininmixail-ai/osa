"""Общие фикстуры для тестов OSA.

Главная фикстура — `tmp_osa_home`, которая перенаправляет OSA_HOME,
OSA_CONFIG_DIR и OSA_LOG_DIR в tmp_path и подменяет LLM-провайдера на stub.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def tmp_osa_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Изолированный OSA_HOME в tmp_path."""
    home = tmp_path / "osa_home"
    cfg = tmp_path / "osa_config"
    logs = tmp_path / "osa_logs"
    home.mkdir()
    cfg.mkdir()
    logs.mkdir()

    monkeypatch.setenv("OSA_HOME", str(home))
    monkeypatch.setenv("OSA_CONFIG_DIR", str(cfg))
    monkeypatch.setenv("OSA_LOG_DIR", str(logs))
    monkeypatch.setenv("OSA_LLM__PROVIDER", "stub")
    monkeypatch.setenv("OSA_LLM__API_KEY", "test-key")

    # Сбросить кеш _CONFIGURED в logging_setup, чтобы configure_logging
    # отрабатывал заново в каждом тесте
    from osa.logging_setup import reset_logging
    reset_logging()

    return home


@pytest.fixture
def initialized_db(tmp_osa_home: Path) -> Path:
    """БД с применёнными миграциями."""
    from osa.db import init_db

    init_db()
    return tmp_osa_home / "osa.db"
