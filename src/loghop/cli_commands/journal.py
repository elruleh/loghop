import argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from loghop.cli_commands._helpers import parse_since, require_project_root, resolve_project_target
from loghop.errors import E_INVALID_INPUT, LoghopError
from loghop.redact import redact_text
from loghop.store import project_paths
from loghop.store._models import SessionMeta
from loghop.store._registry import load_registry
from loghop.store._session import list_sessions
from loghop.terminal import Terminal


def handle_journal(args: argparse.Namespace, term: Terminal) -> int:
    since = parse_since(str(args.since or "").strip())
    roots = _resolve_roots(args)
    entries: list[tuple[str, Path, SessionMeta]] = []
    for root in roots:
        paths = project_paths(root)
        for session in list_sessions(paths):
            ts = session.ts_start.strip()
            if since and ts and not _after(ts, since):
                continue
            entries.append((ts, root, session))

    if not entries:
        term.info("No sessions match the filter")
        term.capture_result({"entries": []})
        return 0

    entries.sort(key=lambda item: item[0], reverse=True)
    output = _render_journal(entries, force_project_names=bool(getattr(args, "all", False)))

    term.line(output.rstrip())
    term.capture_result(
        {
            "entries": [
                {
                    "project": root.name,
                    "id": session.id,
                    "provider": session.provider,
                    "ts_start": session.ts_start,
                    "status": session.status,
                }
                for _, root, session in entries
            ],
            "markdown": output,
        }
    )
    return 0


def _render_journal(
    entries: list[tuple[str, Path, SessionMeta]], *, force_project_names: bool = False
) -> str:
    by_date: dict[str, list[tuple[Path, SessionMeta]]] = defaultdict(list)
    for ts, root, session in entries:
        date = ts[:10] if ts else "unknown"
        by_date[date].append((root, session))

    lines: list[str] = ["# loghop journal", ""]
    multi_project = force_project_names or len({root for _, root, _ in entries}) > 1
    for date in sorted(by_date.keys(), reverse=True):
        lines.append(f"## {date}")
        lines.append("")
        for root, session in by_date[date]:
            lines.extend(_render_journal_entry(root, session, multi_project))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_journal_entry(root: Path, session: SessionMeta, multi_project: bool) -> list[str]:
    header = f"### {session.id} · {session.provider}"
    if multi_project:
        header += f" · _{root.name}_"
    status = session.status
    if status:
        header += f" · {status}"
    lines: list[str] = [header, ""]
    goal = session.goal.strip()
    if goal:
        lines.append(f"**Goal:** {redact_text(goal)}")
        lines.append("")
    summary = session.summary.strip()
    if summary:
        lines.append(redact_text(summary))
        lines.append("")
    decisions: Any = session.decisions or []
    if isinstance(decisions, list) and decisions:
        lines.append("**Decisions:**")
        lines.extend(f"- {redact_text(str(d))}" for d in decisions)
        lines.append("")
    todos_pending: Any = session.todos_pending or []
    if isinstance(todos_pending, list) and todos_pending:
        lines.append("**Pending:**")
        lines.extend(f"- [ ] {redact_text(str(t))}" for t in todos_pending)
        lines.append("")
    return lines


def _resolve_roots(args: argparse.Namespace) -> list[Path]:
    if getattr(args, "all", False):
        projects = load_registry()
        roots: list[Path] = []
        for proj in projects:
            path = Path(str(proj.path))
            if path.is_dir() and (path / ".loghop" / "config.toml").exists():
                roots.append(path)
        if not roots:
            raise LoghopError(
                "no registered projects found. Run `loghop init` first.",
                code=E_INVALID_INPUT,
            )
        return roots
    target = getattr(args, "project", None)
    if target:
        resolved = resolve_project_target(str(target))
        if resolved is None:
            raise LoghopError(
                f"no registered project matches `{target}`.",
                code=E_INVALID_INPUT,
            )
        return [resolved]
    return [require_project_root()]


def _after(ts: str, since: datetime) -> bool:
    try:
        parsed = datetime.fromisoformat(ts)
    except ValueError:
        return True
    return parsed >= since
