from __future__ import annotations

import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from loghop.store import init_project, list_handoffs, project_paths
from loghop.store._handoff import (
    _max_existing_handoff_number,
    _prune_old_handoffs,
    create_handoff,
    create_resume_handoff,
    find_handoff,
    update_handoff_status,
)
from loghop.store._models import SessionMeta


def _git_init_with_commit(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=root, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)
    (root / "a.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True, capture_output=True)


def _init_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git_init_with_commit(root)
    init_project(root)
    return root


class TestMaxExistingHandoffNumber:
    def test_empty_dir(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        paths = project_paths(root)
        assert _max_existing_handoff_number(paths) == 0

    def test_finds_existing(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        paths = project_paths(root)
        (paths.handoffs / "H-005.md").write_text("---\nid: H-005\n---\n", encoding="utf-8")
        (paths.handoffs / "H-012.md").write_text("---\nid: H-012\n---\n", encoding="utf-8")
        assert _max_existing_handoff_number(paths) == 12


class TestPruneOldHandoffs:
    def test_prunes_beyond_limit(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        paths = project_paths(root)
        for i in range(1, 6):
            (paths.handoffs / f"H-{i:03d}.md").write_text(
                f"---\nid: H-{i:03d}\n---\n", encoding="utf-8"
            )
        _prune_old_handoffs(paths, keep=3)
        remaining = list(paths.handoffs.glob("H-*.md"))
        assert len(remaining) == 3

    def test_no_prune_when_under_limit(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        paths = project_paths(root)
        for i in range(1, 3):
            (paths.handoffs / f"H-{i:03d}.md").write_text(
                f"---\nid: H-{i:03d}\n---\n", encoding="utf-8"
            )
        _prune_old_handoffs(paths, keep=5)
        remaining = list(paths.handoffs.glob("H-*.md"))
        assert len(remaining) == 2


class TestCreateHandoff:
    def test_creates_handoff_file(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        record = create_handoff(root, "codex", "ship it")
        assert record.id == "H-001"
        assert record.provider == "codex"
        assert record.goal == "ship it"
        assert record.md_path is not None
        assert record.md_path.exists()

    def test_sequential_ids(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        r1 = create_handoff(root, "codex", "first")
        r2 = create_handoff(root, "claude", "second")
        assert r1.id == "H-001"
        assert r2.id == "H-002"

    def test_handoff_frontmatter_has_status(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        create_handoff(root, "codex", "test")
        paths = project_paths(root)
        handoffs = list_handoffs(paths)
        assert handoffs[0].status == "built"

    def test_prunes_under_project_lock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import loghop.store._handoff as handoff_store

        root = _init_repo(tmp_path)
        state = {"locked": False, "saw_locked_prune": False}

        @contextmanager
        def fake_lock(*_args: object, **_kwargs: object) -> Any:
            state["locked"] = True
            try:
                yield
            finally:
                state["locked"] = False

        def fake_prune(*_args: object, **_kwargs: object) -> None:
            state["saw_locked_prune"] = state["locked"]

        monkeypatch.setattr(handoff_store, "project_lock", fake_lock)
        monkeypatch.setattr(handoff_store, "_prune_old_handoffs", fake_prune)

        create_handoff(root, "codex", "ship it")

        assert state["saw_locked_prune"] is True

    def test_prunes_to_limit_after_create(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        paths = project_paths(root)
        for i in range(1, 21):
            (paths.handoffs / f"H-{i:03d}.md").write_text(
                f"---\nid: H-{i:03d}\nprovider: codex\ngoal: g{i}\nts: now\n---\n",
                encoding="utf-8",
            )

        record = create_handoff(root, "codex", "next")

        remaining = sorted(path.name for path in paths.handoffs.glob("H-*.md"))
        assert record.id == "H-021"
        assert len(remaining) == 20
        assert "H-001.md" not in remaining
        assert "H-021.md" in remaining


class TestFindHandoff:
    def test_finds_existing(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        create_handoff(root, "codex", "test")
        paths = project_paths(root)
        found = find_handoff(paths, "H-001")
        assert found.id == "H-001"
        assert found.provider == "codex"

    def test_invalid_id_raises(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        paths = project_paths(root)
        with pytest.raises(ValueError, match="invalid handoff id"):
            find_handoff(paths, "bad-id")

    def test_missing_raises(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        paths = project_paths(root)
        with pytest.raises(ValueError, match="not found"):
            find_handoff(paths, "H-999")


class TestListHandoffs:
    def test_empty(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        paths = project_paths(root)
        assert list_handoffs(paths) == []

    def test_lists_all(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        create_handoff(root, "codex", "a")
        create_handoff(root, "claude", "b")
        paths = project_paths(root)
        all_h = list_handoffs(paths)
        assert len(all_h) == 2

    def test_filter_by_provider(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        create_handoff(root, "codex", "a")
        create_handoff(root, "claude", "b")
        paths = project_paths(root)
        codex_h = list_handoffs(paths, provider="codex")
        assert len(codex_h) == 1
        assert codex_h[0].provider == "codex"

    def test_sorted_newest_first(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        create_handoff(root, "codex", "first")
        create_handoff(root, "codex", "second")
        paths = project_paths(root)
        all_h = list_handoffs(paths)
        assert all_h[0].id == "H-002"
        assert all_h[1].id == "H-001"


class TestUpdateHandoffStatus:
    def test_updates_status(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        create_handoff(root, "codex", "test")
        updated = update_handoff_status(root, "H-001", status="launched")
        assert updated.status == "launched"

    def test_sets_returncode(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        create_handoff(root, "codex", "test")
        updated = update_handoff_status(root, "H-001", status="succeeded", returncode=0)
        assert updated.status == "succeeded"
        assert updated.returncode == "0"

    def test_persists_to_disk(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        create_handoff(root, "codex", "test")
        update_handoff_status(root, "H-001", status="failed", returncode=1)
        paths = project_paths(root)
        found = find_handoff(paths, "H-001")
        assert found.status == "failed"


class TestCreateResumeHandoff:
    def test_without_previous_session(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        record = create_resume_handoff(root, "codex", "resume goal", previous_session=None)
        assert record.id == "H-001"
        assert record.goal == "resume goal"
        assert record.md_path is not None
        assert record.md_path.exists()

    def test_with_previous_session(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        prev = SessionMeta(
            id="S-001",
            provider="codex",
            goal="first",
            status="succeeded",
            summary="did stuff",
            decisions=["chose X"],
            todos_pending=["finish Y"],
            todos_done=["did Z"],
        )
        record = create_resume_handoff(root, "claude", "next goal", previous_session=prev)
        assert record.id == "H-001"
        assert record.provider == "claude"
        assert record.md_path is not None
        content = record.md_path.read_text(encoding="utf-8")
        assert "Previous Session" in content
        assert "S-001" in content
        assert "chose X" in content

    def test_sequential_after_handoff(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        create_handoff(root, "codex", "first")
        record = create_resume_handoff(root, "codex", "second", previous_session=None)
        assert record.id == "H-002"

    def test_prunes_under_project_lock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import loghop.store._handoff as handoff_store

        root = _init_repo(tmp_path)
        state = {"locked": False, "saw_locked_prune": False}

        @contextmanager
        def fake_lock(*_args: object, **_kwargs: object) -> Any:
            state["locked"] = True
            try:
                yield
            finally:
                state["locked"] = False

        def fake_prune(*_args: object, **_kwargs: object) -> None:
            state["saw_locked_prune"] = state["locked"]

        monkeypatch.setattr(handoff_store, "project_lock", fake_lock)
        monkeypatch.setattr(handoff_store, "_prune_old_handoffs", fake_prune)

        create_resume_handoff(root, "codex", "resume goal", previous_session=None)

        assert state["saw_locked_prune"] is True
