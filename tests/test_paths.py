"""Тесты osa.paths."""

from __future__ import annotations

import os
from pathlib import Path


def test_osa_home_from_env(tmp_osa_home: Path) -> None:
    """OSA_HOME берётся из переменной окружения."""
    from osa.paths import osa_home

    assert osa_home() == tmp_osa_home


def test_config_path_under_config_dir(tmp_osa_home: Path) -> None:
    """config_path лежит в OSA_CONFIG_DIR."""
    from osa.paths import config_dir, config_path

    assert config_path().parent == config_dir()


def test_db_path_under_osa_home(tmp_osa_home: Path) -> None:
    """db_path лежит в OSA_HOME."""
    from osa.paths import db_path

    assert db_path().parent == tmp_osa_home
    assert db_path().name == "osa.db"


def test_sandbox_dir_under_osa_home(tmp_osa_home: Path) -> None:
    from osa.paths import sandbox_dir

    assert sandbox_dir().parent == tmp_osa_home
    assert sandbox_dir().name == "sandbox"
