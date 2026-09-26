"""Логирование переписки пользователь↔агент в отдельный файл.

Формат:
    [Пользователь]: <текст>
    [Агент]: <текст>

    [Пользователь]: <текст>
    [Агент]: <текст>

Пустая строка между парами сообщений. Используется append-режим,
не перезаписывает существующий лог.

Путь к файлу по умолчанию: $OSA_HOME/chat_log.txt
Можно переопределить через ChatLogger(log_path=...).
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ChatLogger:
    """Потокобезопасный логгер переписки."""

    def __init__(self, log_path: Path | None = None) -> None:
        from osa.paths import osa_home

        self.log_path = log_path or (osa_home() / "chat_log.txt")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log_user(self, text: str, user_id: int | None = None) -> None:
        """Записать сообщение пользователя."""
        self._append("Пользователь", text, user_id=user_id)

    def log_agent(self, text: str, **metadata: Any) -> None:
        """Записать ответ агента."""
        self._append("Агент", text, **metadata)

    def log_exchange(self, user_text: str, agent_text: str, **metadata: Any) -> None:
        """Записать пару user+agent одной операцией (с пустой строкой между)."""
        with self._lock:
            self._write_pair(user_text, agent_text, metadata)

    def _append(self, role: str, text: str, **metadata: Any) -> None:
        with self._lock:
            ts = datetime.now(timezone.utc).isoformat()
            meta_str = ""
            if metadata:
                meta_str = " " + " ".join(f"{k}={v}" for k, v in metadata.items() if k != "user_id")
            line = f"[{ts}] [{role}]{meta_str}: {text}\n"
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(line)

    def _write_pair(self, user_text: str, agent_text: str, metadata: dict[str, Any]) -> None:
        """Записать user+agent как один exchange с пустой строкой между."""
        ts = datetime.now(timezone.utc).isoformat()
        meta_str = ""
        if metadata:
            meta_str = " " + " ".join(f"{k}={v}" for k, v in metadata.items())
        block = (
            f"[{ts}] [Пользователь]: {user_text}\n"
            f"[{ts}] [Агент]: {agent_text}\n"
            f"{meta_str}\n\n"
        )
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(block)

    def read(self) -> str:
        """Прочитать весь лог."""
        if not self.log_path.exists():
            return ""
        return self.log_path.read_text(encoding="utf-8")

    def clear(self) -> None:
        """Очистить лог (осторожно)."""
        with self._lock:
            if self.log_path.exists():
                self.log_path.unlink()
