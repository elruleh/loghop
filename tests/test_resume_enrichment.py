from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import init_repo

from loghop.autocapture import capture_from_transcript
from loghop.session_lifecycle import SessionContext, TranscriptOptions
from loghop.store import load_config, project_paths
from loghop.store._handoff import create_resume_handoff
from loghop.store._session import create_session, find_session, finish_session


def _write_claude_transcript(fake_home: Path, cwd: Path, entries: list[dict[str, object]]) -> None:
    slug = str(cwd.resolve()).replace("/", "-")
    proj_dir = fake_home / ".claude" / "projects" / slug
    proj_dir.mkdir(parents=True, exist_ok=True)
    with (proj_dir / "session.jsonl").open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def test_resume_handoff_includes_prior_turns_and_transcript_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = Path.home()
    root = init_repo(tmp_path)
    paths = project_paths(root)

    # Create a previous session with a captured transcript.
    prev = create_session(root, provider="claude", goal="do the thing")
    prev_id = prev.id

    launch_ts = datetime.now(tz=UTC) - timedelta(seconds=1)
    _write_claude_transcript(
        fake_home,
        root,
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "start working"},
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
                                "Decision: go with sqlite\n- [ ] write migration\n\nDone for now."
                            ),
                        }
                    ],
                },
                "timestamp": "2026-04-24T10:00:10Z",
            },
        ],
    )
    capture = capture_from_transcript(
        SessionContext(root=root, session_id=prev_id, provider="claude", launch_ts=launch_ts),
        TranscriptOptions(),
    )
    finish_session(root, prev_id, status="succeeded", returncode=0, **capture)

    prev_meta = find_session(paths, prev_id)

    record = create_resume_handoff(
        root,
        "codex",
        "continue the work",
        previous_session=prev_meta,
    )
    assert record.md_path is not None
    markdown = record.md_path.read_text()

    assert "## Previous Session" in markdown
    assert "## Previous Session Excerpt" in markdown
    assert "> start working" in markdown
    assert "go with sqlite" in markdown
    assert f"{prev_id}.transcript.jsonl" in markdown


def test_resume_without_transcript_still_renders(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    paths = project_paths(root)
    prev = create_session(root, provider="claude", goal="x")
    finish_session(root, prev.id, status="succeeded", returncode=0)
    prev_meta = find_session(paths, prev.id)

    record = create_resume_handoff(root, "codex", "continue", previous_session=prev_meta)
    assert record.md_path is not None
    markdown = record.md_path.read_text()
    assert "## Previous Session" in markdown
    assert "## Previous Session Excerpt" not in markdown


def test_load_config_still_usable_after_resume(tmp_path: Path) -> None:
    # Regression: Phase 3 must not break config round-trip.
    root = init_repo(tmp_path)
    paths = project_paths(root)
    load_config(paths)


# ---------------------------------------------------------------------------
# render_resume_handoff_markdown — direct unit tests for uncovered branches
# ---------------------------------------------------------------------------


def _minimal_packet(goal: str = "test goal") -> dict[str, Any]:
    from datetime import UTC, datetime

    return {
        "ts": datetime.now(tz=UTC).isoformat(),
        "provider": "codex",
        "goal": goal,
        "project": {"name": "proj", "overview": "overview"},
        "repo_state": {
            "branch": "main",
            "head": "abc123",
            "dirty": False,
            "default_branch": "main",
            "changed_files": [],
        },
        "patch": "",
        "context": {
            "changed_files_included": 0,
            "changed_files_ignored": 0,
            "patch_truncated": False,
        },
    }


def test_render_resume_handoff_no_previous_session() -> None:
    from loghop.store._render import render_resume_handoff_markdown

    packet = _minimal_packet()
    md = render_resume_handoff_markdown("H-001", packet)
    assert "## Goal" in md
    assert "## Previous Session" not in md


def test_render_resume_handoff_no_changed_files() -> None:
    from loghop.store._render import render_handoff_markdown

    packet = _minimal_packet()
    md = render_handoff_markdown("H-001", packet)
    assert "No pending file changes" in md


def test_render_resume_handoff_with_patch() -> None:
    from loghop.store._render import render_handoff_markdown

    packet = _minimal_packet()
    packet["patch"] = "diff --git a/x b/x\n+added"
    md = render_handoff_markdown("H-001", packet)
    assert "## Patch" in md


def test_render_resume_handoff_todos_done() -> None:
    from loghop.store._render import render_resume_handoff_markdown

    packet = _minimal_packet()
    packet["previous_session"] = {
        "id": "S-001",
        "provider": "claude",
        "status": "succeeded",
        "summary": None,
        "decisions": None,
        "todos_done": ["finished task A", "finished task B"],
        "todos_pending": None,
        "last_turns": [],
        "transcript_path": None,
    }
    md = render_resume_handoff_markdown("H-001", packet)
    assert "Completed:" in md
    assert "finished task A" in md


def test_render_resume_handoff_long_turn_text() -> None:
    from loghop.store._render import render_resume_handoff_markdown

    packet = _minimal_packet()
    long_text = "x" * 1300
    packet["previous_session"] = {
        "id": "S-001",
        "provider": "claude",
        "status": "succeeded",
        "summary": None,
        "decisions": None,
        "todos_done": None,
        "todos_pending": None,
        "last_turns": [{"role": "assistant", "text": long_text, "ts": "2026-01-01T00:00:00Z"}],
        "transcript_path": None,
    }
    md = render_resume_handoff_markdown("H-001", packet)
    assert "…" in md


def test_render_resume_handoff_non_dict_turn() -> None:
    from loghop.store._render import render_resume_handoff_markdown

    packet = _minimal_packet()
    packet["previous_session"] = {
        "id": "S-001",
        "provider": "claude",
        "status": "succeeded",
        "summary": None,
        "decisions": None,
        "todos_done": None,
        "todos_pending": None,
        "last_turns": [
            "not-a-dict",
            {"role": "user", "text": "hello", "ts": "2026-01-01T00:00:00Z"},
        ],
        "transcript_path": None,
    }
    md = render_resume_handoff_markdown("H-001", packet)
    assert "hello" in md


def test_render_resume_handoff_empty_text_turn() -> None:
    from loghop.store._render import render_resume_handoff_markdown

    packet = _minimal_packet()
    packet["previous_session"] = {
        "id": "S-001",
        "provider": "claude",
        "status": "succeeded",
        "summary": None,
        "decisions": None,
        "todos_done": None,
        "todos_pending": None,
        "last_turns": [
            {"role": "user", "text": "   ", "ts": "2026-01-01T00:00:00Z"},
            {"role": "assistant", "text": "reply", "ts": "2026-01-01T00:00:01Z"},
        ],
        "transcript_path": None,
    }
    md = render_resume_handoff_markdown("H-001", packet)
    assert "reply" in md
