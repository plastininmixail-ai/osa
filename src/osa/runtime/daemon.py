"""Демон OSA — always-on процесс для long-running задач.

На M1a.5 демон пока что просто крутит heartbeat и принимает команды.
Полезная работа (планировщик задач, long-running goals) появится в M1b.

Команды CLI:
    osa start   — запустить демон в фоне
    osa stop    — graceful shutdown
    osa status  — показывает daemon pid/heartbeat/uptime

Состояние демона хранится в БД (таблица daemon_state).
PID-файл НЕ используется — на Windows subprocess.Popen.pid ненадёжен.
Вместо этого проверяем живость процесса через win32 API (psutil fallback).
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

from osa.db import connect
from osa.logging_setup import configure_logging, get_logger
from osa.paths import osa_home


HEARTBEAT_INTERVAL_SEC = 5


def _process_exists(pid: int) -> bool:
    """Проверить, существует ли процесс с данным PID."""
    if pid is None or pid <= 0:
        return False
    try:
        if os.name == "nt":
            # Windows: используем ctypes для OpenProcess
            import ctypes
            from ctypes import wintypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, wintypes.DWORD(pid)
            )
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        else:
            os.kill(pid, 0)
            return True
    except (OSError, AttributeError):
        return False


def is_running() -> tuple[bool, int | None]:
    """Проверить, запущен ли демон через БД.

    Returns:
        (running, pid) — running=True если heartbeat свежий (< 30 сек назад) и процесс жив
    """
    conn = connect()
    row = conn.execute(
        "SELECT pid, status, last_heartbeat FROM daemon_state WHERE id=1"
    ).fetchone()
    conn.close()

    if not row or row["status"] != "running" or row["pid"] is None:
        return False, row["pid"] if row else None

    # Дополнительно: проверяем что heartbeat не устарел (> 30с = процесс завис/умер)
    if row["last_heartbeat"]:
        try:
            from datetime import datetime, timezone
            last = datetime.fromisoformat(row["last_heartbeat"].replace(" ", "T"))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - last).total_seconds()
            if age > 30:
                return False, row["pid"]
        except (ValueError, AttributeError):
            pass

    # И что процесс реально жив
    if not _process_exists(row["pid"]):
        return False, row["pid"]

    return True, row["pid"]


def update_daemon_state(
    pid: int | None, status: str, heartbeat: bool = False
) -> None:
    """Обновить состояние демона в БД."""
    conn = connect()
    # Гарантируем что строка с id=1 существует
    conn.execute(
        "INSERT OR IGNORE INTO daemon_state (id, status) VALUES (1, 'stopped')"
    )
    if heartbeat:
        conn.execute(
            "UPDATE daemon_state SET pid=?, status=?, last_heartbeat=CURRENT_TIMESTAMP WHERE id=1",
            (pid, status),
        )
    else:
        if pid is None:
            conn.execute(
                "UPDATE daemon_state SET pid=NULL, status=?, last_heartbeat=NULL WHERE id=1",
                (status,),
            )
        else:
            conn.execute(
                "UPDATE daemon_state SET pid=?, status=?, "
                "started_at=CASE WHEN started_at IS NULL THEN CURRENT_TIMESTAMP ELSE started_at END, "
                "last_heartbeat=CURRENT_TIMESTAMP WHERE id=1",
                (pid, status),
            )
    conn.commit()
    conn.close()


def start() -> int:
    """Запустить демон в фоне. Возвращает PID процесса демона."""
    running, existing_pid = is_running()
    if running:
        return existing_pid or 0  # type: ignore[return-value]

    # Запускаем отдельный процесс через текущий интерпретатор
    if os.name == "nt":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        proc = subprocess.Popen(
            [sys.executable, "-m", "osa", "daemon-run"],
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        proc = subprocess.Popen(
            [sys.executable, "-m", "osa", "daemon-run"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    # proc.pid на Windows часто != реальный PID процесса из-за слоёв.
    # Ждём пока daemon-run стартует и запишет свой настоящий PID в БД.
    time.sleep(0.5)

    for _ in range(20):  # до 4 секунд
        running, real_pid = is_running()
        if running and real_pid:
            return real_pid
        time.sleep(0.2)

    # Не получили PID из БД — fallback
    update_daemon_state(proc.pid, "starting")
    return proc.pid


def stop(timeout: float = 5.0) -> bool:
    """Остановить демон. Возвращает True если остановился."""
    running, pid = is_running()
    if not running:
        update_daemon_state(None, "stopped")
        return True

    update_daemon_state(pid, "stopping")

    try:
        if os.name == "nt":
            os.kill(pid, signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        else:
            os.kill(pid, signal.SIGTERM)
    except (OSError, AttributeError):
        pass

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_running()[0]:
            update_daemon_state(None, "stopped")
            return True
        time.sleep(0.1)

    # Не остановился — kill
    try:
        if os.name == "nt":
            # На Windows нет SIGKILL; используем TerminateProcess через ctypes
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.TerminateProcess(kernel32.OpenProcess(0x1F0FFF, False, pid), 1)
        else:
            os.kill(pid, signal.SIGKILL)
    except (OSError, AttributeError):
        pass

    update_daemon_state(None, "stopped")
    return False


def run_forever() -> None:
    """Главный цикл демона."""
    configure_logging()
    log = get_logger("osa.daemon")

    pid = os.getpid()
    update_daemon_state(pid, "running")
    log.info("daemon_started", extra={"pid": pid})

    running = True
    stop_signals = []

    def handle_signal(signum: int, frame: object) -> None:
        nonlocal running
        log.info("daemon_signal", extra={"signal": signum})
        running = False

    for sig_name in ("SIGTERM", "SIGINT", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, handle_signal)
            stop_signals.append(sig_name)
        except (ValueError, OSError) as e:
            log.debug("signal_skip", extra={"signal": sig_name, "error": str(e)})

    log.info("daemon_loop_start", extra={"stop_signals": stop_signals})

    iteration = 0
    while running:
        iteration += 1
        try:
            update_daemon_state(pid, "running", heartbeat=True)
            log.debug("heartbeat", extra={"iteration": iteration})
        except Exception as e:  # noqa: BLE001
            log.warning("heartbeat_failed", extra={"error": str(e), "iteration": iteration})

        # Короткие интервалы чтобы реагировать на сигналы
        slept = 0.0
        while slept < HEARTBEAT_INTERVAL_SEC and running:
            time.sleep(0.1)
            slept += 0.1

    update_daemon_state(None, "stopped")
    log.info("daemon_stopped")
