from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from loghop.cli_commands.sessions import _resolve_session_id, _status_icon
from loghop.errors import LoghopError
from loghop.store import init_project, project_paths
from loghop.store._session import _apply_session_meta, create_session, finish_session
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


class TestResolveSessionId:
    def test_explicit_id(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        paths = project_paths(root)
        result = _resolve_session_id(paths, "S-042", latest=False)
        assert result == "S-042"

    def test_latest_returns_most_recent(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        create_session(root, provider="codex", goal="first")
        finish_session(root, "S-001", status="succeeded")
        create_session(root, provider="claude", goal="second")
        finish_session(root, "S-002", status="succeeded")
        paths = project_paths(root)
        result = _resolve_session_id(paths, None, latest=True)
        assert result == "S-002"

    def test_latest_no_sessions_raises(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        paths = project_paths(root)
        with pytest.raises(LoghopError, match="no sessions found"):
            _resolve_session_id(paths, None, latest=True)

    def test_no_id_no_latest_raises(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        paths = project_paths(root)
        with pytest.raises(LoghopError, match="session id is required"):
            _resolve_session_id(paths, None, latest=False)

    def test_invalid_format_raises(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        paths = project_paths(root)
        with pytest.raises(LoghopError, match="invalid session id"):
            _resolve_session_id(paths, "bad-id", latest=False)


class TestStatusIcon:
    def test_known_statuses(self) -> None:
        assert _status_icon("succeeded") != "succeeded"
        assert _status_icon("failed") != "failed"
        assert _status_icon("running") != "running"
        assert _status_icon("timed_out") != "timed_out"
        assert _status_icon("built") != "built"
        assert _status_icon("launch_failed") != "launch_failed"

    def test_unknown_returns_as_is(self) -> None:
        assert _status_icon("custom_status") == "custom_status"


class TestHandleSessionsList:
    def test_empty_list(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        term = _plain_term()
        from loghop.cli_commands.sessions import handle_sessions_list

        args = argparse.Namespace(provider=None, expand=False)
        code = handle_sessions_list(args, term)
        assert code == 0
        assert term._result["sessions"] == []

    def test_lists_sessions(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        create_session(root, provider="codex", goal="test")
        finish_session(root, "S-001", status="succeeded", summary="done")
        term = _plain_term()
        from loghop.cli_commands.sessions import handle_sessions_list

        args = argparse.Namespace(provider=None, expand=False)
        code = handle_sessions_list(args, term)
        assert code == 0
        assert len(term._result["sessions"]) == 1


class TestHandleSessionsReconcile:
    def test_no_stranded_sessions(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        term = _plain_term()
        from loghop.cli_commands.sessions import handle_sessions_reconcile

        args = argparse.Namespace()
        code = handle_sessions_reconcile(args, term)
        assert code == 0
        assert term._result["reconciled"] == []

    def test_reconciles_running_session(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        create_session(root, provider="codex", goal="test")
        term = _plain_term()
        from unittest.mock import patch

        from loghop.cli_commands.sessions import handle_sessions_reconcile

        with patch(
            "loghop.cli_commands.sessions.reconcile_running_sessions",
            return_value=[{"id": "S-001", "turns_captured": 3}],
        ):
            args = argparse.Namespace()
            code = handle_sessions_reconcile(args, term)
            assert code == 0
            assert len(term._result["reconciled"]) == 1


class TestHandleSessionsShow:
    def test_show_by_id(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        create_session(root, provider="codex", goal="test")
        finish_session(root, "S-001", status="succeeded", summary="all done")
        term = _plain_term()
        from loghop.cli_commands.sessions import handle_sessions_show

        args = argparse.Namespace(session_id="S-001", latest=False)
        code = handle_sessions_show(args, term)
        assert code == 0
        assert term._result["id"] == "S-001"

    def test_show_latest(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        create_session(root, provider="codex", goal="first")
        finish_session(root, "S-001", status="succeeded")
        create_session(root, provider="claude", goal="second")
        finish_session(root, "S-002", status="succeeded")
        term = _plain_term()
        from loghop.cli_commands.sessions import handle_sessions_show

        args = argparse.Namespace(session_id=None, latest=True)
        code = handle_sessions_show(args, term)
        assert code == 0
        assert term._result["id"] == "S-002"


def test_apply_session_meta_truncates_output():
    meta = {}
    large_output = "A" * 200_000
    _apply_session_meta(meta, "ended", "", None, None, None, None, large_output, None, "", None)
    assert "output" in meta
    assert len(meta["output"]) < 200_000
    assert meta["output"].endswith("[truncated]")
