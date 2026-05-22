from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from loghop.cli_commands.annotate import handle_session_annotate
from loghop.store import init_project
from loghop.store._session import create_session, finish_session
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


def _finished_session(root: Path) -> None:
    session = create_session(root, provider="codex", goal="test")
    finish_session(root, session.id, status="succeeded", returncode=0)


class TestHandleSessionAnnotate:
    def test_no_fields_given_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        create_session(root, provider="codex", goal="test")
        term = _plain_term()
        args = argparse.Namespace(
            session_id="S-001", summary=None, decision=None, todo=None, done=None
        )
        code = handle_session_annotate(args, term)
        assert code == 2

    def test_annotate_with_summary(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        _finished_session(root)
        term = _plain_term()
        args = argparse.Namespace(
            session_id="S-001",
            summary="session completed",
            decision=None,
            todo=None,
            done=None,
        )
        code = handle_session_annotate(args, term)
        assert code == 0
        assert term._result["session_id"] == "S-001"
        assert term._result["updates"]["summary"] == "session completed"

    def test_annotate_with_multiple_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        _finished_session(root)
        term = _plain_term()
        args = argparse.Namespace(
            session_id="S-001",
            summary="done",
            decision=["chose X over Y"],
            todo=["finish auth"],
            done=["did login"],
        )
        code = handle_session_annotate(args, term)
        assert code == 0
        assert term._result["updates"]["decisions"] == ["chose X over Y"]
        assert term._result["updates"]["todos_pending"] == ["finish auth"]
        assert term._result["updates"]["todos_done"] == ["did login"]

    def test_defaults_to_latest_session(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        _finished_session(root)
        term = _plain_term()
        args = argparse.Namespace(
            session_id=None,
            summary="latest session",
            decision=None,
            todo=None,
            done=None,
        )
        code = handle_session_annotate(args, term)
        assert code == 0
        assert term._result["session_id"] == "S-001"

    def test_no_sessions_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        term = _plain_term()
        args = argparse.Namespace(
            session_id=None,
            summary="test",
            decision=None,
            todo=None,
            done=None,
        )
        code = handle_session_annotate(args, term)
        assert code == 2
