"""Тесты runtime.risk."""

from __future__ import annotations

from osa.runtime.risk import RiskAssessment, RiskLevel, assess_command


def test_safe_commands() -> None:
    """Read-only команды → SAFE."""
    assert assess_command("ls").level == RiskLevel.SAFE
    assert assess_command("ls -la").level == RiskLevel.SAFE
    assert assess_command("cat README.md").level == RiskLevel.SAFE
    assert assess_command("pwd").level == RiskLevel.SAFE
    assert assess_command("echo hello").level == RiskLevel.SAFE
    assert assess_command("head -n 5 file.txt").level == RiskLevel.SAFE
    assert assess_command("tail -f log.txt").level == RiskLevel.SAFE
    assert assess_command("grep -r 'foo' .").level == RiskLevel.SAFE
    assert assess_command("find . -name '*.py'").level == RiskLevel.SAFE
    assert assess_command("git status").level == RiskLevel.SAFE
    assert assess_command("git log --oneline -10").level == RiskLevel.SAFE


def test_low_risk_commands() -> None:
    """Команды которые читают много — LOW."""
    # du — disk usage, читает много, не меняет систему
    assert assess_command("du -sh /tmp").level == RiskLevel.LOW
    assert assess_command("df -h").level == RiskLevel.LOW


def test_dangerous_commands_critical() -> None:
    """Деструктивные команды → CRITICAL."""
    for cmd in [
        "rm file.txt",
        "rm -rf /",
        "rmdir empty_dir",
        "sudo apt install vim",
        "apt-get install nginx",
        "apt remove package",
        "pip uninstall django",
        "shutdown now",
        "reboot",
        "mkfs.ext4 /dev/sda1",
        "fdisk /dev/sda",
    ]:
        assessment = assess_command(cmd)
        assert assessment.level >= RiskLevel.CRITICAL, (
            f"{cmd} should be CRITICAL, got {assessment.level_name}"
        )
        assert assessment.requires_confirmation, f"{cmd} should require confirmation"


def test_dangerous_commands_high() -> None:
    """HIGH: установка пакетов, изменение прав, сеть."""
    for cmd in [
        "pip install django",
        "npm install express",
        "npm uninstall express",
        "chmod 644 file",
        "ssh user@host",
        "scp file user@host:",
    ]:
        assessment = assess_command(cmd)
        assert assessment.level >= RiskLevel.HIGH, f"{cmd} should be HIGH, got {assessment.level_name}"


def test_medium_risk_redirect() -> None:
    """Перенаправление вывода → MEDIUM."""
    assessment = assess_command("echo hello > output.txt")
    assert assessment.level >= RiskLevel.MEDIUM

    assessment = assess_command("cat file >> log.txt")
    assert assessment.level >= RiskLevel.MEDIUM


def test_medium_risk_mv_cp() -> None:
    """mv и cp → MEDIUM."""
    assert assess_command("mv a.txt b.txt").level >= RiskLevel.MEDIUM
    assert assess_command("cp src dst").level >= RiskLevel.MEDIUM


def test_safe_command_with_safe_modifiers() -> None:
    """ls с безопасными флагами остаётся SAFE."""
    assert assess_command("ls -la /tmp").level == RiskLevel.SAFE
    assert assess_command("cat -n file.txt").level == RiskLevel.SAFE
    assert assess_command("grep -i 'pattern' file").level == RiskLevel.SAFE


def test_safe_command_in_pipe() -> None:
    """Pipe без деструктивных операций остаётся SAFE."""
    assert assess_command("cat file.txt | grep pattern").level == RiskLevel.SAFE
    assert assess_command("ls -la | head").level == RiskLevel.SAFE


def test_unknown_command_without_safe_listing() -> None:
    """Неизвестная команда без модификаторов → LOW/SAFE."""
    assessment = assess_command("some_rare_command")
    # Неизвестная команда без опасных паттернов — LOW (по умолчанию)
    assert assessment.level <= RiskLevel.LOW


def test_assessment_has_reasons() -> None:
    """Каждая оценка имеет хотя бы одну причину."""
    a1 = assess_command("ls")
    assert isinstance(a1.reasons, list)

    a2 = assess_command("rm file")
    assert len(a2.reasons) >= 1


def test_level_name_method() -> None:
    """RiskAssessment.level_name возвращает строку."""
    a = assess_command("ls")
    assert a.level_name in ("safe", "low", "medium", "high", "critical")
