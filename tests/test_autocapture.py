from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import init_repo

from loghop.autocapture import capture_from_transcript, last_turns
from loghop.session_lifecycle import SessionContext, TranscriptOptions
from loghop.store import project_paths
from loghop.store._session import create_session, find_session


def _write_claude_transcript(
    fake_home: Path,
    cwd: Path,
    entries: list[dict[str, object]],
    *,
    name: str = "session.jsonl",
) -> Path:
    slug = str(cwd.resolve()).replace("/", "-")
    proj_dir = fake_home / ".claude" / "projects" / slug
    proj_dir.mkdir(parents=True, exist_ok=True)
    path = proj_dir / name
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return path


def _claude_assistant_entry(text: str, *, ts: str = "2026-04-24T10:00:00Z") -> dict[str, Any]:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        },
        "timestamp": ts,
    }


def test_capture_from_claude_transcript_populates_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = Path.home()

    root = init_repo(tmp_path)
    session = create_session(root, provider="claude", goal="test goal")
    session_id = session.id

    launch_ts = datetime.now(tz=UTC) - timedelta(seconds=1)
    _write_claude_transcript(
        fake_home,
        root,
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "implement feature X"},
                "timestamp": "2026-04-24T10:00:00Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Decision: split into two commits\n"
                                "- [ ] write tests\n"
                                "- [x] draft plan\n\n"
                                "Everything is wired up and working."
                            ),
                        }
                    ],
                },
                "timestamp": "2026-04-24T10:00:10Z",
            },
        ],
    )

    capture = capture_from_transcript(
        SessionContext(root=root, session_id=session_id, provider="claude", launch_ts=launch_ts),
        TranscriptOptions(),
    )
    assert capture.get("turns_captured") == 2
    assert capture.get("summary", "").startswith("Decision: split into two commits")
    assert "split into two commits" in capture.get("decisions", [])
    assert "write tests" in capture.get("todos_pending", [])
    assert "draft plan" in capture.get("todos_done", [])
    assert capture.get("transcript_path", "").endswith(f"{session_id}.transcript.jsonl")

    paths = project_paths(root)
    transcript_file = paths.sessions / f"{session_id}.transcript.jsonl"
    assert transcript_file.exists()
    assert transcript_file.stat().st_mode & 0o777 == 0o600

    turns = last_turns(root, session_id, limit=10)
    assert len(turns) == 2
    assert turns[0].role == "user"
    assert turns[1].role == "assistant"


def test_last_turns_rejects_symlinked_transcript(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    paths = project_paths(root)
    paths.sessions.mkdir(parents=True, exist_ok=True)
    real = paths.sessions / "S-001.transcript.jsonl"
    real.write_text(json.dumps({"role": "user", "text": "hi", "ts": ""}) + "\n")
    link = paths.sessions / "S-002.transcript.jsonl"
    link.symlink_to(real)

    assert [turn.text for turn in last_turns(root, "S-001")] == ["hi"]
    assert last_turns(root, "S-002") == []


def test_capture_returns_empty_when_no_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    Path.home()
    root = init_repo(tmp_path)
    session = create_session(root, provider="claude", goal="x")
    launch_ts = datetime.now(tz=UTC)
    assert (
        capture_from_transcript(
            SessionContext(
                root=root, session_id=session.id, provider="claude", launch_ts=launch_ts
            ),
            TranscriptOptions(),
        )
        == {}
    )


def test_capture_unknown_provider_is_noop(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    session = create_session(root, provider="claude", goal="x")
    assert (
        capture_from_transcript(
            SessionContext(
                root=root, session_id=session.id, provider="unknown", launch_ts=datetime.now(tz=UTC)
            ),
            TranscriptOptions(),
        )
        == {}
    )


def test_capture_redacts_secrets_in_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = Path.home()
    root = init_repo(tmp_path)
    session = create_session(root, provider="claude", goal="x")

    launch_ts = datetime.now(tz=UTC) - timedelta(seconds=1)
    _write_claude_transcript(
        fake_home,
        root,
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "export OPENAI_API_KEY=sk-abc123secretvalue\nAll good.",
                        }
                    ],
                },
                "timestamp": "2026-04-24T10:00:10Z",
            },
        ],
    )

    capture_from_transcript(
        SessionContext(root=root, session_id=session.id, provider="claude", launch_ts=launch_ts),
        TranscriptOptions(),
    )
    transcript_file = project_paths(root).sessions / f"{session.id}.transcript.jsonl"
    content = transcript_file.read_text()
    assert "sk-abc123" not in content
    assert "[redacted" in content


def test_capture_writes_fields_back_to_session_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = Path.home()
    root = init_repo(tmp_path)
    session = create_session(root, provider="claude", goal="x")
    session_id = session.id

    launch_ts = datetime.now(tz=UTC) - timedelta(seconds=1)
    _write_claude_transcript(
        fake_home,
        root,
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "All done and tested."}],
                },
                "timestamp": "2026-04-24T10:00:10Z",
            },
        ],
    )

    capture = capture_from_transcript(
        SessionContext(root=root, session_id=session_id, provider="claude", launch_ts=launch_ts),
        TranscriptOptions(),
    )

    from loghop.store._session import finish_session

    finish_session(root, session_id, status="succeeded", returncode=0, **capture)
    meta = find_session(project_paths(root), session_id)
    assert meta.summary == "All done and tested."
    assert meta.turns_captured == 1
    assert str(meta.transcript_path).endswith(f"{session_id}.transcript.jsonl")


def test_capture_prefers_explicit_transcript_path_over_latest_mtime(tmp_path: Path) -> None:
    fake_home = Path.home()
    root = init_repo(tmp_path)
    session = create_session(root, provider="claude", goal="x")

    desired = _write_claude_transcript(
        fake_home,
        root,
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "summary from explicit path"}],
                },
                "timestamp": "2026-04-24T10:00:10Z",
            },
        ],
        name="desired.jsonl",
    )
    newer = _write_claude_transcript(
        fake_home,
        root,
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "wrong newer transcript"}],
                },
                "timestamp": "2026-04-24T10:00:11Z",
            },
        ],
        name="newer.jsonl",
    )
    os.utime(newer, (desired.stat().st_atime + 60, desired.stat().st_mtime + 60))

    capture = capture_from_transcript(
        SessionContext(
            root=root,
            session_id=session.id,
            provider="claude",
            launch_ts=datetime.now(tz=UTC) - timedelta(seconds=1),
        ),
        TranscriptOptions(source_path=desired),
    )

    assert capture.get("summary") == "summary from explicit path"


def test_capture_rejects_explicit_transcript_path_outside_provider_root(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    session = create_session(root, provider="claude", goal="g")
    outside = tmp_path / "outside.jsonl"
    outside.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "leaked secret"}],
                },
                "timestamp": "2026-05-10T00:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = capture_from_transcript(
        SessionContext(
            root=root,
            session_id=session.id,
            provider="claude",
            launch_ts=datetime.now(tz=UTC) - timedelta(seconds=1),
        ),
        TranscriptOptions(source_path=outside),
    )

    assert result == {}
    assert not (project_paths(root).sessions / f"{session.id}.transcript.jsonl").exists()


@pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
def test_capture_rejects_explicit_transcript_symlink(tmp_path: Path) -> None:
    fake_home = Path.home()
    root = init_repo(tmp_path)
    session = create_session(root, provider="claude", goal="g")
    real = _write_claude_transcript(
        fake_home,
        root,
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "through symlink"}],
                },
                "timestamp": "2026-05-10T00:00:00Z",
            }
        ],
        name="target.jsonl",
    )
    link = real.parent / "link.jsonl"
    link.symlink_to(real)

    result = capture_from_transcript(
        SessionContext(
            root=root,
            session_id=session.id,
            provider="claude",
            launch_ts=datetime.now(tz=UTC) - timedelta(seconds=1),
        ),
        TranscriptOptions(source_path=link),
    )

    assert result == {}


def test_capture_prefers_candidate_matching_prompt_hints(tmp_path: Path) -> None:
    fake_home = Path.home()
    root = init_repo(tmp_path)
    session = create_session(root, provider="claude", goal="x")
    launch_ts = datetime.now(tz=UTC) - timedelta(seconds=1)

    desired = _write_claude_transcript(
        fake_home,
        root,
        [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": "Goal: next step\nRead `.loghop/handoffs/H-002.md` before acting.",
                },
                "timestamp": "2026-04-24T10:00:00Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "matched transcript"}],
                },
                "timestamp": "2026-04-24T10:00:10Z",
            },
        ],
        name="desired.jsonl",
    )
    newer = _write_claude_transcript(
        fake_home,
        root,
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "unrelated prompt"},
                "timestamp": "2026-04-24T10:00:00Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "wrong newer transcript"}],
                },
                "timestamp": "2026-04-24T10:00:11Z",
            },
        ],
        name="newer.jsonl",
    )
    os.utime(newer, (desired.stat().st_atime + 60, desired.stat().st_mtime + 60))

    capture = capture_from_transcript(
        SessionContext(
            root=root,
            session_id=session.id,
            provider="claude",
            launch_ts=launch_ts,
        ),
        TranscriptOptions(
            match_texts=["Goal: next step", "Read `.loghop/handoffs/H-002.md` before acting."]
        ),
    )

    assert capture.get("summary") == "matched transcript"


def test_capture_ignores_turns_before_launch_in_reused_transcript(tmp_path: Path) -> None:
    fake_home = Path.home()
    root = init_repo(tmp_path)
    session = create_session(root, provider="claude", goal="new run")
    launch_ts = datetime(2026, 5, 15, 10, 0, 0, tzinfo=UTC)

    _write_claude_transcript(
        fake_home,
        root,
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "```loghop\n"
                                "summary: OLD CLAUDE SUMMARY\n"
                                "todos_pending:\n"
                                "  - old todo\n"
                                "```"
                            ),
                        }
                    ],
                },
                "timestamp": "2026-05-15T09:59:00Z",
            },
            {
                "type": "user",
                "message": {"role": "user", "content": "new prompt after launch"},
                "timestamp": "2026-05-15T10:00:01Z",
            },
        ],
    )

    capture = capture_from_transcript(
        SessionContext(root=root, session_id=session.id, provider="claude", launch_ts=launch_ts),
        TranscriptOptions(),
    )

    assert capture.get("turns_captured") == 1
    assert capture.get("summary") is None
    assert capture.get("todos_pending") is None
    turns = last_turns(root, session.id, limit=10)
    assert [turn.text for turn in turns] == ["new prompt after launch"]


def test_capture_uses_transcript_cwd_for_wrapped_subdirectories(tmp_path: Path) -> None:
    fake_home = Path.home()
    root = init_repo(tmp_path)
    session = create_session(root, provider="claude", goal="x")
    subdir = root / "nested"
    subdir.mkdir()
    launch_ts = datetime.now(tz=UTC) - timedelta(seconds=1)
    _write_claude_transcript(
        fake_home,
        subdir,
        [
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "subdir transcript"}],
                },
                "timestamp": "2026-04-24T10:00:10Z",
            },
        ],
    )

    capture = capture_from_transcript(
        SessionContext(
            root=root,
            session_id=session.id,
            provider="claude",
            launch_ts=launch_ts,
        ),
        TranscriptOptions(transcript_cwd=subdir),
    )

    assert capture.get("summary") == "subdir transcript"


def test_capture_truncates_each_saved_turn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_home = Path.home()
    root = init_repo(tmp_path)
    session = create_session(root, provider="claude", goal="x")
    monkeypatch.setattr("loghop.autocapture._MAX_TURN_CHARS", 20)
    _write_claude_transcript(
        fake_home,
        root,
        [_claude_assistant_entry("x" * 40)],
    )

    capture_from_transcript(
        SessionContext(
            root=root,
            session_id=session.id,
            provider="claude",
            launch_ts=datetime.now(tz=UTC) - timedelta(seconds=1),
        ),
        TranscriptOptions(),
    )

    transcript = project_paths(root).sessions / f"{session.id}.transcript.jsonl"
    saved = json.loads(transcript.read_text(encoding="utf-8").strip())
    assert saved["text"] == "x" * 20 + "…[truncated]"


def test_capture_limits_number_of_saved_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = Path.home()
    root = init_repo(tmp_path)
    session = create_session(root, provider="claude", goal="x")
    monkeypatch.setattr("loghop.autocapture._MAX_CAPTURED_TURNS", 3)
    _write_claude_transcript(
        fake_home,
        root,
        [_claude_assistant_entry(f"turn {idx}") for idx in range(5)],
    )

    capture = capture_from_transcript(
        SessionContext(
            root=root,
            session_id=session.id,
            provider="claude",
            launch_ts=datetime.now(tz=UTC) - timedelta(seconds=1),
        ),
        TranscriptOptions(),
    )

    assert capture["turns_captured"] == 3
    assert [turn.text for turn in last_turns(root, session.id, limit=10)] == [
        "turn 2",
        "turn 3",
        "turn 4",
    ]


def test_require_match_keeps_assistant_only_transcript_without_prompt_match(tmp_path: Path) -> None:
    fake_home = Path.home()
    root = init_repo(tmp_path)
    session = create_session(root, provider="claude", goal="x")
    _write_claude_transcript(
        fake_home,
        root,
        [_claude_assistant_entry("assistant-only summary")],
    )

    capture = capture_from_transcript(
        SessionContext(
            root=root,
            session_id=session.id,
            provider="claude",
            launch_ts=datetime.now(tz=UTC) - timedelta(seconds=1),
        ),
        TranscriptOptions(
            match_texts=["Goal: this prompt is not present"],
            require_match=True,
        ),
    )

    assert capture["summary"] == "assistant-only summary"


def test_stream_redacted_transcript(tmp_path: Path) -> None:
    from loghop.autocapture import _write_redacted_transcript
    from loghop.transcripts import Turn

    dest = tmp_path / "test.jsonl"
    turns = [Turn("user", "Hello", "2023-01-01T00:00:00Z")] * 3
    _write_redacted_transcript(dest, turns)

    with open(dest) as f:
        lines = f.readlines()
    assert len(lines) == 3
    assert json.loads(lines[0])["text"] == "Hello"
