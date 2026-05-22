"""Edge-case tests for store/_session.py."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from conftest import init_repo

from loghop.store import project_paths
from loghop.store._registry import load_registry
from loghop.store._session import (
    create_session,
    current_files_changed,
    delete_session,
    find_session,
    finish_session,
    latest_useful_session,
    list_sessions,
)
from loghop.store._timeline import recent_timeline_events


class TestFinishSessionEdgeCases:
    def test_finish_nonexistent_session_raises(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        with pytest.raises(ValueError, match="not found"):
            finish_session(root, "S-999", status="succeeded")

    def test_finish_appends_project_timeline_event(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        paths = project_paths(root)
        session = create_session(root, provider="codex", goal="ship")

        finish_session(root, session.id, status="succeeded", summary="implemented feature")

        assert paths.timeline.exists()
        events = recent_timeline_events(paths)
        assert events[-1]["session_id"] == session.id
        assert events[-1]["provider"] == "codex"
        assert events[-1]["summary"] == "implemented feature"

    def test_timeline_summary_is_clipped(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        paths = project_paths(root)
        session = create_session(root, provider="codex", goal="ship")

        finish_session(root, session.id, status="succeeded", summary="x" * 2000)

        events = recent_timeline_events(paths)
        assert len(events[-1]["summary"]) == 1200
        assert events[-1]["summary"].endswith("…")

    def test_finish_session_without_frontmatter_raises(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        paths = project_paths(root)
        sessions_dir = paths.sessions
        sessions_dir.mkdir(parents=True, exist_ok=True)
        bad_file = sessions_dir / "S-001.md"
        bad_file.write_text("no frontmatter here\n", encoding="utf-8")
        with pytest.raises(ValueError, match="no frontmatter"):
            finish_session(root, "S-001", status="succeeded")


class TestListSessionsEdgeCases:
    def test_list_sessions_no_dir(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        paths = project_paths(root)
        assert list_sessions(paths) == []

    def test_list_sessions_skips_files_without_id(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        paths = project_paths(root)
        sessions_dir = paths.sessions
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "S-001.md").write_text(
            "---\nstatus: running\n---\n# no id\n", encoding="utf-8"
        )
        sessions = list_sessions(paths)
        assert sessions == []

    def test_list_sessions_skips_empty_frontmatter(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        paths = project_paths(root)
        sessions_dir = paths.sessions
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "S-001.md").write_text("no frontmatter\n", encoding="utf-8")
        sessions = list_sessions(paths)
        assert sessions == []


class TestFindSessionEdgeCases:
    def test_find_invalid_id_raises(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        with pytest.raises(ValueError, match="invalid session id"):
            find_session(project_paths(root), "bad-id")

    def test_find_missing_session_raises(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        with pytest.raises(ValueError, match="not found"):
            find_session(project_paths(root), "S-999")


class TestDeleteSessionEdgeCases:
    def test_delete_missing_session_is_noop(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        delete_session(project_paths(root), "S-001")  # should not raise

    def test_delete_invalid_id_raises(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        with pytest.raises(ValueError, match="invalid session id"):
            delete_session(project_paths(root), "not-valid")

    def test_delete_existing_session(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        s = create_session(root, provider="codex", goal="g")
        paths = project_paths(root)
        delete_session(paths, s.id)
        with pytest.raises(ValueError, match="not found"):
            find_session(paths, s.id)

    def test_delete_existing_session_removes_transcript_and_syncs_registry(
        self, tmp_path: Path
    ) -> None:
        root = init_repo(tmp_path)
        s = create_session(root, provider="codex", goal="g")
        paths = project_paths(root)
        transcript = paths.sessions / f"{s.id}.transcript.jsonl"
        transcript.write_text('{"role":"assistant","text":"hi","ts":""}\n', encoding="utf-8")
        finish_session(
            root, s.id, status="succeeded", transcript_path=str(transcript.relative_to(root))
        )

        delete_session(paths, s.id)

        assert not transcript.exists()
        reg = load_registry()
        assert reg[0].session_count == 0
        assert reg[0].last_session == ""

    def test_delete_ignores_transcript_path_outside_sessions(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        outside = tmp_path / "outside.jsonl"
        outside.write_text("keep\n", encoding="utf-8")
        s = create_session(root, provider="codex", goal="g")
        paths = project_paths(root)
        finish_session(
            root,
            s.id,
            status="succeeded",
            transcript_path=f"../{outside.name}",
        )

        delete_session(paths, s.id)

        assert outside.exists()
        assert not (paths.sessions / f"{s.id}.md").exists()

    def test_finish_session_refreshes_memory(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        s = create_session(root, provider="codex", goal="g")

        finish_session(root, s.id, status="succeeded", summary="fresh summary")

        memory = (root / "loghop.md").read_text(encoding="utf-8")
        assert "## Latest Session" in memory
        assert "fresh summary" in memory

    def test_delete_session_refreshes_memory(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        s = create_session(root, provider="codex", goal="g")
        paths = project_paths(root)
        finish_session(root, s.id, status="succeeded", summary="stale summary")

        delete_session(paths, s.id)

        memory = (root / "loghop.md").read_text(encoding="utf-8")
        assert "stale summary" not in memory
        assert recent_timeline_events(paths) == []
        assert "## Latest Session" not in memory


class TestJsonFrontmatter:
    def test_parses_json_frontmatter(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        paths = project_paths(root)
        sessions_dir = paths.sessions
        sessions_dir.mkdir(parents=True, exist_ok=True)
        import json

        fm = json.dumps({"id": "S-001", "status": "succeeded", "provider": "codex"})
        (sessions_dir / "S-001.md").write_text(f"---\n{fm}\n---\n# Session\n", encoding="utf-8")
        sessions = list_sessions(paths)
        assert len(sessions) == 1
        assert sessions[0].status == "succeeded"

    def test_skips_invalid_json_frontmatter(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        paths = project_paths(root)
        sessions_dir = paths.sessions
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "S-001.md").write_text(
            "---\n{invalid json\n---\n# Session\n", encoding="utf-8"
        )
        sessions = list_sessions(paths)
        assert sessions == []

    def test_skips_json_array_frontmatter(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        paths = project_paths(root)
        sessions_dir = paths.sessions
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "S-001.md").write_text("---\n[1, 2, 3]\n---\n# Session\n", encoding="utf-8")
        sessions = list_sessions(paths)
        assert sessions == []


@pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
def test_create_session_rejects_symlinked_loghop_without_creating_target_sessions(
    tmp_path: Path,
) -> None:
    root = init_repo(tmp_path)
    paths = project_paths(root)
    escape = tmp_path / "escape"
    escape.mkdir()
    shutil.rmtree(paths.dot)
    paths.dot.symlink_to(escape, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinked path component"):
        create_session(root, provider="codex", goal="g")

    assert not (escape / "sessions").exists()


def test_latest_useful_session_skips_non_success_and_empty(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    paths = project_paths(root)
    s1 = create_session(root, provider="codex", goal="g1")
    finish_session(root, s1.id, status="succeeded", summary="useful")
    s2 = create_session(root, provider="codex", goal="g2")
    finish_session(root, s2.id, status="ended", turns_captured=0)
    s3 = create_session(root, provider="codex", goal="g3")
    s4 = create_session(root, provider="claude", goal="g4")
    finish_session(root, s4.id, status="interrupted", summary="partial")

    latest = latest_useful_session(paths)

    assert latest is not None
    assert latest.id == s1.id
    del s3


def test_latest_useful_session_skips_auth_failure_summary(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    paths = project_paths(root)
    useful = create_session(root, provider="codex", goal="g1")
    finish_session(root, useful.id, status="succeeded", summary="useful")
    failed_auth = create_session(root, provider="claude", goal="g2")
    finish_session(
        root,
        failed_auth.id,
        status="succeeded",
        summary="Not logged in · Please run /login",
    )

    latest = latest_useful_session(paths)

    assert latest is not None
    assert latest.id == useful.id


def test_recent_timeline_falls_back_to_legacy_sessions(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    paths = project_paths(root)
    useful = create_session(root, provider="codex", goal="g1")
    finish_session(root, useful.id, status="succeeded", summary="legacy summary")
    paths.timeline.unlink()

    events = recent_timeline_events(paths)

    assert events
    assert events[-1]["session_id"] == useful.id
    assert events[-1]["summary"] == "legacy summary"


def test_current_files_changed_respects_repo_state(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    changed = root / "changed.txt"
    changed.write_text("hello\n", encoding="utf-8")

    files = current_files_changed(root)

    assert "changed.txt" in files
