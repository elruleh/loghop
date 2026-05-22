from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path

from conftest import init_repo

from loghop.store import project_paths
from loghop.store._handoff import create_handoff
from loghop.store._registry import load_registry, touch_project
from loghop.store._session import create_session, finish_session

CliRunner = Callable[..., tuple[int, str, str]]


class TestCountersAndGoal:
    def test_session_count_increments(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        for _ in range(3):
            session = create_session(root, provider="claude", goal="g")
            finish_session(root, session.id, status="succeeded", returncode=0)

        entry = next(p for p in load_registry() if p.path == str(root.resolve()))
        assert entry.session_count == 3
        assert entry.last_session == "S-003"

    def test_handoff_count_increments(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        for _ in range(2):
            create_handoff(root, "claude", "goal")

        entry = next(p for p in load_registry() if p.path == str(root.resolve()))
        assert entry.handoff_count == 2

    def test_goal_syncs_after_config_change(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        touch_project(root)
        entry = next(p for p in load_registry() if p.path == str(root.resolve()))
        assert entry.goal == ""

        paths = project_paths(root)
        from loghop.store import load_config, save_config

        config = load_config(paths)
        config = dataclasses.replace(config, goal="ship it")
        save_config(paths, config)
        touch_project(root)
        entry = next(p for p in load_registry() if p.path == str(root.resolve()))
        assert entry.goal == "ship it"


class TestAutoRegister:
    def test_touch_project_registers_unknown_project(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        # Simulate old install: wipe the registry so the project isn't tracked.
        from loghop.store._registry import save_registry

        save_registry([])
        assert load_registry() == []

        session = create_session(root, provider="claude", goal="g")
        finish_session(root, session.id, status="succeeded", returncode=0)

        registry = load_registry()
        assert len(registry) == 1
        assert registry[0].path == str(root.resolve())
        assert registry[0].session_count == 1

    def test_touch_project_ignores_non_loghop_directory(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        touch_project(plain)
        assert load_registry() == []


class TestProjectsShow:
    def test_show_by_name(self, cli: CliRunner, tmp_path: Path) -> None:
        root = init_repo(tmp_path, name="alpha")
        # Give it a session + handoff so counts appear.
        create_handoff(root, "claude", "goal alpha")
        s = create_session(root, provider="claude", goal="goal alpha")
        finish_session(root, s.id, status="succeeded", returncode=0, summary="done")

        code, stdout, _ = cli(["projects", "show", "alpha"], cwd=tmp_path)
        assert code == 0
        assert "alpha" in stdout
        assert "S-001" in stdout
        assert "recent sessions" in stdout

    def test_show_unknown_errors(self, cli: CliRunner, tmp_path: Path) -> None:
        code, _, stderr = cli(["projects", "show", "nope-missing"], cwd=tmp_path)
        assert code != 0
        assert "no registered project" in stderr.lower()


class TestConcurrentRegistryUpdates:
    """The global registry at ~/.loghop/projects.toml is shared by every
    parallel `loghop` invocation. The `_registry_lock` must serialize
    read-modify-write cycles so concurrent updates don't lose entries."""

    def test_parallel_register_does_not_lose_entries(self, tmp_path: Path) -> None:
        import threading

        from loghop.store._registry import register_project

        # Create N independent loghop projects.
        roots = [init_repo(tmp_path, name=f"p{i}") for i in range(8)]

        # Wipe and register them concurrently.
        from loghop.store._registry import save_registry

        save_registry([])

        errors: list[BaseException] = []

        def _register(r: Path) -> None:
            try:
                register_project(r, goal=f"goal-{r.name}")
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=_register, args=(r,)) for r in roots]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors, f"register_project raised in parallel: {errors!r}"
        registered = {p.path for p in load_registry()}
        for r in roots:
            assert str(r.resolve()) in registered, (
                f"lost {r} from registry under concurrent register"
            )

    def test_parallel_unregister_does_not_corrupt_registry(self, tmp_path: Path) -> None:
        import threading

        from loghop.store._registry import register_project, unregister_project

        roots = [init_repo(tmp_path, name=f"q{i}") for i in range(8)]
        for r in roots:
            register_project(r, goal="g")

        # Half the threads unregister, half re-register. End state must be coherent
        # (no half-written/exception-raising registry, no duplicate entries).
        def _flap(r: Path) -> None:
            unregister_project(r)
            register_project(r, goal="g2")

        threads = [threading.Thread(target=_flap, args=(r,)) for r in roots]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        registry = load_registry()
        paths = [p.path for p in registry]
        assert len(paths) == len(set(paths)), f"duplicates after concurrent flap: {paths}"
        for r in roots:
            assert str(r.resolve()) in paths


class TestGlobalFlag:
    def test_global_forces_gallery_inside_project(
        self, cli: CliRunner, initialized_repo: Path
    ) -> None:
        # Register a second project so the gallery has >1 entry.
        other = init_repo(initialized_repo.parent, name="other")
        cli(["goal", "inside"], cwd=initialized_repo)

        code, stdout, _ = cli(["--global"], cwd=initialized_repo)
        assert code == 0
        assert "loghop projects" in stdout or "project(s) registered" in stdout
        # `other` name should appear in the gallery.
        assert other.name in stdout
