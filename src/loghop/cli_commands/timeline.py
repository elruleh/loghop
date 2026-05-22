import argparse
from collections import defaultdict
from typing import Any

from loghop.cli_commands._helpers import parse_since, require_project_root
from loghop.store import list_timeline_events, project_paths
from loghop.store._timeline import _event_is_useful
from loghop.terminal import Terminal


def handle_timeline(args: argparse.Namespace, term: Terminal) -> int:
    root = require_project_root()
    since = parse_since(str(getattr(args, "since", "") or "").strip())
    paths = project_paths(root)
    include_all = bool(getattr(args, "all_status", False))
    limit = int(getattr(args, "limit", 50) or 50)
    all_matching_events = list_timeline_events(
        paths,
        provider=getattr(args, "provider", None),
        since=since,
        include_technical=True,
    )
    hidden_count = 0
    if include_all:
        events = all_matching_events[-limit:]
    else:
        events = [event for event in all_matching_events if _event_is_useful(event)]
        hidden_count = len(all_matching_events) - len(events)
        events = events[-limit:]
    if not events:
        term.info("No timeline events match the filter")
        if hidden_count:
            term.line(f"{hidden_count} non-success event(s) hidden; use --all-status")
        term.capture_result({"events": [], "hidden": hidden_count})
        return 0

    output = _render_timeline(events)
    if hidden_count:
        output = (
            output.rstrip() + f"\n\n{hidden_count} non-success event(s) hidden; use --all-status\n"
        )
    term.line(output.rstrip())
    term.capture_result({"events": events, "hidden": hidden_count, "text": output})
    return 0


def _render_timeline(events: list[dict[str, Any]]) -> str:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        ts = str(event.get("ts") or "")
        by_date[ts[:10] if ts else "unknown"].append(event)

    lines: list[str] = ["# loghop timeline", ""]
    for date in sorted(by_date.keys(), reverse=True):
        lines.append(f"## {date}")
        lines.append("")
        for event in sorted(by_date[date], key=_event_render_sort_key, reverse=True):
            lines.extend(_render_event(event))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _event_render_sort_key(event: dict[str, Any]) -> tuple[str, int]:
    session_id = str(event.get("session_id") or "")
    session_number = 0
    if session_id.startswith("S-"):
        try:
            session_number = int(session_id[2:])
        except ValueError:
            session_number = 0
    return str(event.get("ts") or ""), session_number


def _render_event(event: dict[str, Any]) -> list[str]:
    ts = str(event.get("ts") or "")
    time_part = ts[11:16] if len(ts) >= 16 else "--:--"  # noqa: PLR2004
    provider = str(event.get("provider") or "?")
    session_id = str(event.get("session_id") or "?")
    status = str(event.get("status") or "?")
    summary = str(event.get("summary") or "").strip()
    lines = [f"- {time_part}  {provider:<6}  {session_id}  {status}"]
    if summary:
        lines.append(f"  {summary}")
    pending = _list_value(event.get("todos_pending"))
    if pending:
        lines.extend(f"  TODO: {item}" for item in pending[:4])
    files = _list_value(event.get("files_changed"))
    if files:
        lines.append(f"  Files: {', '.join(files[:5])}")
    return lines


def _list_value(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
