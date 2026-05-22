from __future__ import annotations

import io
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import init_repo

from loghop.store import project_paths
from loghop.store._session import find_session, list_sessions

CliRunner = Callable[..., tuple[int, str, str]]


def _stage_transcript(root: Path, session_id: str, body: str, *, name: str | None = None) -> Path:
    """Write a Claude-style JSONL with one assistant turn into ~/.claude/projects/<slug>."""
    slug = str(root.resolve()).replace("/", "-")
    proj = Path.home() / ".claude" / "projects" / slug
    proj.mkdir(parents=True, exist_ok=True)
    path = proj / (name or f"{session_id}.jsonl")
    entry = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": body}],
        },
        "timestamp": "2026-04-25T10:00:00Z",
    }
    path.write_text(json.dumps(entry) + "\n")
    return path


def _run_hook(monkeypatch: pytest.MonkeyPatch, event: str, payload: dict[str, object]) -> int:
    from loghop.cli import main

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)
    return main(["--plain", "hook", event])


class TestSessionStartHook:
    def test_creates_session_with_claude_id(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        cli: CliRunner,
    ) -> None:
        root = init_repo(tmp_path)
        monkeypatch.chdir(root)
        rc = _run_hook(
            monkeypatch,
            "claude-session-start",
            {
                "session_id": "claude-uuid-123",
                "transcript_path": "/tmp/whatever.jsonl",
                "cwd": str(root),
                "hook_event_name": "SessionStart",
                "source": "startup",
            },
        )
        assert rc == 0
        sessions = list_sessions(project_paths(root))
        assert len(sessions) == 1
        assert sessions[0].claude_session_id == "claude-uuid-123"

    def test_outside_loghop_repo_is_noop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        monkeypatch.chdir(plain)
        rc = _run_hook(
            monkeypatch,
            "claude-session-start",
            {
                "session_id": "uuid",
                "cwd": str(plain),
                "hook_event_name": "SessionStart",
            },
        )
        assert rc == 0  # silent no-op

    def test_idempotent_on_repeated_start(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = init_repo(tmp_path)
        monkeypatch.chdir(root)
        for _ in range(3):
            _run_hook(
                monkeypatch,
                "claude-session-start",
                {"session_id": "x", "cwd": str(root)},
            )
        sessions = list_sessions(project_paths(root))
        assert len(sessions) == 1


class TestSessionEndHook:
    def test_finalizes_with_captured_transcript(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = init_repo(tmp_path)
        monkeypatch.chdir(root)
        # Start session
        _run_hook(
            monkeypatch,
            "claude-session-start",
            {"session_id": "claude-end-1", "cwd": str(root)},
        )
        # Stage transcript matching the session's slug
        wanted = _stage_transcript(
            root,
            "session",
            """All wrapped up.

```loghop
summary: end-to-end session captured via hook
decisions:
  - cleanly via SessionEnd
```
""",
        )
        _stage_transcript(root, "wrong", "wrong newer transcript", name="zzz-later.jsonl")
        # Fire SessionEnd
        rc = _run_hook(
            monkeypatch,
            "claude-session-end",
            {
                "session_id": "claude-end-1",
                "cwd": str(root),
                "transcript_path": str(wanted),
            },
        )
        assert rc == 0
        sessions = list_sessions(project_paths(root))
        assert len(sessions) == 1
        meta = find_session(project_paths(root), sessions[0].id)
        assert meta.status == "succeeded"
        assert meta.summary == "end-to-end session captured via hook"
        assert "cleanly via SessionEnd" in (meta.decisions or [])

    def test_late_capture_creates_session_when_no_start_fired(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = init_repo(tmp_path)
        monkeypatch.chdir(root)
        _stage_transcript(root, "late", "no block, just final answer")
        rc = _run_hook(
            monkeypatch,
            "claude-session-end",
            {"session_id": "claude-late-1", "cwd": str(root)},
        )
        assert rc == 0
        sessions = list_sessions(project_paths(root))
        assert len(sessions) == 1
        assert sessions[0].claude_session_id == "claude-late-1"

    def test_end_marks_failed_on_auth_failure_in_transcript(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = init_repo(tmp_path)
        monkeypatch.chdir(root)
        _run_hook(
            monkeypatch,
            "claude-session-start",
            {"session_id": "claude-auth-fail", "cwd": str(root)},
        )
        transcript = _stage_transcript(
            root,
            "auth-fail",
            "Claude Code is not logged in. Please run /login.",
        )
        rc = _run_hook(
            monkeypatch,
            "claude-session-end",
            {
                "session_id": "claude-auth-fail",
                "cwd": str(root),
                "transcript_path": str(transcript),
            },
        )
        assert rc == 0
        sessions = list_sessions(project_paths(root))
        meta = find_session(project_paths(root), sessions[0].id)
        assert meta.status == "failed"

    def test_end_marks_interrupted_when_no_transcript_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = init_repo(tmp_path)
        monkeypatch.chdir(root)
        _run_hook(
            monkeypatch,
            "claude-session-start",
            {"session_id": "claude-no-transcript", "cwd": str(root)},
        )
        rc = _run_hook(
            monkeypatch,
            "claude-session-end",
            {"session_id": "claude-no-transcript", "cwd": str(root)},
        )
        assert rc == 0
        sessions = list_sessions(project_paths(root))
        meta = find_session(project_paths(root), sessions[0].id)
        assert meta.status == "interrupted"

    def test_outside_loghop_repo_is_noop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        monkeypatch.chdir(plain)
        rc = _run_hook(
            monkeypatch,
            "claude-session-end",
            {"session_id": "x", "cwd": str(plain)},
        )
        assert rc == 0


class TestHookPayloadSchemaValidation:
    """Malformed hook payloads (wrong types, unknown events) must not crash
    the hook handler — Claude depends on it always exiting cleanly."""

    def test_handler_rejects_unknown_event_directly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Argparse already rejects unknown events at the CLI; this test
        # exercises the in-handler defense-in-depth guard for callers that
        # invoke handle_hook() bypassing argparse.
        from argparse import Namespace

        from loghop.cli_commands.hook import handle_hook
        from loghop.terminal import Terminal, TerminalOptions

        root = init_repo(tmp_path)
        monkeypatch.chdir(root)
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"cwd": str(root)})))
        monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)
        rc = handle_hook(Namespace(event="unknown-event"), Terminal(TerminalOptions(plain=True)))
        assert rc == 0
        assert list_sessions(project_paths(root)) == []

    def test_non_string_cwd_does_not_crash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # cwd as a number — schema violation.
        rc = _run_hook(
            monkeypatch,
            "claude-session-start",
            {"session_id": "x", "cwd": 123},
        )
        assert rc == 0

    def test_non_string_session_id_does_not_crash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = init_repo(tmp_path)
        monkeypatch.chdir(root)
        rc = _run_hook(
            monkeypatch,
            "claude-session-start",
            {"session_id": ["not", "a", "string"], "cwd": str(root)},
        )
        assert rc == 0
        # No session created for the malformed payload.
        assert list_sessions(project_paths(root)) == []

    def test_non_string_transcript_path_does_not_crash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = init_repo(tmp_path)
        monkeypatch.chdir(root)
        rc = _run_hook(
            monkeypatch,
            "claude-session-start",
            {
                "session_id": "ok-id",
                "transcript_path": {"oops": "dict"},
                "cwd": str(root),
            },
        )
        assert rc == 0
        # Schema error short-circuited before session creation.
        assert list_sessions(project_paths(root)) == []

    def test_completely_empty_payload_is_silent_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rc = _run_hook(monkeypatch, "claude-session-start", {})
        assert rc == 0
