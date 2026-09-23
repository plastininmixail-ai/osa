"""Тесты инструментов."""

from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture
def tmp_sandbox(tmp_path, monkeypatch):
    """Изолированный sandbox в tmp."""
    home = tmp_path / "osa_home"
    home.mkdir()
    sandbox = home / "sandbox"
    sandbox.mkdir()
    monkeypatch.setenv("OSA_HOME", str(home))
    return sandbox


def test_file_write_and_read(tmp_sandbox) -> None:
    from osa.tools.builtin import FileWriteTool, FileReadTool

    FileWriteTool().run(path="test.txt", content="hello world")
    r = FileReadTool().run(path="test.txt")
    assert r.success
    assert r.output == "hello world"


def test_file_read_blocks_path_traversal(tmp_sandbox) -> None:
    from osa.tools.builtin import FileReadTool

    r = FileReadTool().run(path="../../etc/passwd")
    assert not r.success
    assert "escapes sandbox" in r.error


def test_file_read_nonexistent(tmp_sandbox) -> None:
    from osa.tools.builtin import FileReadTool

    r = FileReadTool().run(path="missing.txt")
    assert not r.success
    assert "not found" in r.error.lower()


def test_file_list_returns_json(tmp_sandbox) -> None:
    from osa.tools.builtin import FileListTool, FileWriteTool
    import json

    FileWriteTool().run(path="a.txt", content="1")
    FileWriteTool().run(path="subdir/b.txt", content="2")

    r = FileListTool().run(dir=".")
    assert r.success
    entries = json.loads(r.output)
    names = {e["name"] for e in entries}
    assert "a.txt" in names
    assert "subdir" in names


def test_shell_executes_command(tmp_sandbox) -> None:
    from osa.tools.builtin import ShellTool

    r = ShellTool().run(command="echo hello_from_shell", timeout=5)
    assert r.success
    assert "hello_from_shell" in r.output


def test_shell_timeout(tmp_sandbox) -> None:
    from osa.tools.builtin import ShellTool

    r = ShellTool().run(command="sleep 5", timeout=1)
    assert not r.success
    assert "Timeout" in r.error


def test_shell_returns_nonzero_on_error(tmp_sandbox) -> None:
    from osa.tools.builtin import ShellTool

    r = ShellTool().run(command="false", timeout=5)
    assert not r.success
    assert "Exit code" in r.error


def test_http_get_success(tmp_sandbox) -> None:
    from osa.tools.builtin import HttpGetTool

    r = HttpGetTool().run(url="https://httpbin.org/get", timeout=15)
    assert r.success
    assert "HTTP 200" in r.output


def test_http_get_invalid_url(tmp_sandbox) -> None:
    from osa.tools.builtin import HttpGetTool

    r = HttpGetTool().run(url="http://this-domain-does-not-exist.invalid", timeout=5)
    assert not r.success


def test_registry_register_and_get(tmp_sandbox) -> None:
    from osa.tools import builtin, registry

    registry.reset()
    builtin.register_all()
    tools = registry.all_tools()
    assert len(tools) >= 5
    names = {t.name for t in tools}
    assert "file_read" in names
    assert "file_write" in names
    assert "file_list" in names
    assert "shell" in names
    assert "http_get" in names


def test_shell_requires_confirmation(tmp_sandbox) -> None:
    from osa.tools.builtin import ShellTool

    assert ShellTool().requires_confirmation is True


def test_file_tools_no_confirmation(tmp_sandbox) -> None:
    from osa.tools.builtin import FileReadTool, FileWriteTool, FileListTool

    assert FileReadTool().requires_confirmation is False
    assert FileWriteTool().requires_confirmation is False
    assert FileListTool().requires_confirmation is False
