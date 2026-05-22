from pathlib import Path

from loghop.gittools import GitRepo
from loghop.store._config import default_config, save_config
from loghop.store._constants import (
    DEFAULT_IGNORE,
    DEFAULT_MEMORY_FILE,
    DIR_MODE,
    ProjectPaths,
    project_paths,
)
from loghop.store._io import atomic_write_private_text, atomic_write_text, safe_read_text
from loghop.store._render import render_memory


def find_project_root(start: Path) -> Path | None:
    repo = GitRepo.from_cwd(start)
    if repo is None:
        return None
    candidate = repo.root.resolve()
    try:
        paths = _validate_project_layout(candidate, require_initialized=True)
    except ValueError:
        return None
    if paths.config.exists():
        return candidate
    return None


def init_project(root: Path) -> ProjectPaths:
    repo = GitRepo.from_cwd(root)
    if repo is None or repo.root.resolve() != root.resolve():
        raise ValueError("loghop can only be initialized at a Git repository root")
    paths = project_paths(root)
    if paths.dot.is_symlink():
        raise ValueError("refusing to initialize into a symlinked .loghop directory")
    if paths.dot.exists():
        raise ValueError("loghop already initialized in this repository")
    paths.dot.mkdir(parents=True, exist_ok=False, mode=DIR_MODE)
    paths.handoffs.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
    paths.sessions.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)

    config = default_config(root.name)
    save_config(paths, config)

    atomic_write_private_text(paths.ignore, DEFAULT_IGNORE)
    render_memory(paths, config)
    _ensure_gitignore(root)

    from loghop.store._registry import register_project

    register_project(root)

    return paths


def _ensure_gitignore(root: Path) -> None:
    gitignore = root / ".gitignore"
    entries = [".loghop/", DEFAULT_MEMORY_FILE]
    existing = safe_read_text(gitignore) if gitignore.exists() else ""
    existing_lines = existing.splitlines()
    lines = list(existing_lines)
    changed = False
    for entry in entries:
        if entry not in existing_lines:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(entry)
            changed = True
    if changed:
        if lines and lines[-1].strip():
            lines.append("")
        atomic_write_text(gitignore, "\n".join(lines))


def _validate_project_layout(root: Path, *, require_initialized: bool) -> ProjectPaths:
    paths = project_paths(root)
    if paths.dot.is_symlink():
        raise ValueError("refusing to use a symlinked .loghop directory")
    if require_initialized and not paths.dot.is_dir():
        raise ValueError("loghop project is not initialized")
    if paths.dot.exists() and not paths.dot.is_dir():
        raise ValueError("invalid .loghop path")
    if paths.handoffs.exists() and paths.handoffs.is_symlink():
        raise ValueError("refusing to use a symlinked handoff directory")
    if paths.handoffs.exists() and not paths.handoffs.is_dir():
        raise ValueError("invalid handoff directory")
    if paths.sessions.exists() and paths.sessions.is_symlink():
        raise ValueError("refusing to use a symlinked session directory")
    if paths.sessions.exists() and not paths.sessions.is_dir():
        raise ValueError("invalid session directory")
    if paths.config.exists() and paths.config.is_symlink():
        raise ValueError("refusing to use a symlinked config file")
    return paths
