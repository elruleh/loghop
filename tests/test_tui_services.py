from __future__ import annotations

from pathlib import Path

import pytest
from conftest import init_repo

from loghop.store._handoff import create_handoff
from loghop.store._session import create_session, finish_session
from loghop.tui.services import TuiService


def test_projects_and_current_project_use_registry(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    session = create_session(root, provider="claude", goal="ship")
    finish_session(root, session.id, status="succeeded", returncode=0, summary="done")
    create_handoff(root, "codex", "next")

    service = TuiService(cwd=root)

    projects = service.projects()
    assert len(projects) == 1
    assert projects[0].current is True
    assert projects[0].session_count == 1
    assert projects[0].handoff_count == 1
    assert projects[0].last_session == "S-001"


def test_sessions_are_typed_models(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    session = create_session(root, provider="claude", goal="first")
    finish_session(
        root,
        session.id,
        status="succeeded",
        summary="done",
        returncode=0,
        decisions=["pick textual"],
        todos_pending=["ship polish"],
        todos_done=["open preview"],
        files_changed=["app.py"],
        turns_captured=3,
        transcript_path=".loghop/sessions/S-001.transcript.jsonl",
    )

    service = TuiService(cwd=root)

    sessions = service.sessions()
    assert sessions[0].id == "S-001"
    assert sessions[0].returncode == 0
    assert sessions[0].turns_captured == 3
    assert sessions[0].files_changed == ("app.py",)
    assert sessions[0].decisions == ("pick textual",)
    assert sessions[0].todos_pending == ("ship polish",)
    assert sessions[0].todos_done == ("open preview",)
    assert sessions[0].transcript_path == ".loghop/sessions/S-001.transcript.jsonl"
    assert sessions[0].path == root / ".loghop" / "sessions" / "S-001.md"


def test_timeline_returns_cross_provider_entries_newest_first(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    first = create_session(root, provider="codex", goal="first pass")
    finish_session(root, first.id, status="succeeded", returncode=0, summary="captured first pass")
    second = create_session(root, provider="claude", goal="second pass")
    finish_session(
        root, second.id, status="succeeded", returncode=0, summary="captured second pass"
    )

    service = TuiService(cwd=root)

    timeline = service.timeline()
    assert [entry.session_id for entry in timeline[:2]] == ["S-002", "S-001"]
    assert timeline[0].provider == "claude"
    assert timeline[0].title == "captured second pass"


def test_tui_timeline_passes_limit_to_store(tmp_path: Path) -> None:
    from unittest.mock import patch

    root = init_repo(tmp_path)
    service = TuiService(cwd=root)

    with (
        patch("loghop.tui.services.list_timeline_events", return_value=[]) as list_events,
        patch("loghop.tui.services.list_sessions", return_value=[]),
    ):
        assert service.timeline(root, limit=1) == []

    assert list_events.call_count == 1
    assert list_events.call_args.kwargs["limit"] == 1


def test_timeline_includes_failed_sessions_for_tui_filters(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    ok = create_session(root, provider="codex", goal="ok")
    finish_session(root, ok.id, status="succeeded", returncode=0, summary="ok summary")
    failed = create_session(root, provider="claude", goal="failed")
    finish_session(root, failed.id, status="failed", returncode=1, summary="failed summary")

    timeline = TuiService(cwd=root).timeline()

    assert [(entry.session_id, entry.status) for entry in timeline[:2]] == [
        ("S-002", "failed"),
        ("S-001", "succeeded"),
    ]


def test_timeline_preserves_handoff_and_returncode_metadata(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    session = create_session(root, provider="codex", goal="resume", handoff_id="H-007")
    finish_session(
        root,
        session.id,
        status="succeeded",
        returncode=42,
        summary="completed with warnings",
        transcript_path=".loghop/sessions/S-001.transcript.jsonl",
        turns_captured=3,
    )

    event = TuiService(cwd=root).timeline()[0]

    assert event.handoff_id == "H-007"
    assert event.returncode == 42
    assert event.transcript_path == ".loghop/sessions/S-001.transcript.jsonl"
    assert event.turns_captured == 3


def test_timeline_exposes_recent_conversation_excerpt(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    session = create_session(root, provider="codex", goal="conversation")
    transcript = root / ".loghop" / "sessions" / f"{session.id}.transcript.jsonl"
    transcript.write_text(
        '{"role": "user", "text": "Please inspect the memory", "ts": "2026-05-10T10:00:00Z"}\n'
        '{"role": "assistant", "text": "Memory is summarized in the preview", "ts": "2026-05-10T10:01:00Z"}\n',
        encoding="utf-8",
    )
    finish_session(
        root,
        session.id,
        status="succeeded",
        returncode=0,
        summary="conversation captured",
        transcript_path=f".loghop/sessions/{session.id}.transcript.jsonl",
        turns_captured=2,
    )

    event = TuiService(cwd=root).timeline()[0]

    assert event.conversation_excerpt == ()

    excerpt = TuiService(cwd=root).conversation_excerpt(root, event.session_id)
    assert excerpt == (
        ("user", "Please inspect the memory"),
        ("assistant", "Memory is summarized in the preview"),
    )


def test_timeline_keeps_running_session_visible(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    finished = create_session(root, provider="codex", goal="done")
    finish_session(root, finished.id, status="succeeded", returncode=0, summary="captured done")
    running = create_session(root, provider="claude", goal="still running")

    service = TuiService(cwd=root)

    timeline = service.timeline()
    assert timeline[0].session_id == running.id
    assert timeline[0].is_live is True
    assert timeline[1].session_id == finished.id


def test_providers_mark_installed_and_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    codex = bin_dir / "codex"
    codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    codex.chmod(0o755)

    def fake_which(name: str) -> str | None:
        return str(codex) if name == "codex" else None

    monkeypatch.setattr("loghop.providers.shutil.which", fake_which)

    providers = TuiService(cwd=root).providers()

    by_name = {provider.name: provider for provider in providers}
    assert by_name["codex"].installed is True
    assert by_name["codex"].path == codex
    assert by_name["codex"].default is True
    assert by_name["claude"].installed is False


def test_providers_empty_for_invalid_project_root(tmp_path: Path) -> None:
    invalid_root = tmp_path / "plain"
    invalid_root.mkdir()

    providers = TuiService(cwd=invalid_root).providers(invalid_root)

    assert providers == []
