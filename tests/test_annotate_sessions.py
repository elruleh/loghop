"""Tests for session annotate and sessions list/show/reconcile CLI commands."""

from __future__ import annotations

import contextlib
import io
from collections.abc import Callable
from pathlib import Path

from loghop.store import project_paths
from loghop.store._session import create_session, find_session, finish_session, list_sessions

CliRunner = Callable[..., tuple[int, str, str]]


def _finalize_session(repo: Path, session_id: str) -> None:
    """Helper: mark a session as succeeded so it can be annotated."""
    finish_session(repo, session_id, status="succeeded", returncode=0)


def _cli_rich(argv: list[str], cwd: Path) -> tuple[int, str, str]:
    """Run the CLI without --plain so Rich rendering paths are exercised."""
    import os

    from loghop.cli import main

    prev = os.getcwd()
    try:
        os.chdir(str(cwd))
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()
    finally:
        os.chdir(prev)


# ---------------------------------------------------------------------------
# sessions annotate
# ---------------------------------------------------------------------------


class TestAnnotate:
    def test_annotates_latest_session_by_default(
        self, cli: CliRunner, initialized_repo: Path
    ) -> None:
        s = create_session(initialized_repo, provider="codex", goal="g")
        _finalize_session(initialized_repo, s.id)
        code, stdout, _ = cli(
            ["sessions", "annotate", "--summary", "fixed the bug"],
            cwd=initialized_repo,
        )
        assert code == 0
        assert "updated session" in stdout.lower()

    def test_annotates_explicit_session_id(self, cli: CliRunner, initialized_repo: Path) -> None:
        s = create_session(initialized_repo, provider="codex", goal="g")
        _finalize_session(initialized_repo, s.id)
        code, _, _ = cli(
            ["sessions", "annotate", s.id, "--summary", "explicit session"],
            cwd=initialized_repo,
        )
        assert code == 0
        meta = find_session(project_paths(initialized_repo), s.id)
        assert meta.summary == "explicit session"

    def test_annotate_with_decisions(self, cli: CliRunner, initialized_repo: Path) -> None:
        s = create_session(initialized_repo, provider="codex", goal="g")
        _finalize_session(initialized_repo, s.id)
        code, _, _ = cli(
            ["sessions", "annotate", "--decision", "used approach X"],
            cwd=initialized_repo,
        )
        assert code == 0
        meta = find_session(project_paths(initialized_repo), s.id)
        assert meta.decisions == ["used approach X"]

    def test_annotate_with_todos(self, cli: CliRunner, initialized_repo: Path) -> None:
        s = create_session(initialized_repo, provider="codex", goal="g")
        _finalize_session(initialized_repo, s.id)
        code, _, _ = cli(
            ["sessions", "annotate", "--todo", "refactor later", "--todo", "add tests"],
            cwd=initialized_repo,
        )
        assert code == 0
        meta = find_session(project_paths(initialized_repo), s.id)
        assert "refactor later" in meta.todos_pending

    def test_annotate_with_done(self, cli: CliRunner, initialized_repo: Path) -> None:
        s = create_session(initialized_repo, provider="codex", goal="g")
        _finalize_session(initialized_repo, s.id)
        code, _stdout, _ = cli(
            ["sessions", "annotate", "--done", "wrote unit tests"],
            cwd=initialized_repo,
        )
        assert code == 0

    def test_annotate_fails_without_any_flag(self, cli: CliRunner, initialized_repo: Path) -> None:
        s = create_session(initialized_repo, provider="codex", goal="g")
        _finalize_session(initialized_repo, s.id)
        code, _, stderr = cli(["sessions", "annotate"], cwd=initialized_repo)
        assert code == 2
        assert "at least one" in stderr

    def test_annotate_fails_when_no_sessions(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, _, stderr = cli(
            ["sessions", "annotate", "--summary", "nothing"], cwd=initialized_repo
        )
        assert code == 2
        assert "no sessions" in stderr.lower()

    def test_annotate_persists_status_annotated(
        self, cli: CliRunner, initialized_repo: Path
    ) -> None:
        s = create_session(initialized_repo, provider="codex", goal="g")
        _finalize_session(initialized_repo, s.id)
        cli(
            ["sessions", "annotate", s.id, "--summary", "done"],
            cwd=initialized_repo,
        )
        meta = find_session(project_paths(initialized_repo), s.id)
        assert meta.status == "annotated"

    def test_annotate_rejects_running_session(self, cli: CliRunner, initialized_repo: Path) -> None:
        s = create_session(initialized_repo, provider="codex", goal="g")
        # Session is RUNNING — annotate must refuse
        code, _, stderr = cli(
            ["sessions", "annotate", s.id, "--summary", "should fail"],
            cwd=initialized_repo,
        )
        assert code == 2
        assert "running" in stderr.lower()


# ---------------------------------------------------------------------------
# sessions list
# ---------------------------------------------------------------------------


class TestSessionsList:
    def test_no_sessions(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, stdout, _ = cli(["sessions", "list"], cwd=initialized_repo)
        assert code == 0
        assert "no sessions" in stdout.lower()

    def test_lists_existing_sessions(self, cli: CliRunner, initialized_repo: Path) -> None:
        create_session(initialized_repo, provider="codex", goal="my goal")
        code, stdout, _ = cli(["sessions", "list"], cwd=initialized_repo)
        assert code == 0
        assert "S-001" in stdout

    def test_filters_by_provider(self, cli: CliRunner, initialized_repo: Path) -> None:
        create_session(initialized_repo, provider="codex", goal="g1")
        create_session(initialized_repo, provider="claude", goal="g2")
        code, stdout, _ = cli(["sessions", "list", "--provider", "codex"], cwd=initialized_repo)
        assert code == 0
        assert "S-001" in stdout
        assert "S-002" not in stdout

    def test_expand_flag_shows_detail(self, cli: CliRunner, initialized_repo: Path) -> None:
        s = create_session(initialized_repo, provider="codex", goal="g")
        finish_session(initialized_repo, s.id, status="succeeded", summary="done it")
        code, stdout, _ = cli(["sessions", "list", "--expand"], cwd=initialized_repo)
        assert code == 0
        assert "done it" in stdout


# ---------------------------------------------------------------------------
# sessions show
# ---------------------------------------------------------------------------


class TestSessionsShow:
    def test_show_by_id(self, cli: CliRunner, initialized_repo: Path) -> None:
        s = create_session(initialized_repo, provider="codex", goal="test goal")
        code, stdout, _ = cli(["sessions", "show", s.id], cwd=initialized_repo)
        assert code == 0
        assert "test goal" in stdout

    def test_show_latest(self, cli: CliRunner, initialized_repo: Path) -> None:
        create_session(initialized_repo, provider="codex", goal="latest")
        code, stdout, _ = cli(["sessions", "show", "--latest"], cwd=initialized_repo)
        assert code == 0
        assert "latest" in stdout

    def test_show_fails_without_id_or_latest(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, _, _stderr = cli(["sessions", "show"], cwd=initialized_repo)
        assert code == 2

    def test_show_fails_on_no_sessions_with_latest(
        self, cli: CliRunner, initialized_repo: Path
    ) -> None:
        code, _, stderr = cli(["sessions", "show", "--latest"], cwd=initialized_repo)
        assert code == 2
        assert "no sessions" in stderr.lower()


# ---------------------------------------------------------------------------
# sessions delete
# ---------------------------------------------------------------------------


class TestSessionsDelete:
    def test_delete_session_by_id(self, cli: CliRunner, initialized_repo: Path) -> None:
        s = create_session(initialized_repo, provider="codex", goal="delete me")
        _finalize_session(initialized_repo, s.id)
        code, stdout, _ = cli(["sessions", "delete", s.id, "-y"], cwd=initialized_repo)
        assert code == 0
        assert "deleted session" in stdout.lower()
        assert list_sessions(project_paths(initialized_repo)) == []

    def test_delete_latest_session(self, cli: CliRunner, initialized_repo: Path) -> None:
        s1 = create_session(initialized_repo, provider="codex", goal="old")
        _finalize_session(initialized_repo, s1.id)
        s2 = create_session(initialized_repo, provider="claude", goal="new")
        _finalize_session(initialized_repo, s2.id)
        code, stdout, _ = cli(["sessions", "delete", "--latest", "-y"], cwd=initialized_repo)
        assert code == 0
        assert "S-002" in stdout
        sessions = list_sessions(project_paths(initialized_repo))
        assert [s.id for s in sessions] == ["S-001"]

    def test_delete_requires_id_or_latest(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, _, stderr = cli(["sessions", "delete", "-y"], cwd=initialized_repo)
        assert code == 2
        assert "session id is required" in stderr.lower()


# ---------------------------------------------------------------------------
# sessions reconcile
# ---------------------------------------------------------------------------


class TestSessionsReconcile:
    def test_no_stranded_sessions(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, stdout, _ = cli(["sessions", "reconcile"], cwd=initialized_repo)
        assert code == 0
        assert "no running sessions to reconcile" in stdout.lower()

    def test_reconciles_running_session(self, cli: CliRunner, initialized_repo: Path) -> None:
        create_session(initialized_repo, provider="codex", goal="stuck")
        code, _stdout, _ = cli(["sessions", "reconcile"], cwd=initialized_repo)
        assert code == 0
        meta = find_session(project_paths(initialized_repo), "S-001")
        assert meta.status != "running"


# ---------------------------------------------------------------------------
# sessions list in Rich (non-plain) mode — exercises _render_rich_tree
# ---------------------------------------------------------------------------


class TestSessionsRichRendering:
    def test_sessions_list_rich_tree(self, initialized_repo: Path) -> None:
        create_session(initialized_repo, provider="codex", goal="rich goal")
        code, stdout, _ = _cli_rich(["sessions", "list"], initialized_repo)
        assert code == 0
        assert "[bold]" not in stdout
        assert "[dim]" not in stdout

    def test_sessions_list_no_sessions_rich(self, initialized_repo: Path) -> None:
        code, stdout, _ = _cli_rich(["sessions", "list"], initialized_repo)
        assert code == 0
        assert "no sessions" in stdout.lower()
