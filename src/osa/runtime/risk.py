"""Классификация shell-команд по уровню опасности.

Безопасные команды выполняются без подтверждения.
Деструктивные — требуют явного одобрения пользователя через inline-кнопки
в Telegram или через CLI prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum


class RiskLevel(IntEnum):
    """Уровень риска команды."""

    SAFE = 0  # Только чтение, никаких изменений
    LOW = 1  # Может читать большие объёмы, но не меняет систему
    MEDIUM = 2  # Изменяет файлы в sandbox или окружение процесса
    HIGH = 3  # Системные изменения, установка ПО, сетевые операции
    CRITICAL = 4  # Удаление, форматирование, изменение прав, sudo


# Команды которые ТОЛЬКО читают (без побочных эффектов)
SAFE_COMMANDS = frozenset(
    {
        # Просмотр
        "ls", "dir", "pwd", "cd", "echo", "printf", "cat", "head", "tail",
        "less", "more", "file", "stat", "wc", "tree", "find",
        "which", "whereis", "type", "command", "help", "man", "info",
        "history", "alias", "unalias",
        # Чтение содержимого
        "grep", "egrep", "fgrep", "ack", "rg", "ag",
        "sed", "awk", "cut", "sort", "uniq", "tr", "tee",
        "diff", "cmp", "comm", "join", "paste", "expand", "unexpand",
        "xargs", "env", "printenv", "set", "unset",
        "date", "cal", "uptime", "whoami", "id", "groups", "who", "w",
        "uname", "hostname", "hostnamectl",
        # Сетевые (read-only)
        "ping", "traceroute", "nslookup", "dig", "host",
        # Git (read-only)
        "git log", "git status", "git diff", "git show", "git branch",
        "git log", "git remote", "git branch -a", "git tag", "git ls-files",
        # Python (read-only)
        "python --version", "python3 --version",
    }
)

# Паттерны опасных команд (regex)
DANGEROUS_PATTERNS = [
    # Удаление
    (r"\brm\s+", RiskLevel.CRITICAL),
    (r"\brmdir\s+", RiskLevel.CRITICAL),
    (r"\bdel\s+", RiskLevel.CRITICAL),
    (r"\bRemove-Item\b", RiskLevel.CRITICAL),
    # Перемещение/переименование (может сломать структуру)
    (r"\bmv\s+", RiskLevel.MEDIUM),
    (r"\bMove-Item\b", RiskLevel.MEDIUM),
    (r"\bren\s+", RiskLevel.MEDIUM),
    # Копирование
    (r"\bcp\s+", RiskLevel.MEDIUM),
    (r"\bcopy\b", RiskLevel.MEDIUM),
    (r"\bxcopy\b", RiskLevel.MEDIUM),
    # Права
    (r"\bchmod\s+", RiskLevel.HIGH),
    (r"\bchown\s+", RiskLevel.HIGH),
    (r"\bicacls\b", RiskLevel.HIGH),
    (r"\btakeown\b", RiskLevel.CRITICAL),
    # Установка/удаление ПО
    (r"\bapt(-get)?\s+(install|remove|purge)", RiskLevel.CRITICAL),
    (r"\bpip\s+install", RiskLevel.HIGH),
    (r"\bpip\s+uninstall", RiskLevel.CRITICAL),
    (r"\bnpm\s+install", RiskLevel.HIGH),
    (r"\bnpm\s+uninstall", RiskLevel.CRITICAL),
    (r"\bbrew\s+(install|uninstall)", RiskLevel.HIGH),
    (r"\bapt\s+upgrade", RiskLevel.CRITICAL),
    # Сетевые изменения
    (r"\bcurl\s+.*(-X|--request|-d|--data|-T|--upload|-o\s)", RiskLevel.MEDIUM),
    (r"\bwget\s+", RiskLevel.MEDIUM),
    (r"\bssh\s+", RiskLevel.HIGH),
    (r"\bscp\s+", RiskLevel.HIGH),
    (r"\brsync\s+", RiskLevel.HIGH),
    # Запись/перенаправление
    (r">\s*[\w/]", RiskLevel.MEDIUM),  # > file (redirect)
    (r">>\s*[\w/]", RiskLevel.MEDIUM),  # >> file (append)
    (r"\btee\s+", RiskLevel.MEDIUM),
    (r"\bdd\s+", RiskLevel.CRITICAL),
    # Системные
    (r"\bsudo\b", RiskLevel.CRITICAL),
    (r"\bsu\s+", RiskLevel.CRITICAL),
    (r"\breg\s+", RiskLevel.HIGH),  # Windows registry
    (r"\bsc\s+", RiskLevel.HIGH),  # Windows service control
    (r"\bnet\s+(user|localgroup)", RiskLevel.CRITICAL),
    (r"\bformat\s+", RiskLevel.CRITICAL),
    (r"\bdiskpart\b", RiskLevel.CRITICAL),
    (r"\bbcdedit\b", RiskLevel.CRITICAL),
    # Сеть опасная
    (r"\bnc\s+", RiskLevel.HIGH),
    (r"\bnetcat\s+", RiskLevel.HIGH),
    (r"\bcurl\s+.*\|.*sh", RiskLevel.CRITICAL),
    (r"\bcurl\s+.*\|.*bash", RiskLevel.CRITICAL),
    # Process/system
    (r"\bkill\s+-9", RiskLevel.HIGH),
    (r"\bkillall\s+", RiskLevel.CRITICAL),
    (r"\bpkill\s+", RiskLevel.CRITICAL),
    (r"\bshutdown\b", RiskLevel.CRITICAL),
    (r"\breboot\b", RiskLevel.CRITICAL),
    (r"\bpoweroff\b", RiskLevel.CRITICAL),
    # File system опасная
    (r"\bmkfs\b", RiskLevel.CRITICAL),
    (r"\bfdisk\b", RiskLevel.CRITICAL),
    (r"rm\s+-rf\s+/", RiskLevel.CRITICAL),
]

# Команды которые могут читать большие объёмы — LOW risk (нужно подтверждение, но низкий риск)
LOW_COMMANDS = frozenset(
    {
        "find", "grep", "rg", "cat", "tail", "head",
        "du", "df", "ls", "tree", "wc",
    }
)


@dataclass
class RiskAssessment:
    """Результат оценки риска команды."""

    level: RiskLevel
    reasons: list[str]

    @property
    def requires_confirmation(self) -> bool:
        """Требует ли команда подтверждения."""
        return self.level >= RiskLevel.MEDIUM

    @property
    def level_name(self) -> str:
        names = {
            RiskLevel.SAFE: "safe",
            RiskLevel.LOW: "low",
            RiskLevel.MEDIUM: "medium",
            RiskLevel.HIGH: "high",
            RiskLevel.CRITICAL: "critical",
        }
        return names.get(self.level, "unknown")


def assess_command(command: str) -> RiskAssessment:
    """Оценить уровень риска команды.

    Args:
        command: shell-команда для оценки

    Returns:
        RiskAssessment с уровнем и причинами
    """
    cmd = command.strip()
    cmd_lower = cmd.lower()
    reasons: list[str] = []
    max_level = RiskLevel.SAFE

    # Сначала проверяем "опасные" паттерны — они важнее
    for pattern, level in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd):
            if level > max_level:
                max_level = level
            # Извлекаем краткое имя команды для reason
            match = re.search(pattern, cmd)
            if match:
                token = match.group(0).strip()
                reasons.append(f"matches '{token}' ({level.name})")

    # Извлекаем первое слово (имя команды)
    first_word = cmd.split()[0] if cmd.split() else ""

    # Проверяем SAFE список — если первое слово там, и нет опасных паттернов
    if first_word.lower() in SAFE_COMMANDS and max_level <= RiskLevel.SAFE:
        return RiskAssessment(level=RiskLevel.SAFE, reasons=[f"safe command: {first_word}"])

    # Если первое слово в LOW_COMMANDS
    if first_word.lower() in LOW_COMMANDS:
        if max_level <= RiskLevel.LOW:
            return RiskAssessment(level=RiskLevel.LOW, reasons=[f"read-only command: {first_word}"])
        # Иначе остаётся уровень от опасных паттернов
        reasons.append(f"contains {first_word} but with dangerous modifiers")

    # Если ни одного матча — это unknown команда
    if not reasons:
        reasons.append(f"unknown command: {first_word}")

    return RiskAssessment(level=max_level, reasons=reasons)
