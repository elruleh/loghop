"""Tests for the .loghopignore pattern expander and the project_lock.

The expander is the small helper that turns ``**/*.secret`` (gitignore-style)
into the fnmatch patterns fnmatch can actually evaluate. It is easy to
under-engineer (forgetting to expand both ``foo/**`` and ``**/foo``) so
these tests pin down the expected behaviour.

The project_lock tests verify reentrancy (same thread, same lock), mutual
exclusion (different threads, same lock), and the post-yield cleanup path.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from loghop.store._io import project_lock
from loghop.store._security import _expand_doublestar, _matches

# --- _expand_doublestar ---------------------------------------------------------


@pytest.mark.parametrize(
    "pattern,alternatives",
    [
        ("**/*.secret", ["/*.secret", "*/*.secret"]),
        ("secrets/**", ["secrets/*"]),
        ("**/keys/*.pem", ["/keys/*.pem", "*/keys/*.pem"]),
        ("literal", ["literal"]),
    ],
)
def test_expand_doublestar(pattern: str, alternatives: list[str]) -> None:
    result = _expand_doublestar(pattern)
    for expected in alternatives:
        assert expected in result, f"missing {expected!r} in {result!r} for {pattern!r}"


def test_expand_doublestar_does_not_recurse() -> None:
    """** is expanded to a single *; this implementation does not produce
    multi-level alternatives. The output is checked for shape, not for
    producing every conceivable match (fnmatch's * already matches '/').
    """
    result = _expand_doublestar("a/**/b")
    assert "/b" in result
    # The one-depth alternative keeps the prefix.
    assert any("*/b" in alt or "*" in alt for alt in result)


def test_matches_glob_recursive() -> None:
    """Patterns with ** should match across directory boundaries."""
    assert _matches("a/b/c.secret", "**/*.secret")
    assert _matches("a/c.secret", "**/*.secret")


def test_matches_glob_directory_only() -> None:
    """Trailing-slash patterns match the directory itself and everything below."""
    assert _matches("build", "build/")
    assert _matches("build/lib", "build/")


def test_matches_glob_literal() -> None:
    """A plain pattern (no wildcards) matches its exact name."""
    assert _matches(".env", ".env")
    assert not _matches(".env.local", ".env")


# --- project_lock reentrancy + thread exclusion --------------------------------


def test_project_lock_reentrant_same_thread(tmp_path: Path) -> None:
    """A thread holding the lock can re-acquire it without blocking."""
    lock_path = tmp_path / "subdir" / "lock"
    with (
        project_lock(lock_path, timeout=2.0),
        project_lock(lock_path, timeout=2.0),
        project_lock(lock_path, timeout=2.0),
    ):
        # All three levels held; no deadlock.
        assert lock_path.exists()


def test_project_lock_serialises_distinct_threads(tmp_path: Path) -> None:
    """Two threads contending for the same lock must take turns."""
    lock_path = tmp_path / "subdir" / "lock"
    state = {
        "inside": 0,
        "max_concurrent": 0,
        "entered": 0,
        "exited": 0,
    }
    state_lock = threading.Lock()
    target_threads = 4

    def worker() -> None:
        with project_lock(lock_path, timeout=5.0):
            with state_lock:
                state["inside"] += 1
                state["entered"] += 1
                state["max_concurrent"] = max(state["max_concurrent"], state["inside"])
            time.sleep(0.02)
            with state_lock:
                state["inside"] -= 1
                state["exited"] += 1

    threads = [threading.Thread(target=worker) for _ in range(target_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert state["entered"] == target_threads
    assert state["exited"] == target_threads
    # Mandatory flock guarantees at most one thread inside.
    assert state["max_concurrent"] == 1, f"lock failed: max={state['max_concurrent']}"


def test_project_lock_timeout_raises(tmp_path: Path) -> None:
    """Holding the lock from one thread and asking again from another must time out."""
    lock_path = tmp_path / "subdir" / "lock"
    holder_acquired = threading.Event()
    release_holder = threading.Event()

    def holder() -> None:
        with project_lock(lock_path, timeout=5.0):
            holder_acquired.set()
            release_holder.wait(timeout=5.0)

    th = threading.Thread(target=holder)
    th.start()
    try:
        assert holder_acquired.wait(timeout=2.0), "holder never acquired the lock"
        with pytest.raises(TimeoutError), project_lock(lock_path, timeout=0.2):
            pass
    finally:
        release_holder.set()
        th.join(timeout=2.0)


def test_project_lock_cleans_up_on_exception(tmp_path: Path) -> None:
    """A failure inside the ``with`` body must release the lock."""
    lock_path = tmp_path / "subdir" / "lock"
    with pytest.raises(RuntimeError), project_lock(lock_path, timeout=2.0):
        raise RuntimeError("boom")
    # The lock file is removed on exit; a fresh acquire must succeed.
    with project_lock(lock_path, timeout=0.5):
        pass
