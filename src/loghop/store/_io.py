import os
import stat
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import IO, Any

from loghop.store._constants import DIR_MODE, FILE_MODE

# Thread-local reentrancy tracker for ``project_lock``.
# Key: (resolved lock path, thread id).  Value: nesting depth.
_lock_depth: dict[tuple[Path, int | None], int] = {}


def safe_read_text(path: Path) -> str:
    fd = _open_readonly(path)
    try:
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        with suppress(OSError):
            os.close(fd)
        raise


def _fsync_file(handle: Any) -> None:
    handle.flush()
    os.fsync(handle.fileno())


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def atomic_stream_to_file(
    path: Path,
    *,
    file_mode: int | None = None,
    dir_mode: int | None = None,
) -> Iterator[IO[str]]:
    parent = _ensure_directory(path.parent)
    if dir_mode is not None:
        with suppress(PermissionError):
            os.chmod(parent, dir_mode)
    fd, temp_name = tempfile.mkstemp(dir=str(parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        if file_mode is not None and hasattr(os, "fchmod"):
            with suppress(OSError):
                os.fchmod(fd, file_mode)
        elif file_mode is not None:
            with suppress(OSError):
                os.chmod(temp_name, file_mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yield handle
            _fsync_file(handle)
        os.replace(temp_name, path)
    except Exception:
        with suppress(FileNotFoundError):
            os.unlink(temp_name)
        raise
    if file_mode is not None:
        with suppress(OSError):
            os.chmod(path, file_mode)
    _fsync_dir(parent)


def atomic_write_text(
    path: Path,
    text: str,
    *,
    file_mode: int | None = None,
    dir_mode: int | None = None,
) -> None:
    with atomic_stream_to_file(path, file_mode=file_mode, dir_mode=dir_mode) as handle:
        handle.write(text)


def atomic_write_private_text(path: Path, text: str) -> None:
    atomic_write_text(path, text, file_mode=FILE_MODE, dir_mode=DIR_MODE)


@contextmanager
def project_lock(
    path: Path, *, timeout: float = 5.0, poll_interval: float = 0.05
) -> Iterator[None]:
    parent = _ensure_directory(path.parent)
    deadline = time.monotonic() + timeout

    if sys.platform == "win32":
        # Fallback for Windows — no reentrancy support.
        while True:
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, FILE_MODE)
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("project is busy; try again in a moment") from None
                time.sleep(poll_interval)
        try:
            with suppress(OSError):
                os.chmod(parent, DIR_MODE)
            with suppress(OSError):
                os.chmod(path, FILE_MODE)
            yield
        finally:
            with suppress(OSError):
                os.close(fd)
            with suppress(FileNotFoundError, PermissionError):
                os.unlink(path)
            _fsync_dir(parent)
        return

    import fcntl
    import threading

    # Reentrancy: if the current thread already holds this lock, just nest.
    lock_key = (path.resolve(), threading.current_thread().ident)
    counter = _lock_depth.get(lock_key, 0)
    if counter > 0:
        _lock_depth[lock_key] = counter + 1
        try:
            yield
        finally:
            _lock_depth[lock_key] -= 1
            if _lock_depth[lock_key] <= 0:
                _lock_depth.pop(lock_key, None)
        return

    fd = os.open(path, os.O_CREAT | os.O_RDWR, FILE_MODE)
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("project is busy; try again in a moment") from None
                time.sleep(poll_interval)
        with suppress(OSError):
            os.chmod(parent, DIR_MODE)
        with suppress(OSError):
            os.chmod(path, FILE_MODE)
        _lock_depth[lock_key] = 1
        try:
            yield
        finally:
            _lock_depth[lock_key] -= 1
            if _lock_depth[lock_key] <= 0:
                _lock_depth.pop(lock_key, None)
    finally:
        with suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        _fsync_dir(parent)


def _ensure_directory(path: Path) -> Path:
    """Create ``path`` (and missing ancestors), refusing symlinks at any level.

    ``Path.mkdir(parents=True, exist_ok=True)`` has two TOCTOU concerns:

    1. It silently follows symlinked ancestors. If any directory in the
       chain is attacker-writable and replaced with a symlink, files may be
       created outside the intended tree.
    2. The legacy post-mkdir ``is_symlink()`` check only inspects the leaf,
       and only after the create. A symlink can be swapped in between
       ``mkdir`` and the check.

    We walk the absolute path component by component, ``lstat``-checking
    each existing segment and creating missing ones with ``os.mkdir`` (no
    parents). A ``FileExistsError`` race is reconciled by re-stat'ing.
    """
    abs_path = Path(path).absolute()
    parts = abs_path.parts
    if not parts:
        raise ValueError(f"refusing empty path: {path}")
    accum = Path(parts[0])
    for part in parts[1:]:
        accum = accum / part
        try:
            st = os.lstat(accum)
        except FileNotFoundError:
            try:
                os.mkdir(accum, mode=DIR_MODE)
            except FileExistsError:
                # Concurrent creator won the race; verify what's there.
                st = os.lstat(accum)
            else:
                continue
        if stat.S_ISLNK(st.st_mode):
            raise ValueError(f"refusing to use symlinked path component: {accum}")
        if not stat.S_ISDIR(st.st_mode):
            raise ValueError(f"expected directory: {accum}")
    return abs_path


def _open_readonly(path: Path) -> int:
    if os.name == "nt":
        if path.is_symlink():
            raise OSError(f"refusing to read symlinked path: {path}")
        return os.open(path, os.O_RDONLY)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return os.open(path, flags)
