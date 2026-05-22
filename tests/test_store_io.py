from __future__ import annotations

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from loghop.errors import LoghopError
from loghop.redact import redact_text
from loghop.store import (
    create_handoff,
    find_project_root,
    init_project,
    load_config,
    project_paths,
    save_config,
)
from loghop.store._io import (
    atomic_write_private_text,
    atomic_write_text,
    safe_read_text,
)
from loghop.store._render import render_memory


def _git_init_with_commit(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=root, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)
    (root / "a.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True, capture_output=True)


class TestAtomicWriteText:
    def test_writes_file(self, tmp_path: Path) -> None:
        path = tmp_path / "out.txt"
        atomic_write_text(path, "hello\n")
        assert path.read_text(encoding="utf-8") == "hello\n"

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        path = tmp_path / "out.txt"
        atomic_write_text(path, "first")
        atomic_write_text(path, "second")
        assert path.read_text(encoding="utf-8") == "second"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "dir" / "file.txt"
        atomic_write_text(path, "nested")
        assert path.exists()

    @pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
    def test_private_permissions(self, tmp_path: Path) -> None:
        path = tmp_path / "perm.txt"
        atomic_write_private_text(path, "data")
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600

    @pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
    def test_safe_read_rejects_symlink(self, tmp_path: Path) -> None:
        target = tmp_path / "target.txt"
        target.write_text("secret\n", encoding="utf-8")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        with pytest.raises(OSError, match="symbol|symlink"):
            from loghop.store._io import safe_read_text

            safe_read_text(link)


class TestEnsureDirectoryRejectsSymlinks:
    """`_ensure_directory` must refuse symlinks at any level of the path,
    not just the leaf — closing the TOCTOU race in `mkdir(parents=True)`."""

    @pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
    def test_target_is_symlink_to_dir(self, tmp_path: Path) -> None:
        from loghop.store._io import _ensure_directory

        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real, target_is_directory=True)
        with pytest.raises(ValueError, match="symlinked"):
            _ensure_directory(link)

    @pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
    def test_intermediate_parent_is_symlink(self, tmp_path: Path) -> None:
        from loghop.store._io import _ensure_directory

        # Layout: tmp/real_parent/  (real)
        #         tmp/link_parent  -> tmp/real_parent  (symlink)
        # Calling _ensure_directory(tmp/link_parent/child) must refuse
        # because an ancestor is a symlink.
        real_parent = tmp_path / "real_parent"
        real_parent.mkdir()
        link_parent = tmp_path / "link_parent"
        link_parent.symlink_to(real_parent, target_is_directory=True)
        with pytest.raises(ValueError, match="symlinked"):
            _ensure_directory(link_parent / "child")

    @pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
    def test_target_is_symlink_to_file(self, tmp_path: Path) -> None:
        from loghop.store._io import _ensure_directory

        target = tmp_path / "afile"
        target.write_text("x")
        link = tmp_path / "linkfile"
        link.symlink_to(target)
        with pytest.raises(ValueError, match="symlinked"):
            _ensure_directory(link)

    def test_creates_missing_chain_normally(self, tmp_path: Path) -> None:
        from loghop.store._io import _ensure_directory

        target = tmp_path / "a" / "b" / "c"
        result = _ensure_directory(target)
        assert result.is_dir()
        # Each segment created with the right mode (best-effort on POSIX).
        if os.name != "nt":
            assert oct((tmp_path / "a").stat().st_mode & 0o777) == "0o700"

    def test_idempotent_on_existing_real_dir(self, tmp_path: Path) -> None:
        from loghop.store._io import _ensure_directory

        target = tmp_path / "existing"
        target.mkdir()
        # Calling twice must not raise.
        _ensure_directory(target)
        _ensure_directory(target)

    def test_rejects_target_that_is_a_regular_file(self, tmp_path: Path) -> None:
        from loghop.store._io import _ensure_directory

        f = tmp_path / "is_a_file"
        f.write_text("x")
        with pytest.raises(ValueError, match="expected directory"):
            _ensure_directory(f)


class TestFindProjectRoot:
    def test_finds_root(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        init_project(tmp_path)
        sub = tmp_path / "src" / "pkg"
        sub.mkdir(parents=True)
        assert find_project_root(sub) == tmp_path

    def test_returns_none_without_loghop(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        assert find_project_root(tmp_path) is None

    def test_finds_from_root_itself(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        init_project(tmp_path)
        assert find_project_root(tmp_path) == tmp_path

    def test_does_not_cross_nested_git_root(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        init_project(tmp_path)
        nested = tmp_path / "nested"
        nested.mkdir()
        _git_init_with_commit(nested)
        assert find_project_root(nested) is None

    @pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
    def test_returns_none_when_sessions_dir_is_symlink(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        init_project(tmp_path)
        paths = project_paths(tmp_path)
        target = tmp_path / "elsewhere"
        target.mkdir()
        paths.sessions.rmdir()
        paths.sessions.symlink_to(target, target_is_directory=True)
        assert find_project_root(tmp_path) is None


class TestConfigRoundTrip:
    def test_defaults_written_on_init(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        init_project(tmp_path)
        config = load_config(project_paths(tmp_path))
        assert config.project_name == tmp_path.name
        assert config.goal == ""
        assert config.handoff_counter == 0
        assert not hasattr(config, "providers")

    def test_roundtrip_preserves_goal_and_counter(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        init_project(tmp_path)
        paths = project_paths(tmp_path)
        config = load_config(paths)
        import dataclasses

        config = dataclasses.replace(config, goal="ship v1")
        config = dataclasses.replace(config, handoff_counter=7)
        save_config(paths, config)
        reloaded = load_config(paths)
        assert reloaded.goal == "ship v1"
        assert reloaded.handoff_counter == 7

    def test_corrupt_config_is_user_error(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        init_project(tmp_path)
        paths = project_paths(tmp_path)
        paths.config.write_text("not = [valid\n", encoding="utf-8")
        with pytest.raises(LoghopError, match="invalid config file"):
            load_config(paths)

    def test_concurrent_handoffs_get_distinct_ids(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        init_project(tmp_path)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda goal: create_handoff(tmp_path, "codex", goal).id,
                    ["one", "two"],
                )
            )
        assert sorted(results) == ["H-001", "H-002"]

    def test_handoff_counter_uses_existing_files(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        init_project(tmp_path)
        paths = project_paths(tmp_path)
        (paths.handoffs / "H-010.md").write_text(
            '---\n{"id": "H-010", "provider": "codex", "goal": "old", "ts": "x"}\n---\n',
            encoding="utf-8",
        )
        record = create_handoff(tmp_path, "codex", "next")
        assert record.id == "H-011"

    def test_handoff_frontmatter_round_trips_quotes(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        init_project(tmp_path)
        create_handoff(tmp_path, "codex", 'say "hello"')
        from loghop.store import list_handoffs

        handoffs = list_handoffs(project_paths(tmp_path))
        assert handoffs[0].goal == 'say "hello"'

    def test_memory_respects_loghopignore(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        init_project(tmp_path)
        (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-secret\n", encoding="utf-8")
        paths = project_paths(tmp_path)
        render_memory(paths, load_config(paths))
        memory = safe_read_text(paths.memory)
        assert ".env" not in memory


class _ListHandler:
    """Tiny in-memory log handler. The loghop logger has propagate=False so
    pytest's caplog (which injects on the root logger by default) can't see
    its records — attach a handler directly instead."""

    def __init__(self) -> None:
        import logging as _logging

        self.records: list[_logging.LogRecord] = []

        class _H(_logging.Handler):
            def emit(_self, record: _logging.LogRecord) -> None:
                self.records.append(record)

        self._handler = _H()

    def attach(self) -> None:
        from loghop.logging import get_logger

        get_logger().addHandler(self._handler)

    def detach(self) -> None:
        from loghop.logging import get_logger

        get_logger().removeHandler(self._handler)


class TestConfigVersionForwardCompat:
    """Audit fix #8: a config written by a newer loghop must load gracefully
    (preserving the version) and warn rather than silently drop unknown keys.
    """

    def test_higher_version_warns_but_loads(self, tmp_path: Path) -> None:
        import logging

        root = tmp_path / "repo"
        root.mkdir()
        _git_init_with_commit(root)
        init_project(root)
        paths = project_paths(root)

        # Manually write a config with a higher version + a future-only key.
        paths.config.write_text(
            "version = 99\n"
            'project_name = "repo"\n'
            'goal = "future goal"\n'
            "handoff_counter = 0\n"
            'unknown_future_key = "future"\n',
            encoding="utf-8",
        )

        cap = _ListHandler()
        cap.attach()
        try:
            from loghop.logging import get_logger

            get_logger().setLevel(logging.WARNING)
            cfg = load_config(paths)
        finally:
            cap.detach()

        assert cfg.version == 99
        assert cfg.goal == "future goal"
        messages = [rec.getMessage() for rec in cap.records]
        has_warning = any("schema is newer" in message for message in messages)
        assert has_warning, f"expected forward-compat warning, got: {messages}"

    def test_non_int_version_warns_and_uses_default(self, tmp_path: Path) -> None:
        import logging

        from loghop.store._constants import VERSION

        root = tmp_path / "repo"
        root.mkdir()
        _git_init_with_commit(root)
        init_project(root)
        paths = project_paths(root)
        paths.config.write_text(
            'version = "wrong"\nproject_name = "repo"\ngoal = ""\nhandoff_counter = 0\n',
            encoding="utf-8",
        )

        cap = _ListHandler()
        cap.attach()
        try:
            from loghop.logging import get_logger

            get_logger().setLevel(logging.WARNING)
            cfg = load_config(paths)
        finally:
            cap.detach()

        assert cfg.version == VERSION
        assert any("non-integer version" in rec.getMessage() for rec in cap.records)


class TestRedactText:
    def test_none_returns_empty(self) -> None:
        assert redact_text(None) == ""

    def test_empty_returns_empty(self) -> None:
        assert redact_text("") == ""

    def test_safe_text_unchanged(self) -> None:
        assert redact_text("just a normal string") == "just a normal string"


def test_flock_based_project_lock(tmp_path):
    import threading

    from loghop.store._io import project_lock

    lock_file = tmp_path / ".lock"
    # Reentrancy: same thread can nest locks without deadlock.
    with project_lock(lock_file), project_lock(lock_file, timeout=0.1):
        pass  # nested lock acquired successfully

    # Cross-thread contention: a second thread should timeout.
    acquired = threading.Event()
    release = threading.Event()
    error_seen: list[str] = []

    def _hold_lock() -> None:
        with project_lock(lock_file):
            acquired.set()
            release.wait(timeout=5)

    t = threading.Thread(target=_hold_lock, daemon=True)
    t.start()
    acquired.wait(timeout=2)
    try:
        with project_lock(lock_file, timeout=0.1):
            pass  # should NOT reach here
        error_seen.append("expected TimeoutError")
    except TimeoutError:
        pass  # expected
    finally:
        release.set()
        t.join(timeout=2)
    assert not error_seen, error_seen


class TestAtomicStreamErrorHandling:
    """Cover error paths in atomic_stream_to_file and project_lock."""

    def test_exception_during_write_cleans_up_tmp(self, tmp_path: Path) -> None:
        from loghop.store._io import atomic_stream_to_file

        target = tmp_path / "out.txt"
        with pytest.raises(RuntimeError), atomic_stream_to_file(target) as handle:
            handle.write("partial")
            raise RuntimeError("boom")
        # Temp file must be cleaned up
        assert not target.exists()
        tmp_files = list(tmp_path.glob(".*.tmp"))
        assert len(tmp_files) == 0

    def test_write_with_file_mode(self, tmp_path: Path) -> None:
        from loghop.store._io import atomic_write_text

        target = tmp_path / "mode.txt"
        atomic_write_text(target, "data", file_mode=0o640)
        assert target.read_text() == "data"

    def test_write_with_dir_mode(self, tmp_path: Path) -> None:
        from loghop.store._io import atomic_write_text

        subdir = tmp_path / "sub"
        target = subdir / "mode.txt"
        atomic_write_text(target, "data", dir_mode=0o700)
        assert target.read_text() == "data"

    def test_fsync_dir_nonexistent_does_not_raise(self, tmp_path: Path) -> None:
        from loghop.store._io import _fsync_dir

        # Should silently ignore missing directory
        _fsync_dir(tmp_path / "nonexistent")

    def test_safe_read_nonexistent_raises(self, tmp_path: Path) -> None:
        from loghop.store._io import safe_read_text

        with pytest.raises(OSError, match="No such file"):
            safe_read_text(tmp_path / "missing.txt")

    def test_ensure_directory_dot_path_works(self) -> None:
        from loghop.store._io import _ensure_directory

        # Path('.') has empty parts but absolute resolves to cwd
        result = _ensure_directory(Path("."))
        assert result.is_dir()

    def test_project_lock_basic(self, tmp_path: Path) -> None:
        from loghop.store._io import project_lock

        lock = tmp_path / ".lock"
        with project_lock(lock):
            assert lock.exists()

    def test_project_lock_timeout(self, tmp_path: Path) -> None:
        import threading

        import pytest

        from loghop.store._io import project_lock

        lock = tmp_path / ".lock"
        acquired = threading.Event()
        release = threading.Event()

        def _hold() -> None:
            with project_lock(lock):
                acquired.set()
                release.wait(timeout=5)

        t = threading.Thread(target=_hold, daemon=True)
        t.start()
        acquired.wait(timeout=2)
        try:
            with pytest.raises(TimeoutError), project_lock(lock, timeout=0.1):
                pass
        finally:
            release.set()
            t.join(timeout=2)


class TestAtomicStreamEdgeCases:
    """Cover remaining edge cases in store/_io.py for 85%+ coverage."""

    def test_fchmod_path(self, tmp_path: Path) -> None:
        """On Linux, os.fchmod is available — cover that branch."""
        from loghop.store._io import atomic_stream_to_file

        target = tmp_path / "fchmod.txt"
        with atomic_stream_to_file(target, file_mode=0o640) as handle:
            handle.write("test")
        assert target.read_text() == "test"

    def test_ensure_directory_concurrent_race(self, tmp_path: Path) -> None:
        """FileExistsError race in _ensure_directory is handled gracefully."""
        from loghop.store._io import _ensure_directory

        target = tmp_path / "concurrent"
        # First call creates it normally
        _ensure_directory(target)
        # Second call should be idempotent (already exists)
        _ensure_directory(target)

    def test_ensure_directory_creates_intermediate(self, tmp_path: Path) -> None:
        """Intermediate directories are created one by one."""
        from loghop.store._io import _ensure_directory

        deep = tmp_path / "a" / "b" / "c" / "d"
        result = _ensure_directory(deep)
        assert result.is_dir()
        # Verify each level was created
        assert (tmp_path / "a").is_dir()
        assert (tmp_path / "a" / "b").is_dir()

    def test_project_lock_contention(self, tmp_path: Path) -> None:
        """Cross-thread contention — second thread times out."""
        import threading

        import pytest

        from loghop.store._io import project_lock

        lock = tmp_path / ".lock"
        acquired = threading.Event()
        release = threading.Event()

        def _hold() -> None:
            with project_lock(lock):
                acquired.set()
                release.wait(timeout=5)

        t = threading.Thread(target=_hold, daemon=True)
        t.start()
        acquired.wait(timeout=2)
        try:
            with pytest.raises(TimeoutError), project_lock(lock, timeout=0.1):
                pass
        finally:
            release.set()
            t.join(timeout=2)

    def test_project_lock_releases_on_success(self, tmp_path: Path) -> None:
        """Lock is released after successful use."""
        from loghop.store._io import project_lock

        lock = tmp_path / ".lock"
        with project_lock(lock, timeout=0.5):
            pass
        # Should be able to acquire again immediately
        with project_lock(lock, timeout=0.5):
            pass

    def test_atomic_write_overwrites_with_content(self, tmp_path: Path) -> None:
        """Full round-trip: write → read → overwrite → read."""
        from loghop.store._io import atomic_write_text, safe_read_text

        target = tmp_path / "round.txt"
        atomic_write_text(target, "first")
        assert safe_read_text(target) == "first"
        atomic_write_text(target, "second")
        assert safe_read_text(target) == "second"

    def test_fsync_dir_on_real_dir(self, tmp_path: Path) -> None:
        """_fsync_dir on a real directory succeeds silently."""
        from loghop.store._io import _fsync_dir

        # Should not raise
        _fsync_dir(tmp_path)


class TestSafeReadTextFdLeak:
    """Cover the OSError path in safe_read_text where fd needs closing."""

    def test_fd_closed_on_fdopen_failure(self, tmp_path: Path) -> None:
        """If fdopen fails after opening fd, fd is properly closed."""
        import os
        from unittest.mock import patch

        from loghop.store._io import safe_read_text

        target = tmp_path / "test.txt"
        target.write_text("content")

        # Mock os.fdopen to raise OSError on first call
        original_fdopen = os.fdopen
        calls = [0]

        def mock_fdopen(fd, *args, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                raise OSError("mock fdopen failure")
            return original_fdopen(fd, *args, **kwargs)

        with patch("os.fdopen", side_effect=mock_fdopen):  # noqa: SIM117
            with pytest.raises(OSError, match="mock fdopen failure"):
                safe_read_text(target)


class TestEnsureDirectoryRace:
    """Cover FileExistsError race and symlink/file checks."""

    @pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
    def test_rejects_symlink_to_file(self, tmp_path: Path) -> None:
        from loghop.store._io import _ensure_directory

        target = tmp_path / "afile"
        target.write_text("x")
        link = tmp_path / "linkdir"
        link.symlink_to(target)
        with pytest.raises(ValueError, match="symlinked"):
            _ensure_directory(link)
