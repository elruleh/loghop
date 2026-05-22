from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from loghop.transcripts import (
    Turn,
    extract_decisions,
    extract_summary,
    extract_todos,
    get_reader,
)
from loghop.transcripts._claude import ClaudeTranscriptReader, _slug_for_cwd
from loghop.transcripts._codex import CodexTranscriptReader


def _write_jsonl(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def test_get_reader_known_providers() -> None:
    reader_claude = get_reader("claude")
    assert reader_claude is not None
    assert reader_claude.provider == "claude"  # type: ignore[attr-defined]
    reader_codex = get_reader("codex")
    assert reader_codex is not None
    assert reader_codex.provider == "codex"  # type: ignore[attr-defined]
    assert get_reader("unknown") is None


def test_extract_summary_picks_last_assistant() -> None:
    turns = [
        Turn(role="user", text="hi", ts=""),
        Turn(role="assistant", text="first", ts=""),
        Turn(role="user", text="more", ts=""),
        Turn(role="assistant", text="final answer here", ts=""),
    ]
    assert extract_summary(turns) == "final answer here"


def test_extract_summary_truncates_long_prose() -> None:
    """Prose-shaped long text gets truncated with an ellipsis."""
    # Real prose has sentence terminators — synthesize them so the log-like
    # heuristic doesn't trip.
    long = ("This is a sentence. " * 80).strip()
    turns = [Turn(role="assistant", text=long, ts="")]
    summary = extract_summary(turns, max_chars=100)
    assert len(summary) <= 100
    assert summary.endswith("…")


def test_extract_summary_uses_placeholder_for_log_like_dump() -> None:
    """A long blob with no sentence structure must not be returned as a summary."""
    long = "x" * 5000
    turns = [Turn(role="assistant", text=long, ts="")]
    summary = extract_summary(turns, max_chars=500)
    assert summary == "(no structured summary; see transcript)"


def test_extract_summary_placeholder_when_tool_result_dominates() -> None:
    """When most of the assistant turn is a tool_result dump, refuse to summarize."""
    text = "Here you go:\n[tool_result] " + ("a" * 5000)
    turns = [Turn(role="assistant", text=text, ts="")]
    summary = extract_summary(turns, max_chars=500)
    assert summary == "(no structured summary; see transcript)"


def test_extract_summary_empty_when_no_assistant() -> None:
    turns = [Turn(role="user", text="hi", ts="")]
    assert extract_summary(turns) == ""


def test_extract_decisions_matches_prefix() -> None:
    turns = [
        Turn(
            role="assistant",
            text="Decision: use sqlite\n\nSome prose.\nDecided: skip redis for now",
            ts="",
        ),
        Turn(role="user", text="Decision: ignored from user", ts=""),
    ]
    assert extract_decisions(turns) == ["use sqlite", "skip redis for now"]


def test_extract_todos_checkboxes_and_done() -> None:
    turns = [
        Turn(
            role="assistant",
            text="- [ ] write tests\n- [x] draft plan\n* [ ] deploy\nTODO: update docs",
            ts="",
        ),
    ]
    pending, done = extract_todos(turns)
    assert "write tests" in pending
    assert "deploy" in pending
    assert "update docs" in pending
    assert done == ["draft plan"]


def test_extract_todos_deduplicates() -> None:
    turns = [
        Turn(role="assistant", text="- [ ] task\n- [ ] task", ts=""),
    ]
    pending, _ = extract_todos(turns)
    assert pending == ["task"]


def test_extract_todos_removes_completed_items_from_pending() -> None:
    turns = [
        Turn(role="assistant", text="- [ ] write parser\n- [x] write parser", ts=""),
    ]

    pending, done = extract_todos(turns)

    assert pending == []
    assert done == ["write parser"]


def test_codex_reader_parses_agent_message_payload_without_duplicate_message(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rollout-agent-message.jsonl"
    _write_jsonl(
        path,
        [
            {
                "timestamp": "2026-05-15T10:00:00Z",
                "type": "response_item",
                "payload": {
                    "type": "agent_message",
                    "message": [{"type": "output_text", "text": "agent-only answer"}],
                },
            },
            {
                "timestamp": "2026-05-15T10:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "user_message",
                    "message": [{"type": "input_text", "text": "agent-only prompt"}],
                },
            },
        ],
    )

    turns = list(CodexTranscriptReader().parse(path))

    assert [(turn.role, turn.text) for turn in turns] == [
        ("assistant", "agent-only answer"),
        ("user", "agent-only prompt"),
    ]


def test_claude_slug_matches_path() -> None:
    assert _slug_for_cwd(Path("/home/raul/projects/loghop")) == "-home-raul-projects-loghop"


def test_claude_reader_finds_and_parses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_home = Path.home()
    cwd = tmp_path / "project"
    cwd.mkdir()

    slug = _slug_for_cwd(cwd)
    proj_dir = fake_home / ".claude" / "projects" / slug
    jsonl = proj_dir / "abc.jsonl"
    _write_jsonl(
        jsonl,
        [
            {"type": "permission-mode", "permissionMode": "default"},
            {
                "type": "user",
                "message": {"role": "user", "content": "hola"},
                "timestamp": "2026-04-24T10:00:00Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Decision: ship minimal"},
                        {"type": "tool_use", "name": "Read"},
                    ],
                },
                "timestamp": "2026-04-24T10:00:05Z",
            },
            {"type": "system", "message": {"role": "system", "content": "ignore me"}},
        ],
    )

    reader = ClaudeTranscriptReader()
    since = datetime.now(tz=UTC) - timedelta(hours=1)
    found = reader.find_latest(cwd, since)
    assert found == jsonl

    turns = list(reader.parse(found))
    assert len(turns) == 2
    assert turns[0].role == "user"
    assert turns[0].text == "hola"
    assert turns[1].role == "assistant"
    assert "Decision: ship minimal" in turns[1].text
    assert "[tool_use: Read]" in turns[1].text


def test_claude_reader_skips_files_older_than_since(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = Path.home()
    cwd = tmp_path / "project"
    cwd.mkdir()

    slug = _slug_for_cwd(cwd)
    proj_dir = fake_home / ".claude" / "projects" / slug
    old = proj_dir / "old.jsonl"
    _write_jsonl(old, [{"type": "user", "message": {"role": "user", "content": "x"}}])
    past = (datetime.now(tz=UTC) - timedelta(days=7)).timestamp()
    os.utime(old, (past, past))

    since = datetime.now(tz=UTC) - timedelta(hours=1)
    assert ClaudeTranscriptReader().find_latest(cwd, since) is None


def test_claude_reader_missing_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    Path.home()
    cwd = tmp_path / "project"
    cwd.mkdir()
    since = datetime.now(tz=UTC) - timedelta(hours=1)
    assert ClaudeTranscriptReader().find_latest(cwd, since) is None


def test_codex_reader_finds_by_cwd_meta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_home = Path.home()
    cwd = tmp_path / "project"
    cwd.mkdir()
    cwd_str = str(cwd.resolve())

    sessions = fake_home / ".codex" / "sessions" / "2026" / "04" / "24"
    matching = sessions / "rollout-2026-04-24T10-00-00-abc.jsonl"
    _write_jsonl(
        matching,
        [
            {
                "timestamp": "2026-04-24T10:00:00Z",
                "type": "session_meta",
                "payload": {"id": "abc", "cwd": cwd_str},
            },
            {
                "timestamp": "2026-04-24T10:00:05Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "arranca"}],
                },
            },
            {
                "timestamp": "2026-04-24T10:00:10Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "hecho"}],
                },
            },
        ],
    )
    other = sessions / "rollout-2026-04-24T11-00-00-zzz.jsonl"
    _write_jsonl(
        other,
        [
            {
                "timestamp": "2026-04-24T11:00:00Z",
                "type": "session_meta",
                "payload": {"id": "zzz", "cwd": "/some/other/path"},
            },
        ],
    )

    reader = CodexTranscriptReader()
    since = datetime.now(tz=UTC) - timedelta(hours=1)
    found = reader.find_latest(cwd, since)
    assert found == matching

    turns = list(reader.parse(found))
    assert [t.role for t in turns] == ["user", "assistant"]
    assert turns[0].text == "arranca"
    assert turns[1].text == "hecho"


def test_codex_reader_ignores_non_message_response_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = Path.home()
    cwd = tmp_path / "project"
    cwd.mkdir()
    cwd_str = str(cwd.resolve())

    sessions = fake_home / ".codex" / "sessions" / "2026" / "04" / "24"
    path = sessions / "rollout.jsonl"
    _write_jsonl(
        path,
        [
            {"type": "session_meta", "payload": {"cwd": cwd_str}},
            {"type": "event_msg", "payload": {"type": "task_started"}},
            {"type": "turn_context", "payload": {"cwd": cwd_str}},
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "system-ish"}],
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "real answer"}],
                },
            },
        ],
    )
    reader = CodexTranscriptReader()
    turns = list(reader.parse(path))
    assert len(turns) == 1
    assert turns[0].role == "assistant"
    assert turns[0].text == "real answer"


def test_codex_reader_missing_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    Path.home()
    cwd = tmp_path / "project"
    cwd.mkdir()
    since = datetime.now(tz=UTC) - timedelta(hours=1)
    assert CodexTranscriptReader().find_latest(cwd, since) is None
