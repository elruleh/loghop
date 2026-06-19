from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from conftest import init_repo

from loghop.reconcile import (
    auto_reconcile_silent,
    find_running_sessions,
    reconcile_running_sessions,
)
from loghop.store import project_paths
from loghop.store._session import create_session, find_session, finish_session

CliRunner = Callable[..., tuple[int, str, str]]


def _rewrite_session_start(root: Path, session_id: str, ts_start: str) -> None:
    """Rewrite the session's ts_start frontmatter to an explicit timestamp."""
    from loghop.store._index import rebuild_index

    md = project_paths(root).sessions / f"{session_id}.md"
    text = md.read_text()
    # Handle both JSON and YAML for robustness in tests
    text = re.sub(r'"ts_start":\s*"[^"]*"', f'"ts_start": "{ts_start}"', text)
    text = re.sub(r"ts_start:\s*.*", f"ts_start: '{ts_start}'", text)
    md.write_text(text)
    # Refresh the session index so list_sessions() picks up the new ts_start.
    rebuild_index(project_paths(root))


def _backdate_session(root: Path, session_id: str, hours_ago: int) -> None:
    """Rewrite the session's ts_start frontmatter to N hours ago."""
    old = (datetime.now(tz=UTC) - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")
    _rewrite_session_start(root, session_id, old)


def _stage_claude_transcript(cwd: Path, payload: dict[str, object]) -> Path:
    slug = str(cwd.resolve()).replace("/", "-")
    proj_dir = Path.home() / ".claude" / "projects" / slug
    proj_dir.mkdir(parents=True, exist_ok=True)
    path = proj_dir / "session.jsonl"
    path.write_text(json.dumps(payload) + "\n")
    return path


def _stage_named_claude_transcript(cwd: Path, name: str, payloads: list[dict[str, object]]) -> Path:
    slug = str(cwd.resolve()).replace("/", "-")
    proj_dir = Path.home() / ".claude" / "projects" / slug
    proj_dir.mkdir(parents=True, exist_ok=True)
    path = proj_dir / name
    path.write_text("\n".join(json.dumps(payload) for payload in payloads) + "\n")
    return path


class TestFindAndReconcile:
    def test_find_only_running_sessions(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        s1 = create_session(root, provider="claude", goal="g")
        finish_session(root, s1.id, status="succeeded", returncode=0)
        s2 = create_session(root, provider="claude", goal="g")  # left running
        del s2

        running = find_running_sessions(root)
        assert [s.id for s in running] == ["S-002"]

    def test_older_than_filter(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        s = create_session(root, provider="claude", goal="g")
        # Recent: should not match older_than=1h
        assert find_running_sessions(root, older_than=timedelta(hours=1)) == []
        _backdate_session(root, s.id, hours_ago=3)
        matched = find_running_sessions(root, older_than=timedelta(hours=1))
        assert [m.id for m in matched] == [s.id]

    def test_reconcile_captures_partial_transcript(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        s = create_session(root, provider="claude", goal="g")
        sid = s.id
        # Backdate so the transcript (mtime now) is after the session's ts_start.
        _backdate_session(root, sid, hours_ago=2)
        _stage_claude_transcript(
            root,
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "we got this far before kill."}],
                },
                "timestamp": "2026-04-25T10:00:00Z",
            },
        )

        reports = reconcile_running_sessions(root)
        assert len(reports) == 1
        assert reports[0]["status"] == "interrupted"
        assert reports[0]["turns_captured"] == 1

        meta = find_session(project_paths(root), sid)
        assert meta.status == "interrupted"
        assert meta.returncode == "130"
        assert "this far before kill" in meta.summary

    def test_reconcile_marks_interrupted_even_without_transcript(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        s = create_session(root, provider="claude", goal="g")
        _backdate_session(root, s.id, hours_ago=2)

        reports = reconcile_running_sessions(root)
        assert reports[0]["status"] == "interrupted"
        assert reports[0]["turns_captured"] == 0
        meta = find_session(project_paths(root), s.id)
        assert meta.status == "interrupted"

    def test_reconcile_does_not_attach_unrelated_later_transcript(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        s = create_session(root, provider="claude", goal="original goal")
        _backdate_session(root, s.id, hours_ago=2)
        now = datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
        path = _stage_named_claude_transcript(
            root,
            "unrelated.jsonl",
            [
                {
                    "type": "user",
                    "message": {"role": "user", "content": "completely unrelated work"},
                    "timestamp": now,
                },
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "later unrelated Claude work"}],
                    },
                    "timestamp": now,
                },
            ],
        )
        import os

        future = datetime.now(tz=UTC).timestamp() + 60
        os.utime(path, (future, future))

        reports = reconcile_running_sessions(root)

        assert reports[0]["status"] == "interrupted"
        assert reports[0]["turns_captured"] == 0
        meta = find_session(project_paths(root), s.id)
        assert meta.summary == ""
        assert not meta.turns_captured


class TestSessionsReconcileCommand:
    def test_command_reports_salvage(self, cli: CliRunner, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        create_session(root, provider="claude", goal="g")
        # Recent enough to skip auto-reconcile (>1h threshold) but still
        # picked up by explicit `sessions reconcile`.
        _stage_claude_transcript(
            root,
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "rescued."}],
                },
                "timestamp": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
            },
        )
        code, stdout, _ = cli(["sessions", "reconcile"], cwd=root)
        assert code == 0
        assert "recovered 1 turns" in stdout.lower()

    def test_command_no_op_when_clean(self, cli: CliRunner, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        s = create_session(root, provider="claude", goal="g")
        finish_session(root, s.id, status="succeeded", returncode=0)
        code, stdout, _ = cli(["sessions", "reconcile"], cwd=root)
        assert code == 0
        assert "no running sessions to reconcile" in stdout.lower()

    def test_command_reports_salvage_with_small_future_skew(
        self, cli: CliRunner, tmp_path: Path
    ) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="claude", goal="g")
        skewed = (datetime.now(tz=UTC) + timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
        _rewrite_session_start(root, session.id, skewed)
        _stage_claude_transcript(
            root,
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "rescued despite skew."}],
                },
                "timestamp": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
            },
        )
        code, stdout, _ = cli(["sessions", "reconcile"], cwd=root)
        assert code == 0
        assert "recovered 1 turns" in stdout.lower()

    def test_command_reconcile_continues_after_corrupt_session(
        self, cli: CliRunner, tmp_path: Path
    ) -> None:
        root = init_repo(tmp_path)
        create_session(root, provider="claude", goal="bad")
        create_session(root, provider="claude", goal="good")

        from unittest.mock import patch

        with patch(
            "loghop.cli_commands.sessions.reconcile_running_sessions",
            return_value=[
                {
                    "id": "S-001",
                    "provider": "claude",
                    "status": "reconcile_error",
                    "error": "broken session file",
                },
                {
                    "id": "S-002",
                    "provider": "claude",
                    "status": "interrupted",
                    "turns_captured": 1,
                },
            ],
        ):
            code, stdout, stderr = cli(["sessions", "reconcile"], cwd=root)

        assert code == 0
        assert "S-001: reconcile failed" in stderr
        assert "S-002: recovered 1 turns" in stdout


class TestAutoReconcileOnStartup:
    def test_stale_sessions_reconciled_silently(self, cli: CliRunner, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        s = create_session(root, provider="claude", goal="g")
        _backdate_session(root, s.id, hours_ago=2)

        # Any plain command triggers the auto-reconcile sweep.
        cli(["status"], cwd=root)

        meta = find_session(project_paths(root), s.id)
        assert meta.status == "interrupted"

    def test_recent_running_sessions_left_alone(self, cli: CliRunner, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        s = create_session(root, provider="claude", goal="g")
        cli(["status"], cwd=root)
        meta = find_session(project_paths(root), s.id)
        assert meta.status == "running"  # too recent

    def test_auto_reconcile_silent_handles_missing_root(self, tmp_path: Path) -> None:
        # Should never raise.
        auto_reconcile_silent(None)
        auto_reconcile_silent(tmp_path / "does-not-exist")
