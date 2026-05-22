import dataclasses
import shutil
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import tomli_w

from loghop.logging import get_logger
from loghop.store._constants import utc_now
from loghop.store._io import (
    _ensure_directory,
    atomic_write_private_text,
    project_lock,
    safe_read_text,
)
from loghop.store._models import RegistryEntry

_LOGGER = get_logger()


def _safe_int(value: object, default: int = 0) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def global_dir() -> Path:
    return Path.home() / ".loghop"


def _registry_path() -> Path:
    return global_dir() / "projects.toml"


def _registry_lock_path() -> Path:
    return global_dir() / ".registry.lock"


def _ensure_global_dir() -> None:
    _ensure_directory(global_dir())


@contextmanager
def _registry_lock() -> Iterator[None]:
    _ensure_global_dir()
    with project_lock(_registry_lock_path()):
        yield


def load_registry() -> list[RegistryEntry]:
    path = _registry_path()
    if not path.exists():
        return []
    try:
        raw = tomllib.loads(safe_read_text(path))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        _quarantine_registry(path, reason=str(exc))
        return []
    projects = raw.get("project", [])
    if not isinstance(projects, list):
        _quarantine_registry(path, reason="`project` table is not a list")
        return []

    return [
        RegistryEntry(
            name=str(p.get("name")),
            path=str(p.get("path")),
            registered=str(p.get("registered", "")),
            last_used=str(p.get("last_used")),
            goal=str(p.get("goal")),
            last_session=str(p.get("last_session", "")),
            session_count=_safe_int(p.get("session_count", 0)),
            handoff_count=_safe_int(p.get("handoff_count", 0)),
        )
        for p in projects
        if isinstance(p, dict) and isinstance(p.get("path"), str)
    ]


def save_registry(projects: list[RegistryEntry]) -> None:
    _ensure_global_dir()
    data = {"project": [dataclasses.asdict(proj) for proj in projects]}

    text = "# loghop global project registry\n\n" + tomli_w.dumps(data)
    atomic_write_private_text(_registry_path(), text)


def register_project(root: Path, goal: str = "") -> None:
    root = root.resolve()
    path_str = str(root)
    with _registry_lock():
        projects = load_registry()
        existing = next((proj for proj in projects if proj.path == path_str), None)
        replacement = _registry_entry_from_disk(root, existing=existing, goal_override=goal or None)
        if existing is not None:
            for i, proj in enumerate(projects):
                if proj.path == path_str:
                    projects[i] = replacement
                    break
        else:
            projects.append(replacement)
        save_registry(projects)


def unregister_project(root: Path) -> None:
    root = root.resolve()
    path_str = str(root)
    with _registry_lock():
        projects = load_registry()
        projects = [p for p in projects if p.path != path_str]
        save_registry(projects)


def delete_project_data(root: Path) -> bool:
    root = root.resolve()
    dot = root / ".loghop"
    lock_path = dot / ".lock"
    with project_lock(lock_path):
        if dot.is_symlink():
            raise ValueError("refusing to delete symlinked .loghop directory")
        try:
            dot.relative_to(root)
        except ValueError as exc:
            raise ValueError("refusing to delete project data outside project root") from exc
        if not (dot / "config.toml").exists():
            return False
        if not dot.is_dir():
            raise ValueError("invalid .loghop path")
        shutil.rmtree(dot)
    return True


def touch_project(
    root: Path,
    *,
    last_session: str | None = None,
    bump_session: bool = False,
    bump_handoff: bool = False,
    **extra: Any,
) -> None:
    root = root.resolve()
    if not (root / ".loghop" / "config.toml").exists():
        return
    path_str = str(root)
    goal = _read_project_goal(root)
    with _registry_lock():
        projects = load_registry()
        entry_idx = next((i for i, p in enumerate(projects) if p.path == path_str), None)

        if entry_idx is None:
            entry = RegistryEntry(
                name=root.name,
                path=path_str,
                registered=utc_now(),
                last_used=utc_now(),
                goal=goal,
                last_session=last_session or "",
                session_count=1 if bump_session else 0,
                handoff_count=1 if bump_handoff else 0,
                # Ignore extra to prevent typing errors as extra fields aren't in RegistryEntry
            )
            projects.append(entry)
            save_registry(projects)
            return

        orig = projects[entry_idx]
        replacements: dict[str, Any] = {
            "last_used": utc_now(),
            "goal": goal or orig.goal,
        }
        if last_session is not None:
            replacements["last_session"] = last_session
        if bump_session:
            replacements["session_count"] = int(orig.session_count) + 1
        if bump_handoff:
            replacements["handoff_count"] = int(orig.handoff_count) + 1

        projects[entry_idx] = dataclasses.replace(orig, **replacements)
        save_registry(projects)


def sync_project(root: Path) -> None:
    root = root.resolve()
    if not (root / ".loghop" / "config.toml").exists():
        return
    path_str = str(root)
    with _registry_lock():
        projects = load_registry()
        existing = next((proj for proj in projects if proj.path == path_str), None)
        if existing is None:
            return
        replacement = _registry_entry_from_disk(root, existing=existing)
        for i, proj in enumerate(projects):
            if proj.path == path_str:
                projects[i] = replacement
                break
        save_registry(projects)


def _read_project_goal(root: Path) -> str:
    cfg_path = root / ".loghop" / "config.toml"
    if not cfg_path.exists():
        return ""
    try:
        data = tomllib.loads(safe_read_text(cfg_path))
    except (tomllib.TOMLDecodeError, OSError):
        return ""
    value = data.get("goal", "")
    return str(value) if isinstance(value, str) else ""


def cleanup_missing() -> int:
    with _registry_lock():
        projects = load_registry()
        valid = []
        for proj in projects:
            path = Path(proj.path)
            if path.is_dir() and (path / ".loghop" / "config.toml").exists():
                valid.append(proj)
        removed = len(projects) - len(valid)
        if removed > 0:
            save_registry(valid)
        return removed


def _registry_entry_from_disk(
    root: Path,
    *,
    existing: RegistryEntry | None = None,
    goal_override: str | None = None,
) -> RegistryEntry:
    goal = goal_override if goal_override is not None else _read_project_goal(root)
    session_count = 0
    handoff_count = 0
    last_session = ""
    if (root / ".loghop" / "config.toml").exists():
        try:
            from loghop.store._constants import project_paths
            from loghop.store._handoff import list_handoffs
            from loghop.store._session import list_sessions

            paths = project_paths(root)
            sessions = list_sessions(paths)
            handoffs = list_handoffs(paths)
            session_count = len(sessions)
            handoff_count = len(handoffs)
            if sessions:
                last_session = sessions[0].id or ""
        except (OSError, ValueError):
            session_count = 0
            handoff_count = 0
            last_session = ""
        if not goal:
            goal = _read_project_goal(root)

    registered = existing.registered if existing is not None else utc_now()
    return RegistryEntry(
        name=root.name,
        path=str(root),
        registered=registered,
        last_used=utc_now(),
        goal=goal or (existing.goal if existing is not None else ""),
        last_session=last_session,
        session_count=session_count,
        handoff_count=handoff_count,
    )


def _quarantine_registry(path: Path, *, reason: str) -> None:
    """Keep a copy of an unreadable registry before callers rebuild it."""
    if not path.exists():
        return
    backup = path.with_name(f"{path.name}.corrupt-{_backup_stamp()}")
    try:
        shutil.copy2(path, backup)
    except OSError:
        _LOGGER.warning(
            "global registry is unreadable and could not be backed up",
            extra={"component": "registry", "path": str(path), "reason": reason},
        )
        return
    _LOGGER.warning(
        "global registry is unreadable; backed up corrupt copy",
        extra={
            "component": "registry",
            "path": str(path),
            "backup": str(backup),
            "reason": reason,
        },
    )


def _backup_stamp() -> str:
    return utc_now().replace(":", "").replace("-", "").replace(".", "").replace("+", "Z")
