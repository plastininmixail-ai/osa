"""Тесты osa.config."""

from __future__ import annotations

from pathlib import Path

import pytest
import tomlkit


def test_load_returns_defaults_when_no_file(tmp_path: Path) -> None:
    """load_config без файла → дефолты."""
    from osa.config import load_config

    config = load_config(tmp_path / "nonexistent.toml")
    assert config.llm.provider == "minimax"
    assert config.llm.base_url == "https://api.minimax.io/v1"
    assert config.llm.model == "MiniMax-M3"
    assert config.logging.level == "info"
    assert config.logging.json_logs is True


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    """save → load → значения те же."""
    from osa.config import load_config, save_default_config

    path = tmp_path / "config.toml"
    save_default_config(path)
    assert path.exists()

    # Комментарии сохранились
    text = path.read_text(encoding="utf-8")
    assert "O.S.A." in text
    assert "OSA_LLM__API_KEY" in text

    # Загрузка
    config = load_config(path)
    assert config.llm.provider == "minimax"
    assert config.llm.timeout == 30.0
    assert config.logging.json_logs is True


def test_env_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Переменные окружения перекрывают значения из TOML."""
    from osa.config import load_config, save_default_config

    path = tmp_path / "config.toml"
    save_default_config(path)

    monkeypatch.setenv("OSA_LLM__PROVIDER", "stub")
    monkeypatch.setenv("OSA_LLM__MODEL", "test-model")
    monkeypatch.setenv("OSA_LLM__BASE_URL", "http://localhost:1234/v1")

    config = load_config(path)
    assert config.llm.provider == "stub"
    assert config.llm.model == "test-model"
    assert config.llm.base_url == "http://localhost:1234/v1"
