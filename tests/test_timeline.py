from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import init_repo

from loghop.cli_commands.timeline import _render_timeline
from loghop.store import project_paths
from loghop.store._session import create_session, finish_session
from loghop.store._timeline import list_timeline_events

CliRunner = Callable[..., tuple[int, str, str]]


def test_timeline_records_provider_chain_in_one_file(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    paths = project_paths(root)
    for provider, summary in (
        ("codex", "started feature"),
        ("claude", "reviewed feature"),
        ("codex", "finished feature"),
    ):
        session = create_session(root, provider=provider, goal=summary)
        finish_session(root, session.id, status="succeeded", summary=summary)

    events = list_timeline_events(paths)

    assert paths.timeline.exists()
    assert [event["provider"] for event in events] == ["codex", "claude", "codex"]
    assert [event["session_id"] for event in events] == ["S-001", "S-002", "S-003"]
    assert [event["summary"] for event in events] == [
        "started feature",
        "reviewed feature",
        "finished feature",
    ]


def test_timeline_event_includes_session_resume_metadata(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    session = create_session(root, provider="codex", goal="resume", handoff_id="H-009")
    finish_session(root, session.id, status="succeeded", summary="done", returncode=7)

    event = list_timeline_events(project_paths(root))[0]

    assert event["handoff_id"] == "H-009"
    assert event["returncode"] == "7"


def test_timeline_cli_groups_by_time_and_provider(cli: CliRunner, tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    codex = create_session(root, provider="codex", goal="one")
    finish_session(root, codex.id, status="succeeded", summary="did codex work")
    claude = create_session(root, provider="claude", goal="two")
    finish_session(root, claude.id, status="succeeded", summary="did claude work")

    code, stdout, _ = cli(["timeline", "--limit", "10"], cwd=root)

    assert code == 0
    assert "# loghop timeline" in stdout
    assert "codex" in stdout
    assert "claude" in stdout
    assert "did codex work" in stdout
    assert "did claude work" in stdout


def test_timeline_cli_provider_filter(cli: CliRunner, tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    codex = create_session(root, provider="codex", goal="one")
    finish_session(root, codex.id, status="succeeded", summary="codex only")
    claude = create_session(root, provider="claude", goal="two")
    finish_session(root, claude.id, status="succeeded", summary="claude hidden")

    code, stdout, _ = cli(["timeline", "--provider", "codex"], cwd=root)

    assert code == 0
    assert "codex only" in stdout
    assert "claude hidden" not in stdout


@pytest.mark.skipif(not hasattr(Path, "symlink_to"), reason="symlinks unsupported")
def test_timeline_append_refuses_symlink_escape(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    paths = project_paths(root)
    escape = tmp_path / "escape.jsonl"
    paths.timeline.symlink_to(escape)

    session = create_session(root, provider="codex", goal="blocked symlink")
    finish_session(root, session.id, status="succeeded", summary="must stay in project")

    assert paths.timeline.is_symlink()
    assert not escape.exists()


def test_timeline_cli_orders_same_timestamp_by_session_number_desc() -> None:
    events = [
        {
            "ts": "2026-05-16T10:00:00Z",
            "provider": "codex",
            "session_id": "S-002",
            "status": "succeeded",
            "summary": "second",
        },
        {
            "ts": "2026-05-16T10:00:00Z",
            "provider": "claude",
            "session_id": "S-010",
            "status": "succeeded",
            "summary": "tenth",
        },
        {
            "ts": "2026-05-16T10:00:00Z",
            "provider": "codex",
            "session_id": "S-001",
            "status": "succeeded",
            "summary": "first",
        },
    ]

    rendered = _render_timeline(events)

    assert rendered.index("S-010") < rendered.index("S-002") < rendered.index("S-001")


def test_timeline_cli_notes_hidden_non_success_events(cli: CliRunner, tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    success = create_session(root, provider="codex", goal="good")
    finish_session(root, success.id, status="succeeded", summary="visible success")
    failed = create_session(root, provider="claude", goal="bad")
    finish_session(root, failed.id, status="failed", summary="hidden failure")

    code, stdout, _ = cli(["timeline"], cwd=root)

    assert code == 0
    assert "visible success" in stdout
    assert "hidden failure" not in stdout
    assert "1 non-success event(s) hidden; use --all-status" in stdout


def test_list_timeline_events_recovers_sessions_missing_from_partial_timeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init_repo(tmp_path)
    first = create_session(root, provider="claude", goal="first")
    finish_session(root, first.id, status="succeeded", returncode=0, summary="first summary")

    from loghop.store import _session as session_module

    second = create_session(root, provider="codex", goal="second")
    monkeypatch.setattr(
        session_module,
        "_append_timeline_best_effort",
        lambda _root, _session: "timeline append failed",
    )
    finish_session(root, second.id, status="succeeded", returncode=0, summary="second summary")

    events = list_timeline_events(project_paths(root), include_technical=True)

    assert [event["session_id"] for event in events] == ["S-001", "S-002"]
    assert events[-1]["summary"] == "second summary"
