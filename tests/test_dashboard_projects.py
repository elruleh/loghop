"""Tests for dashboard / projects CLI commands."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from conftest import init_repo

from loghop.store._session import create_session, finish_session

CliRunner = Callable[..., tuple[int, str, str]]


class TestDashboard:
    def test_no_projects_registered(
        self, cli: CliRunner, loghop_env: object, tmp_path: Path
    ) -> None:
        code, stdout, _ = cli(["projects", "list"])
        assert code == 0
        assert "no loghop projects" in stdout.lower()

    def test_lists_registered_project(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, stdout, _ = cli(["projects", "list"], cwd=initialized_repo)
        assert code == 0
        assert "repo" in stdout

    def test_cleanup_no_missing(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, stdout, _ = cli(["projects", "cleanup"], cwd=initialized_repo)
        assert code == 0
        assert "valid" in stdout

    def test_cleanup_removes_missing(
        self, cli: CliRunner, initialized_repo: Path, tmp_path: Path
    ) -> None:
        ghost = init_repo(tmp_path, "ghost")
        from loghop.store._registry import touch_project

        touch_project(ghost)
        import shutil

        shutil.rmtree(ghost)
        code, stdout, _ = cli(["projects", "cleanup"], cwd=initialized_repo)
        assert code == 0
        assert "removed" in stdout.lower()


class TestProjectsShow:
    def test_show_by_name(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, stdout, _ = cli(["projects", "show", "repo"], cwd=initialized_repo)
        assert code == 0
        assert "repo" in stdout

    def test_show_duplicate_exact_name_errors(self, cli: CliRunner, tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        init_repo(tmp_path / "a", "dup")
        init_repo(tmp_path / "b", "dup")

        code, _, stderr = cli(["projects", "show", "dup"], cwd=tmp_path)
        assert code == 2
        assert "ambiguous target" in stderr.lower()

    def test_show_by_path(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, _stdout, _ = cli(["projects", "show", str(initialized_repo)], cwd=initialized_repo)
        assert code == 0

    def test_show_fails_without_target(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, _, _stderr = cli(["projects", "show"], cwd=initialized_repo)
        assert code == 2

    def test_show_fails_unknown_project(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, _, stderr = cli(["projects", "show", "nonexistent-project"], cwd=initialized_repo)
        assert code == 2
        assert "no registered project" in stderr

    def test_show_includes_sessions(self, cli: CliRunner, initialized_repo: Path) -> None:
        s = create_session(initialized_repo, provider="codex", goal="fix bug")
        finish_session(initialized_repo, s.id, status="succeeded")
        code, stdout, _ = cli(["projects", "show", "repo"], cwd=initialized_repo)
        assert code == 0
        assert "S-001" in stdout

    def test_show_with_last_session_row(self, cli: CliRunner, initialized_repo: Path) -> None:
        s = create_session(initialized_repo, provider="codex", goal="g")
        finish_session(initialized_repo, s.id, status="succeeded")
        code, stdout, _ = cli(["projects", "show", "repo"], cwd=initialized_repo)
        assert code == 0
        assert "last session" in stdout


class TestProjectsRemovePurge:
    def test_remove_unregisters_project_but_keeps_local_store(
        self, cli: CliRunner, initialized_repo: Path
    ) -> None:
        code, stdout, _ = cli(["projects", "remove", "repo", "-y"], cwd=initialized_repo)

        assert code == 0
        assert "removed project" in stdout.lower()
        assert (initialized_repo / ".loghop" / "config.toml").exists()

        code, stdout, _ = cli(["projects", "list"], cwd=initialized_repo)
        assert code == 0
        assert "no loghop projects" in stdout.lower()

    def test_purge_unregisters_project_and_deletes_local_store(
        self, cli: CliRunner, tmp_path: Path
    ) -> None:
        root = init_repo(tmp_path, "alpha")

        code, stdout, _ = cli(["projects", "purge", "alpha", "-y"], cwd=tmp_path)

        assert code == 0
        assert "purged project" in stdout.lower()
        assert not (root / ".loghop").exists()

        code, stdout, _ = cli(["projects", "list"], cwd=tmp_path)
        assert code == 0
        assert "no loghop projects" in stdout.lower()

    def test_remove_duplicate_exact_name_errors(self, cli: CliRunner, tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        init_repo(tmp_path / "a", "dup")
        init_repo(tmp_path / "b", "dup")

        code, _, stderr = cli(["projects", "remove", "dup", "-y"], cwd=tmp_path)
        assert code == 2
        assert "ambiguous target" in stderr.lower()


class TestSessionsExpandedRendering:
    """Cover the _render_expanded paths that need decisions/todos/files."""

    def test_expand_shows_decisions(self, cli: CliRunner, initialized_repo: Path) -> None:
        s = create_session(initialized_repo, provider="codex", goal="g")
        finish_session(
            initialized_repo,
            s.id,
            status="succeeded",
            decisions=["chose approach A", "deferred feature B"],
        )
        code, stdout, _ = cli(["sessions", "list", "--expand"], cwd=initialized_repo)
        assert code == 0
        assert "chose approach A" in stdout

    def test_expand_shows_many_decisions_truncated(
        self, cli: CliRunner, initialized_repo: Path
    ) -> None:
        s = create_session(initialized_repo, provider="codex", goal="g")
        finish_session(
            initialized_repo,
            s.id,
            status="succeeded",
            decisions=[f"decision {i}" for i in range(8)],
        )
        code, stdout, _ = cli(["sessions", "list", "--expand"], cwd=initialized_repo)
        assert code == 0
        assert "more decisions" in stdout

    def test_expand_shows_files_changed(self, cli: CliRunner, initialized_repo: Path) -> None:
        s = create_session(initialized_repo, provider="codex", goal="g")
        finish_session(
            initialized_repo,
            s.id,
            status="succeeded",
            files_changed=["src/main.py", "tests/test_main.py"],
        )
        code, stdout, _ = cli(["sessions", "list", "--expand"], cwd=initialized_repo)
        assert code == 0
        assert "src/main.py" in stdout

    def test_expand_shows_todos(self, cli: CliRunner, initialized_repo: Path) -> None:
        s = create_session(initialized_repo, provider="codex", goal="g")
        finish_session(
            initialized_repo,
            s.id,
            status="succeeded",
            todos_pending=[f"todo {i}" for i in range(7)],
        )
        code, stdout, _ = cli(["sessions", "list", "--expand"], cwd=initialized_repo)
        assert code == 0
        assert "more todos" in stdout
