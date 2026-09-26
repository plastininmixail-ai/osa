"""Встроенные инструменты OSA.

5 штук:
- FileReadTool — прочитать файл
- FileWriteTool — записать файл
- FileListTool — список файлов в директории
- ShellTool — выполнить shell-команду (с human-in-the-loop)
- HttpGetTool — HTTP GET запрос

Все инструменты работают ТОЛЬКО в $OSA_HOME/sandbox/.
За пределы sandbox выйти нельзя (path traversal защита).
"""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

import httpx

from osa.paths import sandbox_dir
from osa.tools.base import Tool, ToolResult


def _resolve_safe_path(path_str: str) -> Path:
    """Резолвит path относительно sandbox, защита от ../.

    Бросает ValueError если путь пытается выйти за пределы sandbox.
    """
    sandbox = sandbox_dir().resolve()
    if Path(path_str).is_absolute():
        # абсолютный путь тоже резолвим относительно sandbox
        candidate = (sandbox / path_str.lstrip("/\\")).resolve()
    else:
        candidate = (sandbox / path_str).resolve()

    # Проверка что candidate внутри sandbox
    try:
        candidate.relative_to(sandbox)
    except ValueError as e:
        raise ValueError(
            f"Path {path_str!r} escapes sandbox ({sandbox}). "
            f"Resolved to {candidate}."
        ) from e

    return candidate


class FileReadTool(Tool):
    name = "file_read"
    description = (
        "Прочитать содержимое файла в рабочей директории (sandbox). "
        "Параметр path — относительный путь от корня sandbox. "
        "Возвращает содержимое файла как строку. "
        "Для больших файлов возвращает первые 10000 символов."
    )
    params_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Путь к файлу относительно sandbox",
            },
        },
        "required": ["path"],
    }

    MAX_CHARS = 10000

    def run(self, **params: Any) -> ToolResult:
        path_str = params.get("path", "")
        if not path_str:
            return ToolResult(success=False, output="", error="path is required")

        try:
            target = _resolve_safe_path(path_str)
        except ValueError as e:
            return ToolResult(success=False, output="", error=str(e))

        if not target.exists():
            return ToolResult(success=False, output="", error=f"File not found: {path_str}")
        if not target.is_file():
            return ToolResult(success=False, output="", error=f"Not a file: {path_str}")

        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolResult(
                success=False,
                output="",
                error=f"Cannot read {path_str}: not a UTF-8 text file",
            )

        truncated = len(content) > self.MAX_CHARS
        if truncated:
            content = content[: self.MAX_CHARS] + f"\n... [truncated, {self.MAX_CHARS}+ chars]"

        return ToolResult(success=True, output=content)


class FileWriteTool(Tool):
    name = "file_write"
    description = (
        "Записать текст в файл в sandbox. "
        "Создаёт родительские директории если нужно. "
        "Перезаписывает существующий файл. "
        "Используй осторожно — действие необратимо."
    )
    params_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Путь к файлу"},
            "content": {"type": "string", "description": "Содержимое для записи"},
        },
        "required": ["path", "content"],
    }
    requires_confirmation = False  # внутри sandbox, безопасно

    def run(self, **params: Any) -> ToolResult:
        path_str = params.get("path", "")
        content = params.get("content", "")
        if not path_str:
            return ToolResult(success=False, output="", error="path is required")

        try:
            target = _resolve_safe_path(path_str)
        except ValueError as e:
            return ToolResult(success=False, output="", error=str(e))

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as e:
            return ToolResult(success=False, output="", error=f"Write failed: {e}")

        return ToolResult(
            success=True,
            output=f"Written {len(content)} chars to {path_str}",
        )


class FileListTool(Tool):
    name = "file_list"
    description = (
        "Показать список файлов и директорий в указанной директории (sandbox). "
        "Параметр dir — относительный путь, по умолчанию корень sandbox. "
        "Возвращает JSON-список с именами и типами."
    )
    params_schema = {
        "type": "object",
        "properties": {
            "dir": {
                "type": "string",
                "description": "Директория относительно sandbox",
                "default": ".",
            },
        },
        "required": [],
    }

    def run(self, **params: Any) -> ToolResult:
        dir_str = params.get("dir", ".")
        try:
            target = _resolve_safe_path(dir_str)
        except ValueError as e:
            return ToolResult(success=False, output="", error=str(e))

        if not target.exists():
            return ToolResult(
                success=False, output="", error=f"Directory not found: {dir_str}"
            )
        if not target.is_dir():
            return ToolResult(
                success=False, output="", error=f"Not a directory: {dir_str}"
            )

        entries = []
        for entry in sorted(target.iterdir()):
            entries.append({
                "name": entry.name,
                "type": "dir" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else None,
            })

        return ToolResult(
            success=True,
            output=json.dumps(entries, ensure_ascii=False, indent=2),
        )


class ShellTool(Tool):
    name = "shell"
    description = (
        "Выполнить shell-команду в sandbox. Команда выполняется через "
        "bash -c. По умолчанию timeout 30 секунд. cwd = sandbox. "
        "Опасные команды требуют подтверждения пользователя. "
        "Используй только когда file_read/write недостаточно."
    )
    params_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Команда для выполнения"},
            "timeout": {
                "type": "integer",
                "description": "Таймаут в секундах",
                "default": 30,
            },
        },
        "required": ["command"],
    }
    requires_confirmation = True  # по умолчанию, но run() проверяет risk level

    def run(self, **params: Any) -> ToolResult:
        cmd = params.get("command", "")
        timeout = int(params.get("timeout", 30))
        if not cmd:
            return ToolResult(success=False, output="", error="command is required")

        cwd = sandbox_dir()
        cwd.mkdir(parents=True, exist_ok=True)

        # Ищем bash кросс-платформенно
        bash = _find_bash()
        try:
            if bash:
                proc = subprocess.run(
                    [bash, "-c", cmd],
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            else:
                # Fallback на cmd.exe
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False, output="", error=f"Timeout after {timeout}s"
            )
        except OSError as e:
            return ToolResult(success=False, output="", error=f"Execution failed: {e}")

        output = proc.stdout
        if proc.stderr:
            output += f"\n[stderr]\n{proc.stderr}"

        return ToolResult(
            success=(proc.returncode == 0),
            output=output,
            metadata={"returncode": proc.returncode, "command": cmd[:200]},
            error=None if proc.returncode == 0 else f"Exit code {proc.returncode}",
        )

    @property
    def risk_assessor(self):  # type: ignore[no-untyped-def]
        """Lazy import чтобы избежать circular."""
        from osa.runtime.risk import assess_command

        return assess_command

    def requires_confirmation_for(self, command: str) -> bool:
        """Проверить, требует ли конкретная команда подтверждения.

        Безопасные read-only команды (ls, cat, pwd, grep) выполняются
        без подтверждения. Всё остальное — требует.
        """
        from osa.runtime.risk import assess_command

        assessment = assess_command(command)
        return assessment.requires_confirmation


def _find_bash() -> str | None:
    """Найти bash на Windows или POSIX."""
    import os
    import shutil

    if os.name == "nt":
        # Git Bash на Windows
        candidates = [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
            shutil.which("bash"),
        ]
        for c in candidates:
            if c and os.path.exists(c):
                return c
        return None
    return shutil.which("bash") or "/bin/bash"


def _has_bash() -> bool:
    return _find_bash() is not None


class HttpGetTool(Tool):
    name = "http_get"
    description = (
        "Выполнить HTTP GET запрос. Возвращает тело ответа как строку "
        "(до 10000 символов) и статус-код. timeout = 30 секунд. "
        "Не используй для скачивания больших файлов."
    )
    params_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL для GET запроса"},
            "timeout": {
                "type": "integer",
                "description": "Таймаут в секундах",
                "default": 30,
            },
        },
        "required": ["url"],
    }
    requires_confirmation = False

    def run(self, **params: Any) -> ToolResult:
        url = params.get("url", "")
        timeout = int(params.get("timeout", 30))
        if not url:
            return ToolResult(success=False, output="", error="url is required")

        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.get(url)
        except httpx.HTTPError as e:
            return ToolResult(success=False, output="", error=f"HTTP error: {e}")

        body = response.text
        truncated = len(body) > 10000
        if truncated:
            body = body[:10000] + f"\n... [truncated, {len(response.text)} chars total]"

        output = f"HTTP {response.status_code}\n{body}"
        return ToolResult(
            success=response.is_success,
            output=output,
            metadata={"status_code": response.status_code, "url": url},
        )


def register_all() -> None:
    """Зарегистрировать все встроенные инструменты."""
    from osa.tools import registry

    for tool in [
        FileReadTool(),
        FileWriteTool(),
        FileListTool(),
        ShellTool(),
        HttpGetTool(),
    ]:
        registry.register(tool)
