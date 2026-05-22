from __future__ import annotations

import argparse
import os
import tarfile
from pathlib import Path
from typing import BinaryIO

from loghop.gittools import GitRepo
from loghop.store import project_paths, utc_now
from loghop.store._io import _ensure_directory
from loghop.terminal import Terminal

_BACKUP_PREFIX = "loghop-backup-"


def handle_backup_create(args: argparse.Namespace, term: Terminal) -> int:
    root = _project_root_from_cwd()
    paths = project_paths(root)
    output = Path(getattr(args, "output", "") or _default_backup_path(root))
    if not output.is_absolute():
        output = (root / output).resolve()
    if output.is_symlink():
        raise ValueError("refusing to write symlinked backup output")
    _ensure_directory(output.parent)
    with _open_private_backup_output(output) as output_file:
        with tarfile.open(fileobj=output_file, mode="w:gz", dereference=False) as tar:
            _add_if_exists(tar, paths.dot, ".loghop", exclude_prefix=".loghop/backups/")
            _add_if_exists(tar, paths.memory, paths.memory.name)
        output_file.flush()
        os.fsync(output_file.fileno())
    os.chmod(output, 0o600)
    term.success(f"backup written: {output}")
    term.capture_result({"archive": str(output)})
    return 0


def handle_backup_restore(args: argparse.Namespace, term: Terminal) -> int:
    root = _project_root_from_cwd(require_initialized=False)
    archive = Path(str(getattr(args, "archive", ""))).expanduser()
    if not archive.is_absolute():
        archive = (Path.cwd() / archive).resolve()
    if not getattr(args, "yes", False) and not term.confirm(
        f"Restore loghop data from {archive}?", default=False
    ):
        term.warn("restore cancelled")
        term.capture_result({"restored": False, "cancelled": True})
        return 2
    restored = _restore_archive(root, archive)
    term.success(f"restored {restored} files from {archive}")
    term.capture_result({"restored": True, "archive": str(archive), "files": restored})
    return 0


def _project_root_from_cwd(*, require_initialized: bool = True) -> Path:
    repo = GitRepo.from_cwd(Path.cwd())
    if repo is None:
        raise ValueError("loghop backup requires a Git repository")
    root = repo.root.resolve()
    if require_initialized and not project_paths(root).config.exists():
        raise ValueError("loghop is not initialized in this repository")
    if project_paths(root).dot.exists() and project_paths(root).dot.is_symlink():
        raise ValueError("refusing to use a symlinked .loghop directory")
    return root


def _default_backup_path(root: Path) -> Path:
    stamp = utc_now().replace(":", "").replace("-", "")
    return root / ".loghop" / "backups" / f"{_BACKUP_PREFIX}{stamp}.tar.gz"


def _open_private_backup_output(path: Path) -> BinaryIO:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    return os.fdopen(fd, "wb")


def _add_if_exists(
    tar: tarfile.TarFile,
    path: Path,
    arcname: str,
    *,
    exclude_prefix: str | None = None,
) -> None:
    if not path.exists():
        return
    if path.is_symlink():
        raise ValueError(f"refusing to backup symlinked path: {path}")
    if path.is_dir():
        for child in sorted(path.rglob("*")):
            rel = child.relative_to(path.parent).as_posix()
            if exclude_prefix and rel.startswith(exclude_prefix):
                continue
            if child.is_symlink():
                raise ValueError(f"refusing to backup symlinked path: {child}")
            tar.add(child, arcname=rel, recursive=False)
        return
    tar.add(path, arcname=arcname, recursive=False)


def _restore_archive(root: Path, archive: Path) -> int:
    if archive.is_symlink():
        raise ValueError("refusing to restore symlinked backup archive")
    restored = 0
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            target = _safe_restore_target(root, member)
            if member.isdir():
                _ensure_directory(target)
                continue
            if not member.isfile():
                raise ValueError(f"unsafe backup member: {member.name}")
            _ensure_directory(target.parent)
            extracted = tar.extractfile(member)
            if extracted is None:
                raise ValueError(f"could not read backup member: {member.name}")
            _write_private_bytes(target, extracted.read())
            restored += 1
    return restored


def _write_private_bytes(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def _safe_restore_target(root: Path, member: tarfile.TarInfo) -> Path:
    name = member.name.replace("\\", "/")
    if name.startswith("/") or ".." in Path(name).parts:
        raise ValueError(f"unsafe backup member: {member.name}")
    if not (name == "loghop.md" or name.startswith(".loghop/")):
        raise ValueError(f"unsafe backup member: {member.name}")
    target = root / name
    if target.is_symlink():
        raise ValueError(f"refusing to overwrite symlinked restore target: {member.name}")
    resolved = target.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"unsafe backup member: {member.name}") from exc
    return resolved
