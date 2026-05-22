"""View-model helpers for the project screen.

Extracts data filtering, sorting, and preparation from the Textual screen
so that the UI layer only handles rendering.
"""

from __future__ import annotations

from typing import Any

from loghop.tui.format import parse_timestamp

_SORT_TIME = "time"
_SORT_STATUS = "status"
_SORT_PROVIDER = "provider"
SORT_CYCLE: tuple[str, ...] = (_SORT_TIME, _SORT_STATUS, _SORT_PROVIDER)
SORT_LABELS: dict[str, str] = {
    _SORT_TIME: "SORT_TIME",
    _SORT_STATUS: "SORT_STATUS",
    _SORT_PROVIDER: "SORT_PROVIDER",
}

_STATUS_PRIORITY: dict[str, int] = {
    "running": 0,
    "failed": 1,
    "launch_failed": 1,
    "timed_out": 2,
    "interrupted": 2,
    "succeeded": 3,
}
_PENDING_TODO_LIMIT = 3
_DONE_TODO_LIMIT = 2
_CONVERSATION_TURN_ARITY = 2
_EXCERPT_MAX_LINES = 3
_EXCERPT_MAX_CHARS = 260
_LIST_MAX_CHARS = 96


def _reverse_time_key(value: str) -> int:
    parsed = parse_timestamp(value)
    if parsed is None:
        return 0
    return -int(parsed.timestamp())


def filter_sessions(
    sessions: list[Any],
    *,
    provider: str,
    text: str,
    flags: set[str],
) -> list[Any]:
    """Filter sessions by provider, search text, and status flags."""
    result = list(sessions)
    if provider:
        result = [s for s in result if getattr(s, "provider", "") == provider]
    if text:
        result = [s for s in result if _matches_text(s, text)]
    for flag in flags:
        result = [s for s in result if _matches_flag(s, flag)]
    return result


def sort_sessions(sessions: list[Any], key: str) -> list[Any]:
    """Sort sessions by the given key."""
    if key == _SORT_STATUS:
        return sorted(
            sessions,
            key=lambda s: (
                _STATUS_PRIORITY.get((getattr(s, "status", "") or "").lower(), 9),
                _reverse_time_key(getattr(s, "ts_start", "") or ""),
            ),
        )
    if key == _SORT_PROVIDER:
        return sorted(
            sessions,
            key=lambda s: (
                (getattr(s, "provider", "") or "").lower(),
                _reverse_time_key(getattr(s, "ts_start", "") or ""),
            ),
        )
    return list(sessions)


def matches_text(session: Any, text: str) -> bool:
    """Check if a session matches search text (id, goal, summary, etc)."""
    pending = " ".join(str(item) for item in (getattr(session, "todos_pending", ()) or ()))
    done = " ".join(str(item) for item in (getattr(session, "todos_done", ()) or ()))
    decisions = " ".join(str(item) for item in (getattr(session, "decisions", ()) or ()))
    files = " ".join(str(item) for item in (getattr(session, "files_changed", ()) or ()))
    haystack = (
        f"{getattr(session, 'id', '')} "
        f"{getattr(session, 'session_id', '')} "
        f"{getattr(session, 'provider', '')} "
        f"{getattr(session, 'title', '')} "
        f"{getattr(session, 'goal', '')} "
        f"{getattr(session, 'summary', '')} "
        f"{getattr(session, 'status', '')} "
        f"{pending} "
        f"{done} "
        f"{decisions} "
        f"{files}"
    ).lower()
    return text in haystack


def _matches_text(session: Any, text: str) -> bool:
    return matches_text(session, text)


def _matches_flag(session: Any, flag: str) -> bool:
    from datetime import UTC, datetime, timedelta

    from loghop.tui.format import parse_timestamp

    status = (getattr(session, "status", "") or "").lower()
    if flag == "running":
        return status == "running"
    if flag == "failed":
        return status in {"failed", "launch_failed", "timed_out", "interrupted"}
    if flag == "done":
        return status == "succeeded"
    if flag == "today":
        parsed = parse_timestamp(getattr(session, "ts_start", "") or "")
        if parsed is None:
            return False
        return datetime.now(UTC) - parsed.astimezone(UTC) < timedelta(days=1)
    return True


def running_session_ids(sessions: list[Any]) -> set[str]:
    """Return the set of IDs for sessions that are still running."""
    from loghop.tui.widgets import badge

    return {
        str(getattr(s, "id", "")) for s in sessions if badge.is_running(getattr(s, "status", ""))
    }


def format_list_block(items: tuple[str, ...], *, limit: int) -> str:
    from loghop.tui import strings
    from loghop.tui.format import truncate
    from loghop.tui.widgets import glyph

    visible = [
        f"{glyph.DOT} {truncate(str(item), max_chars=_LIST_MAX_CHARS)}" for item in items[:limit]
    ]
    if len(items) > limit:
        visible.append(
            f"[dim]{glyph.ELLIPSIS} {strings.tr('MORE_ITEMS', count=len(items) - limit)}[/]"
        )
    return "\n".join(visible)


def _format_file_entry(path_value: str) -> str:
    from pathlib import Path

    path = Path(path_value)
    name = path.name or path_value
    parent = str(path.parent)
    if parent in (".", ""):
        return name
    return f"{name}  [dim]{parent}[/]"


def format_files_block(files: tuple[str, ...], *, limit: int) -> str:
    from loghop.tui import strings
    from loghop.tui.widgets import glyph

    lines = [_format_file_entry(path) for path in files[:limit]]
    if len(files) > limit:
        lines.append(
            f"[dim]{glyph.ELLIPSIS} {strings.tr('MORE_ITEMS', count=len(files) - limit)}[/]"
        )
    return "\n".join(lines)


def format_todos_block(pending: tuple[str, ...], done: tuple[str, ...]) -> str:
    from loghop.tui import strings
    from loghop.tui.widgets import glyph

    lines: list[str] = []
    lines.extend(f"☐ {item}" for item in pending[:_PENDING_TODO_LIMIT])
    if len(pending) > _PENDING_TODO_LIMIT:
        lines.append(
            f"[dim]{glyph.ELLIPSIS} {strings.tr('MORE_PENDING', count=len(pending) - _PENDING_TODO_LIMIT)}[/]"
        )
    lines.extend(f"[dim]☑ {item}[/]" for item in done[:_DONE_TODO_LIMIT])
    if len(done) > _DONE_TODO_LIMIT:
        lines.append(
            f"[dim]{glyph.ELLIPSIS} {strings.tr('MORE_DONE', count=len(done) - _DONE_TODO_LIMIT)}[/]"
        )
    return "\n".join(lines)


def format_next_block(pending: tuple[str, ...], done: tuple[str, ...]) -> str:
    from loghop.tui import strings

    if pending or done:
        return format_todos_block(pending, done)
    clear = strings.tr("SESSION_NEXT_CLEAR")
    if clear == "SESSION_NEXT_CLEAR":
        clear = "No pending work recorded."
    return f"[dim]{clear}[/]"


def _truncate_block(text: str, *, max_lines: int, max_chars: int) -> str:
    from loghop.tui.widgets import glyph

    stripped = str(text).strip()
    if not stripped:
        return ""
    lines = stripped.splitlines()
    clipped = lines[:max_lines]
    body = "\n".join(clipped)
    truncated = len(lines) > max_lines
    if len(body) > max_chars:
        body = body[: max_chars - 1].rstrip() + glyph.ELLIPSIS
        truncated = True
    if truncated:
        body = f"{body}\n[dim]{glyph.ELLIPSIS}[/]"
    return body


def format_conversation_excerpt(session: Any, *, limit: int = 4) -> str:
    turns = tuple(getattr(session, "conversation_excerpt", ()) or ())
    lines: list[str] = []
    for raw in turns[:limit]:
        if isinstance(raw, tuple) and len(raw) == _CONVERSATION_TURN_ARITY:
            role, text = raw
            body = _truncate_block(
                str(text), max_lines=_EXCERPT_MAX_LINES, max_chars=_EXCERPT_MAX_CHARS
            )
            if not body:
                continue
            lines.append(f"[dim]{role!s}:[/]\n{body}")
            continue
        body = _truncate_block(str(raw), max_lines=1, max_chars=_LIST_MAX_CHARS)
        if body:
            lines.append(body)
    return "\n\n".join(lines)
