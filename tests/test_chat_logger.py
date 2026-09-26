"""Тесты ChatLogger."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def test_logger_creates_file(tmp_path: Path) -> None:
    """При первом сообщении файл создаётся автоматически."""
    from osa.runtime.chat_logger import ChatLogger

    log_path = tmp_path / "chat_log.txt"
    logger = ChatLogger(log_path=log_path)
    logger.log_user("hello")

    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "[Пользователь]" in content
    assert "hello" in content


def test_logger_appends_not_overwrites(tmp_path: Path) -> None:
    """Каждое сообщение добавляется, не перезаписывает."""
    from osa.runtime.chat_logger import ChatLogger

    log_path = tmp_path / "chat_log.txt"
    logger = ChatLogger(log_path=log_path)
    logger.log_user("first")
    logger.log_user("second")
    logger.log_user("third")

    content = log_path.read_text(encoding="utf-8")
    assert "first" in content
    assert "second" in content
    assert "third" in content


def test_logger_exchange_format(tmp_path: Path) -> None:
    """log_exchange создаёт пару user+agent с пустой строкой между."""
    from osa.runtime.chat_logger import ChatLogger

    log_path = tmp_path / "chat_log.txt"
    logger = ChatLogger(log_path=log_path)
    logger.log_exchange("hello", "hi there", goal_id=42)

    content = log_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    # Ищем паттерн: user-line, agent-line, metadata, empty line
    user_idx = next(i for i, l in enumerate(lines) if "Пользователь" in l and "hello" in l)
    agent_idx = next(i for i, l in enumerate(lines) if "Агент" in l and "hi there" in l)
    assert user_idx < agent_idx
    # Пустая строка после metadata
    assert lines[user_idx + 3] == "" or lines[-1] == ""


def test_logger_read_returns_full_text(tmp_path: Path) -> None:
    """read() возвращает весь файл."""
    from osa.runtime.chat_logger import ChatLogger

    log_path = tmp_path / "chat_log.txt"
    logger = ChatLogger(log_path=log_path)
    logger.log_user("one")
    logger.log_user("two")

    text = logger.read()
    assert "one" in text
    assert "two" in text


def test_logger_clear_removes_file(tmp_path: Path) -> None:
    """clear() удаляет файл."""
    from osa.runtime.chat_logger import ChatLogger

    log_path = tmp_path / "chat_log.txt"
    logger = ChatLogger(log_path=log_path)
    logger.log_user("test")
    assert log_path.exists()
    logger.clear()
    assert not log_path.exists()


def test_logger_includes_metadata(tmp_path: Path) -> None:
    """log_exchange записывает metadata."""
    from osa.runtime.chat_logger import ChatLogger

    log_path = tmp_path / "chat_log.txt"
    logger = ChatLogger(log_path=log_path)
    logger.log_exchange("q", "a", goal_id=99, status="done")

    content = log_path.read_text(encoding="utf-8")
    assert "goal_id=99" in content
    assert "status=done" in content


def test_logger_default_path_uses_osa_home(tmp_path: Path, monkeypatch) -> None:
    """Без явного пути — использует $OSA_HOME/chat_log.txt."""
    monkeypatch.setenv("OSA_HOME", str(tmp_path))
    monkeypatch.setenv("OSA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OSA_LOG_DIR", str(tmp_path / "logs"))

    from importlib import reload
    from osa import paths as osa_paths

    reload(osa_paths)

    from osa.runtime.chat_logger import ChatLogger

    logger = ChatLogger()
    assert logger.log_path.parent == tmp_path
    assert logger.log_path.name == "chat_log.txt"
