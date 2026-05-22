from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from loghop.store import init_project
from loghop.store._handoff import create_handoff
from loghop.store._models import RegistryEntry
from loghop.store._registry import (
    cleanup_missing,
    delete_project_data,
    load_registry,
    register_project,
    save_registry,
    sync_project,
    touch_project,
    unregister_project,
)
from loghop.store._session import create_session, finish_session


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


class TestLoadSaveRegistry:
    def test_empty_registry(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        assert load_registry() == []

    def test_roundtrip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        entries = [
            RegistryEntry(
                name="proj1",
                path="/tmp/proj1",
                registered="2025-01-01T00:00:00Z",
                last_used="2025-01-02T00:00:00Z",
                goal="ship it",
                session_count=5,
                handoff_count=3,
            )
        ]
        save_registry(entries)
        loaded = load_registry()
        assert len(loaded) == 1
        assert loaded[0].name == "proj1"
        assert loaded[0].goal == "ship it"
        assert loaded[0].session_count == 5

    def test_corrupt_registry_is_backed_up_before_returning_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        registry = Path.home() / ".loghop" / "projects.toml"
        registry.parent.mkdir(parents=True)
        registry.write_text("[[project]\npath = ", encoding="utf-8")

        assert load_registry() == []

        backups = list(registry.parent.glob("projects.toml.corrupt-*"))
        assert backups
        assert backups[0].read_text(encoding="utf-8") == "[[project]\npath = "


class TestRegisterProject:
    def test_registers_new(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        root = _init_repo(tmp_path)
        register_project(root, goal="test goal")
        reg = load_registry()
        assert len(reg) == 1
        assert reg[0].name == "repo"
        assert reg[0].goal == "test goal"

    def test_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        root = _init_repo(tmp_path)
        register_project(root, goal="first")
        register_project(root, goal="second")
        reg = load_registry()
        assert len(reg) == 1
        assert reg[0].goal == "second"

    def test_multiple_projects(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        root1 = tmp_path / "repo1"
        root1.mkdir()
        _git_init_with_commit(root1)
        init_project(root1)

        root2 = tmp_path / "repo2"
        root2.mkdir()
        _git_init_with_commit(root2)
        init_project(root2)

        register_project(root1, goal="proj 1")
        register_project(root2, goal="proj 2")
        reg = load_registry()
        assert len(reg) == 2

    def test_reregister_preserves_session_and_handoff_metadata(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        root = _init_repo(tmp_path)
        create_handoff(root, "codex", "ship it next")
        session = create_session(root, provider="claude", goal="ship it")
        finish_session(root, session.id, status="succeeded")
        unregister_project(root)

        register_project(root)
        reg = load_registry()
        assert len(reg) == 1
        assert reg[0].session_count == 1
        assert reg[0].handoff_count == 1
        assert reg[0].last_session == session.id


class TestUnregisterProject:
    def test_removes_project(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        root = _init_repo(tmp_path)
        register_project(root)
        assert len(load_registry()) == 1
        unregister_project(root)
        assert len(load_registry()) == 0

    def test_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        root = _init_repo(tmp_path)
        unregister_project(root)
        assert len(load_registry()) == 0


class TestTouchProject:
    def test_touch_registers_if_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        root = _init_repo(tmp_path)
        touch_project(root, bump_session=True)
        reg = load_registry()
        assert len(reg) == 1
        assert reg[0].session_count == 1

    def test_bump_session(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        root = _init_repo(tmp_path)
        register_project(root)
        touch_project(root, bump_session=True)
        reg = load_registry()
        assert reg[0].session_count == 1
        touch_project(root, bump_session=True)
        reg = load_registry()
        assert reg[0].session_count == 2

    def test_bump_handoff(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        root = _init_repo(tmp_path)
        register_project(root)
        touch_project(root, bump_handoff=True)
        reg = load_registry()
        assert reg[0].handoff_count == 1

    def test_last_session(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        root = _init_repo(tmp_path)
        register_project(root)
        touch_project(root, last_session="S-005")
        reg = load_registry()
        assert reg[0].last_session == "S-005"

    def test_updates_goal_from_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        root = _init_repo(tmp_path)
        import dataclasses

        from loghop.store import load_config, project_paths, save_config

        paths = project_paths(root)
        config = load_config(paths)
        save_config(paths, dataclasses.replace(config, goal="new goal"))
        register_project(root)
        touch_project(root)
        reg = load_registry()
        assert reg[0].goal == "new goal"

    def test_sync_project_rebuilds_counts_from_disk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        root = _init_repo(tmp_path)
        session = create_session(root, provider="codex", goal="g")
        finish_session(root, session.id, status="succeeded")
        save_registry(
            [
                RegistryEntry(
                    name=root.name,
                    path=str(root.resolve()),
                    registered="2025-01-01T00:00:00Z",
                    last_used="2025-01-01T00:00:00Z",
                    goal="bad",
                    last_session="S-999",
                    session_count=99,
                    handoff_count=42,
                )
            ]
        )

        sync_project(root)
        reg = load_registry()
        assert reg[0].session_count == 1
        assert reg[0].handoff_count == 0
        assert reg[0].last_session == session.id


class TestCleanupMissing:
    def test_removes_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        root = _init_repo(tmp_path)
        register_project(root)
        entries = [
            RegistryEntry(
                name="ghost",
                path="/nonexistent/path",
                registered="2025-01-01T00:00:00Z",
                last_used="2025-01-01T00:00:00Z",
            )
        ]
        save_registry(load_registry() + entries)
        removed = cleanup_missing()
        assert removed == 1
        assert len(load_registry()) == 1

    def test_all_valid(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        root = _init_repo(tmp_path)
        register_project(root)
        removed = cleanup_missing()
        assert removed == 0


class TestDeleteProjectData:
    def test_deletes_loghop_dir(self, tmp_path: Path) -> None:
        root = _init_repo(tmp_path)
        assert (root / ".loghop").exists()
        assert delete_project_data(root) is True
        assert not (root / ".loghop").exists()

    def test_returns_false_if_not_initialized(self, tmp_path: Path) -> None:
        root = tmp_path / "empty"
        root.mkdir()
        assert delete_project_data(root) is False

    @pytest.mark.skipif(not hasattr(Path, "symlink_to"), reason="symlink unavailable")
    def test_refuses_symlinked_loghop_dir(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        target = tmp_path / "target"
        target.mkdir()
        (target / "config.toml").write_text("", encoding="utf-8")
        (root / ".loghop").symlink_to(target, target_is_directory=True)

        with pytest.raises(ValueError, match="symlinked"):
            delete_project_data(root)

        assert target.exists()
