import argparse
import dataclasses
import re
from collections import defaultdict
from typing import Any

from loghop.cli_commands._helpers import require_project_root, truncate_text
from loghop.errors import E_INVALID_INPUT, LoghopError
from loghop.reconcile import reconcile_running_sessions
from loghop.store import ProjectPaths, project_paths
from loghop.store._io import safe_read_text
from loghop.store._models import SessionMeta
from loghop.store._session import delete_session, find_session, list_sessions
from loghop.terminal import Terminal

_SESSION_ID_RE = re.compile(r"^S-(\d+)$")


def handle_sessions_list(args: argparse.Namespace, term: Terminal) -> int:
    root = require_project_root()
    paths = project_paths(root)
    sessions = list_sessions(paths, provider=args.provider)
    if not sessions:
        term.info("No sessions yet")
        term.capture_result({"sessions": []})
        return 0

    if getattr(args, "expand", False):
        _render_expanded(sessions, term)
    else:
        _render_tree(sessions, term)

    term.capture_result({"sessions": sessions})
    return 0


def handle_sessions_reconcile(args: argparse.Namespace, term: Terminal) -> int:
    root = require_project_root()
    reports = reconcile_running_sessions(root)
    if not reports:
        term.info("No running sessions to reconcile")
        term.capture_result({"reconciled": []})
        return 0
    for report in reports:
        sid = report["id"]
        if report.get("status") == "reconcile_error":
            term.warn(f"{sid}: reconcile failed: {report.get('error', 'unknown error')}")
            continue
        turns = int(report.get("turns_captured") or 0)
        if turns:
            term.success(f"{sid}: recovered {turns} turns")
        else:
            term.warn(f"{sid}: no transcript found; marked interrupted")
    term.capture_result({"reconciled": reports})
    return 0


def handle_sessions_show(args: argparse.Namespace, term: Terminal) -> int:
    root = require_project_root()
    paths = project_paths(root)
    session_id = _resolve_session_id(paths, args.session_id, latest=bool(args.latest))
    session_path = paths.root / f".loghop/sessions/{session_id}.md"
    if not session_path.exists():
        raise LoghopError(f"session {session_id} not found", code=E_INVALID_INPUT)
    text = safe_read_text(session_path)
    term.line(text.rstrip())
    meta = find_session(paths, session_id)
    term.capture_result({**dataclasses.asdict(meta), "markdown": text})
    return 0


def handle_sessions_delete(args: argparse.Namespace, term: Terminal) -> int:
    root = require_project_root()
    paths = project_paths(root)
    session_id = _resolve_session_id(paths, args.session_id, latest=bool(args.latest))
    session = find_session(paths, session_id)
    if not getattr(args, "yes", False):
        summary = str(session.summary or session.goal or "")
        label = f" ({truncate_text(summary, 60)})" if summary else ""
        if not term.confirm(f"Delete session {session_id}{label}?", default=False):
            term.info("Aborted")
            term.capture_result({"deleted": None, "aborted": True})
            return 0
    delete_session(paths, session_id)
    term.success(f"Deleted session {session_id}")
    term.capture_result({"deleted": session_id})
    return 0


def _render_tree(sessions: list[SessionMeta], term: Terminal) -> None:
    by_date: dict[str, list[SessionMeta]] = defaultdict(list)
    for s in sessions:
        ts = s.ts_start
        date = ts[:10] if ts else "unknown"
        by_date[date].append(s)

    for date in sorted(by_date.keys(), reverse=True):
        if term.plain:
            term.line(f"  {date}/")
        else:
            try:
                from rich.tree import Tree  # noqa: F401

                _render_rich_tree(by_date, term)
            except ImportError:
                term.line(f"  {date}/")
            else:
                return

        for s in by_date[date]:
            status_icon = _status_icon(s.status)
            sid = s.id
            provider = s.provider
            goal = s.goal
            goal_display = truncate_text(goal, 50) if goal else "-"
            term.line(f"    {sid}  {provider}  {status_icon}  {goal_display}")
        term.line("")

    if term.json_mode:
        return


def _render_rich_tree(by_date: dict[str, list[SessionMeta]], term: Terminal) -> None:
    from rich.text import Text
    from rich.tree import Tree

    console = term.console
    if console is None:
        return

    tree = Tree("sessions", guide_style="dim")
    for date in sorted(by_date.keys(), reverse=True):
        date_branch = tree.add(Text(date, style="bold"))
        for s in by_date[date]:
            status_icon = _status_icon(s.status)
            sid = s.id
            provider = s.provider
            goal = s.goal
            goal_display = truncate_text(goal, 50) if goal else "-"
            handoff = s.handoff_id
            extra = f" -> {handoff}" if handoff else ""
            decisions = s.decisions
            todos = s.todos_pending
            meta_parts: list[str] = []
            if decisions and isinstance(decisions, list):
                meta_parts.append(f"{len(decisions)} decisions")
            if todos and isinstance(todos, list):
                meta_parts.append(f"{len(todos)} todos")
            meta_str = f" ({', '.join(meta_parts)})" if meta_parts else ""
            label = Text(f"{status_icon} {sid}  {provider}  {goal_display}{extra}")
            if meta_str:
                label.append(meta_str, style="dim")
            date_branch.add(label)
    console.print(tree)


def _render_expanded(sessions: list[SessionMeta], term: Terminal) -> None:
    by_date: dict[str, list[SessionMeta]] = defaultdict(list)
    for s in sessions:
        ts = s.ts_start
        date = ts[:10] if ts else "unknown"
        by_date[date].append(s)

    for date in sorted(by_date.keys(), reverse=True):
        term.line(f"  {date}/")
        for s in by_date[date]:
            _render_expanded_session(s, term)
        term.line("")


def _render_expanded_session(s: SessionMeta, term: Terminal) -> None:
    status_icon = _status_icon(s.status)
    sid = s.id
    provider = s.provider
    goal = s.goal
    term.line(f"    {sid}  {provider}  {status_icon}  {goal}")
    if s.summary:
        term.line(f"      Summary: {s.summary[:80]}")
    _render_list_items(term, s.decisions, "      - ", 5, "decisions")
    _render_list_items(term, s.todos_pending, "      TODO: ", 5, "todos")
    files = s.files_changed
    if files and isinstance(files, list):
        term.line(f"      Files: {', '.join(str(f) for f in files[:5])}")
    term.line("")


def _render_list_items(term: Terminal, items: Any, prefix: str, limit: int, label: str) -> None:
    if not items or not isinstance(items, list):
        return
    for item in items[:limit]:
        term.line(f"{prefix}{item}")
    if len(items) > limit:
        term.line(f"      ... {len(items) - limit} more {label}")


def _status_icon(status: str) -> str:
    icons = {
        "succeeded": "\u2705",
        "failed": "\u274c",
        "timed_out": "\u23f1",
        "running": "\U0001f504",
        "built": "\U0001f4e6",
        "launch_failed": "\u26a0",
    }
    return icons.get(status, status)


def _resolve_session_id(paths: ProjectPaths, session_id: str | None, *, latest: bool) -> str:
    if latest:
        sessions = list_sessions(paths)
        if not sessions:
            raise LoghopError("no sessions found", code=E_INVALID_INPUT)
        return sessions[0].id
    if not session_id:
        raise LoghopError("session id is required unless --latest is used", code=E_INVALID_INPUT)
    if not _SESSION_ID_RE.match(session_id):
        raise LoghopError(f"invalid session id: {session_id}", code=E_INVALID_INPUT)
    return session_id
