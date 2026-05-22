import argparse
import dataclasses
from pathlib import Path

from loghop.cli_commands._helpers import format_relative_time, truncate_text
from loghop.errors import E_INVALID_INPUT, LoghopError
from loghop.redact import redact_text
from loghop.store import delete_project_data, project_paths
from loghop.store._handoff import list_handoffs
from loghop.store._models import RegistryEntry
from loghop.store._registry import cleanup_missing, load_registry, unregister_project
from loghop.store._session import list_sessions
from loghop.terminal import Terminal


def handle_dashboard(_args: argparse.Namespace, term: Terminal) -> int:
    removed = cleanup_missing()
    if removed:
        term.detail(f"cleaned up {removed} missing project(s) from registry")
    projects = load_registry()
    if not projects:
        term.info("No loghop projects registered yet")
        term.info("Run `loghop init` inside a Git repo to get started")
        term.capture_result({"projects": []})
        return 0
    projects.sort(key=lambda p: p.last_used or "", reverse=True)
    rows = []
    for proj in projects:
        path = Path(proj.path or "")
        exists = path.is_dir()
        name = proj.name or path.name
        goal = proj.goal or ""
        last_used = format_relative_time(proj.last_used or "")
        status_icon = "\u2022"
        state = "" if exists else " (missing)"
        goal_display = truncate_text(goal, 40) if goal else "-"
        rows.append(
            (
                f"{status_icon} {name}{state}",
                goal_display,
                last_used,
                str(proj.session_count or 0),
                str(proj.handoff_count or 0),
            )
        )
    term.table(
        rows,
        headers=("project", "goal", "last used", "sessions", "handoffs"),
        title="loghop projects",
    )
    term.info(f"{len(projects)} project(s) registered")
    term.capture_result(
        {"projects": [dataclasses.asdict(p) for p in projects], "count": len(projects)}
    )
    return 0


def handle_projects_cleanup(_args: argparse.Namespace, term: Terminal) -> int:
    removed = cleanup_missing()
    if removed:
        term.success(f"Removed {removed} missing project(s)")
    else:
        term.info("All registered projects are valid")
    term.capture_result({"removed": removed})
    return 0


def handle_projects_show(args: argparse.Namespace, term: Terminal) -> int:
    target = str(args.target or "").strip()
    if not target:
        raise LoghopError(
            "projects show requires a name or path.",
            code=E_INVALID_INPUT,
        )
    projects = load_registry()
    entry = _match_project(projects, target)
    if entry is None:
        raise LoghopError(
            f"no registered project matches `{target}`. "
            "Run `loghop projects` to see registered projects.",
            code=E_INVALID_INPUT,
        )
    root = Path(str(entry.path or ""))
    if not (root / ".loghop" / "config.toml").exists():
        term.warn(f"Project `{entry.name or target}` is registered but missing on disk")
        term.capture_result({"project": dataclasses.asdict(entry), "missing": True})
        return 0
    paths = project_paths(root)
    sessions = list_sessions(paths)
    handoffs = list_handoffs(paths)
    goal = redact_text(str(entry.goal or ""))
    rows = [
        ("name", str(entry.name or root.name)),
        ("path", str(root)),
        ("goal", goal or "(not set)"),
        ("last used", format_relative_time(entry.last_used or "")),
        ("sessions", str(len(sessions))),
        ("handoffs", str(len(handoffs))),
    ]
    if entry.last_session:
        rows.append(("last session", entry.last_session))
    term.section(f"project: {entry.name or root.name}", rows)
    if sessions:
        term.line("")
        term.table(
            [
                (
                    s.id or "?",
                    s.provider or "?",
                    s.status or "?",
                    (s.summary or "")[:60],
                    (s.ts_start or "")[:10],
                )
                for s in sessions[:20]
            ],
            headers=("id", "provider", "status", "summary", "started"),
            title="recent sessions",
        )
        if len(sessions) > 20:  # noqa: PLR2004
            term.info(f"... {len(sessions) - 20} older sessions not shown")
    else:
        term.info("No sessions recorded yet")
    term.capture_result(
        {
            "project": dataclasses.asdict(entry),
            "sessions": [dataclasses.asdict(s) for s in sessions],
            "handoffs": [dataclasses.asdict(h) for h in handoffs],
        }
    )
    return 0


def handle_projects_remove(args: argparse.Namespace, term: Terminal) -> int:
    entry = _require_project_entry(str(args.target or "").strip())
    path = Path(str(entry.path or "")).expanduser()
    name = str(entry.name or path.name or args.target)
    if not getattr(args, "yes", False) and not term.confirm(
        f"Remove project {name} from the registry? Local .loghop data will be kept.",
        default=False,
    ):
        term.info("Aborted")
        term.capture_result({"removed": None, "aborted": True})
        return 0
    unregister_project(path)
    term.success(f"Removed project {name} from the registry")
    term.capture_result({"removed": dataclasses.asdict(entry), "purged": False})
    return 0


def handle_projects_purge(args: argparse.Namespace, term: Terminal) -> int:
    entry = _require_project_entry(str(args.target or "").strip())
    path = Path(str(entry.path or "")).expanduser()
    name = str(entry.name or path.name or args.target)
    if not getattr(args, "yes", False) and not term.confirm(
        f"Purge loghop data for project {name}? This deletes its .loghop directory and unregisters it.",
        default=False,
    ):
        term.info("Aborted")
        term.capture_result({"purged": None, "aborted": True})
        return 0
    purged = False
    if path.exists():
        purged = delete_project_data(path)
    unregister_project(path)
    if purged:
        term.success(f"Purged project {name}")
    else:
        term.success(f"Removed project {name} from the registry (no local .loghop data found)")
    term.capture_result({"removed": dataclasses.asdict(entry), "purged": purged})
    return 0


def _require_project_entry(target: str) -> RegistryEntry:
    if not target:
        raise LoghopError(
            "project target is required.",
            code=E_INVALID_INPUT,
        )
    entry = _match_project(load_registry(), target)
    if entry is None:
        raise LoghopError(
            f"no registered project matches `{target}`. "
            "Run `loghop projects` to see registered projects.",
            code=E_INVALID_INPUT,
        )
    return entry


def _match_project(projects: list[RegistryEntry], target: str) -> RegistryEntry | None:
    resolved = str(Path(target).expanduser().resolve()) if "/" in target else target
    for proj in projects:
        if str(proj.path or "") == resolved:
            return proj
    exact_name_matches = [p for p in projects if str(p.name or "") == target]
    if len(exact_name_matches) == 1:
        return exact_name_matches[0]
    if len(exact_name_matches) > 1:
        exact_match_labels = ", ".join(f"{p.name} -> {p.path}" for p in exact_name_matches)
        raise LoghopError(
            f"ambiguous target `{target}` matches multiple projects: {exact_match_labels}. "
            "Use the full project path.",
            code=E_INVALID_INPUT,
        )
    fuzzy_matches = [p for p in projects if target.lower() in str(p.name or "").lower()]
    if len(fuzzy_matches) == 1:
        return fuzzy_matches[0]
    if len(fuzzy_matches) > 1:
        names = ", ".join(f"{p.name} -> {p.path}" for p in fuzzy_matches)
        raise LoghopError(
            f"ambiguous target `{target}` matches multiple projects: {names}. "
            "Use the full project name or path.",
            code=E_INVALID_INPUT,
        )
    return None
