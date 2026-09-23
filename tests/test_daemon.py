"""Тесты runtime.daemon.

Используют реальный OSA_HOME (не sandbox), чтобы не конфликтовать с основным демоном.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time


def test_daemon_state_table_exists(tmp_osa_home, initialized_db) -> None:
    """Таблица daemon_state создана миграцией 003."""
    from osa.db import connect

    conn = connect()
    tables = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()

    assert "daemon_state" in tables


def test_update_daemon_state_creates_row(tmp_osa_home, initialized_db) -> None:
    """update_daemon_state создаёт строку id=1 если её нет (для совместимости)."""
    from osa.db import connect
    from osa.runtime.daemon import update_daemon_state

    # До: строка может отсутствовать
    update_daemon_state(pid=12345, status="running")

    conn = connect()
    row = conn.execute(
        "SELECT * FROM daemon_state WHERE id=1"
    ).fetchone()
    conn.close()

    assert row is not None
    assert row["pid"] == 12345
    assert row["status"] == "running"


def test_update_daemon_state_heartbeat(tmp_osa_home, initialized_db) -> None:
    """heartbeat=True обновляет last_heartbeat."""
    from osa.db import connect
    from osa.runtime.daemon import update_daemon_state

    update_daemon_state(pid=999, status="running")
    update_daemon_state(pid=999, status="running", heartbeat=True)

    conn = connect()
    row = conn.execute(
        "SELECT last_heartbeat FROM daemon_state WHERE id=1"
    ).fetchone()
    conn.close()

    assert row["last_heartbeat"] is not None


def test_update_daemon_state_stop_clears_pid(tmp_osa_home, initialized_db) -> None:
    """status='stopped' очищает pid и last_heartbeat."""
    from osa.db import connect
    from osa.runtime.daemon import update_daemon_state

    update_daemon_state(pid=999, status="running", heartbeat=True)
    update_daemon_state(pid=None, status="stopped")

    conn = connect()
    row = conn.execute(
        "SELECT pid, last_heartbeat FROM daemon_state WHERE id=1"
    ).fetchone()
    conn.close()

    assert row["pid"] is None
    assert row["last_heartbeat"] is None


def test_process_exists_invalid_pid() -> None:
    """_process_exists возвращает False для несуществующих PID."""
    from osa.runtime.daemon import _process_exists

    assert _process_exists(-1) is False
    assert _process_exists(0) is False
    assert _process_exists(999999999) is False


def test_process_exists_for_current_pid() -> None:
    """_process_exists возвращает True для текущего процесса."""
    import os

    from osa.runtime.daemon import _process_exists

    assert _process_exists(os.getpid()) is True


def test_is_running_false_when_no_state(tmp_osa_home, initialized_db) -> None:
    """is_running возвращает False когда в БД нет running state."""
    from osa.runtime.daemon import is_running

    running, pid = is_running()
    assert running is False


def test_is_running_true_after_update(tmp_osa_home, initialized_db) -> None:
    """is_running True когда state=running и процесс жив."""
    import os

    from osa.runtime.daemon import is_running, update_daemon_state

    update_daemon_state(pid=os.getpid(), status="running", heartbeat=True)

    running, pid = is_running()
    assert running is True
    assert pid == os.getpid()


def test_is_running_false_after_pid_dies(tmp_osa_home, initialized_db) -> None:
    """is_running False когда PID мёртв."""
    from osa.runtime.daemon import is_running, update_daemon_state

    # 999999999 должен быть несуществующим PID
    update_daemon_state(pid=999999999, status="running", heartbeat=True)

    running, pid = is_running()
    assert running is False
