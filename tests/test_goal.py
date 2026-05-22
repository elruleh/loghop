from __future__ import annotations

import argparse
import dataclasses
import subprocess
from pathlib import Path

import pytest

from loghop.cli_commands.goal import handle_goal
from loghop.store import init_project, load_config, project_paths, save_config
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


class TestHandleGoal:
    def test_show_unset_goal(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        term = _plain_term()
        args = argparse.Namespace(text=None, clear=False)
        code = handle_goal(args, term)
        assert code == 0
        assert term._result["goal"] == ""

    def test_set_goal(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        term = _plain_term()
        args = argparse.Namespace(text="ship auth module", clear=False)
        code = handle_goal(args, term)
        assert code == 0
        assert term._result["goal"] == "ship auth module"
        paths = project_paths(root)
        config = load_config(paths)
        assert config.goal == "ship auth module"

    def test_show_set_goal(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        paths = project_paths(root)
        config = load_config(paths)
        save_config(paths, dataclasses.replace(config, goal="my goal"))
        term = _plain_term()
        args = argparse.Namespace(text=None, clear=False)
        code = handle_goal(args, term)
        assert code == 0
        assert term._result["goal"] == "my goal"

    def test_clear_goal(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        paths = project_paths(root)
        config = load_config(paths)
        save_config(paths, dataclasses.replace(config, goal="existing"))
        term = _plain_term()
        args = argparse.Namespace(text=None, clear=True)
        code = handle_goal(args, term)
        assert code == 0
        assert term._result["goal"] == ""
        config_after = load_config(paths)
        assert config_after.goal == ""

    def test_goal_updates_memory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        term = _plain_term()
        args = argparse.Namespace(text="new goal", clear=False)
        handle_goal(args, term)
        paths = project_paths(root)
        assert paths.memory.exists()
        content = paths.memory.read_text(encoding="utf-8")
        assert "new goal" in content
