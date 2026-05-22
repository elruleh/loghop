from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from loghop.cli_commands.handoff import (
    _resolve_handoff_id,
    handle_handoff_build,
    handle_handoff_list,
    handle_handoff_show,
)
from loghop.errors import LoghopError
from loghop.store import init_project, project_paths
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


class TestResolveHandoffId:
    def test_explicit_id(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        paths = project_paths(root)
        result = _resolve_handoff_id(paths, "H-042", latest=False)
        assert result == "H-042"

    def test_latest_returns_most_recent(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        from loghop.store import create_handoff

        create_handoff(root, "codex", "first")
        create_handoff(root, "codex", "second")
        paths = project_paths(root)
        result = _resolve_handoff_id(paths, None, latest=True)
        assert result == "H-002"

    def test_latest_no_handoffs_raises(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        paths = project_paths(root)
        with pytest.raises(LoghopError, match="no handoffs found"):
            _resolve_handoff_id(paths, None, latest=True)

    def test_no_id_no_latest_raises(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        paths = project_paths(root)
        with pytest.raises(LoghopError, match="handoff id is required"):
            _resolve_handoff_id(paths, None, latest=False)


class TestHandleHandoffList:
    def test_empty_list(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        term = _plain_term()
        args = argparse.Namespace(provider=None)
        code = handle_handoff_list(args, term)
        assert code == 0
        assert term._result["handoffs"] == []

    def test_lists_handoffs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        from loghop.store import create_handoff

        create_handoff(root, "codex", "goal 1")
        create_handoff(root, "claude", "goal 2")
        term = _plain_term()
        args = argparse.Namespace(provider=None)
        code = handle_handoff_list(args, term)
        assert code == 0
        assert len(term._result["handoffs"]) == 2

    def test_filter_by_provider(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        from loghop.store import create_handoff

        create_handoff(root, "codex", "goal 1")
        create_handoff(root, "claude", "goal 2")
        term = _plain_term()
        args = argparse.Namespace(provider="codex")
        code = handle_handoff_list(args, term)
        assert code == 0
        assert len(term._result["handoffs"]) == 1


class TestHandleHandoffShow:
    def test_show_by_id(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        from loghop.store import create_handoff

        record = create_handoff(root, "codex", "show me")
        term = _plain_term()
        args = argparse.Namespace(handoff_id=record.id, latest=False)
        code = handle_handoff_show(args, term)
        assert code == 0
        assert term._result["id"] == record.id
        assert "markdown" in term._result

    def test_show_latest(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        from loghop.store import create_handoff

        create_handoff(root, "codex", "first")
        record2 = create_handoff(root, "codex", "second")
        term = _plain_term()
        args = argparse.Namespace(handoff_id=None, latest=True)
        code = handle_handoff_show(args, term)
        assert code == 0
        assert term._result["id"] == record2.id


class TestHandleHandoffBuild:
    def test_build_with_provider_and_goal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        term = _plain_term()
        args = argparse.Namespace(provider="codex", goal="build a feature")
        code = handle_handoff_build(args, term)
        assert code == 0
        assert term._result["provider"] == "codex"
        assert term._result["goal"] == "build a feature"
        assert term._result["id"].startswith("H-")

    def test_build_creates_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        term = _plain_term()
        args = argparse.Namespace(provider="codex", goal="test goal")
        handle_handoff_build(args, term)
        paths = project_paths(root)
        handoff_files = list(paths.handoffs.glob("*.md"))
        assert len(handoff_files) >= 1
