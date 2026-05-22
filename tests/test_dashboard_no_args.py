from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from loghop.cli_commands._dashboard_no_args import handle_dashboard_no_args


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
    from loghop.store import init_project

    init_project(root)
    return root


class TestHandleDashboardNoArgs:
    def test_outside_project(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        args = type(
            "Args",
            (),
            {"plain": True, "quiet": False, "verbose": False, "json": False, "global_view": False},
        )()
        code = handle_dashboard_no_args(args)
        assert code == 0

    def test_inside_project(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        args = type(
            "Args",
            (),
            {"plain": True, "quiet": False, "verbose": False, "json": False, "global_view": False},
        )()
        code = handle_dashboard_no_args(args)
        assert code == 0

    def test_global_view_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        monkeypatch.chdir(root)
        args = type(
            "Args",
            (),
            {"plain": True, "quiet": False, "verbose": False, "json": False, "global_view": True},
        )()
        code = handle_dashboard_no_args(args)
        assert code == 0

    def test_with_goal_set(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _init_repo(tmp_path)
        import dataclasses

        from loghop.store import load_config, project_paths, save_config

        paths = project_paths(root)
        config = load_config(paths)
        save_config(paths, dataclasses.replace(config, goal="ship v2"))
        monkeypatch.chdir(root)
        args = type(
            "Args",
            (),
            {"plain": True, "quiet": False, "verbose": False, "json": False, "global_view": False},
        )()
        code = handle_dashboard_no_args(args)
        assert code == 0
