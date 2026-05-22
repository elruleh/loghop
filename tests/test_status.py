from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from loghop.cli_commands.status import handle_status
from loghop.store import init_project
from loghop.terminal import Terminal, TerminalOptions


def _git_init_with_commit(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=root, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)
    (root / "a.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True, capture_output=True)


def _init_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git_init_with_commit(root)
    init_project(root)
    return root


def _plain_term() -> Terminal:
    return Terminal(options=TerminalOptions(plain=True))


class TestHandleStatus:
    def test_not_initialized(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _git_init_with_commit(repo)
        monkeypatch.chdir(repo)
        term = _plain_term()
        args = type("Args", (), {})()
        code = handle_status(args, term)
        assert code == 20
        assert term._result["initialized"] is False

    def test_initialized_repo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        term = _plain_term()
        args = type("Args", (), {})()
        code = handle_status(args, term)
        assert code == 0
        assert term._result["initialized"] is True
        assert term._result["repo"] == root.name
        assert "branch" in term._result
        assert "handoffs" in term._result

    def test_with_handoffs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        from loghop.store import create_handoff

        create_handoff(root, "codex", "test goal")
        term = _plain_term()
        args = type("Args", (), {})()
        code = handle_status(args, term)
        assert code == 0
        assert term._result["handoffs"] >= 1
        assert term._result["last_handoff"] is not None
