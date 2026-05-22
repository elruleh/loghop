from __future__ import annotations

from typing import Any

from loghop.tui import strings
from loghop.tui.format import relative_time, truncate
from loghop.tui.widgets import glyph

SORT_RECENT = "recent"
SORT_NAME = "name"
SORT_SESSIONS = "sessions"
PREVIEW_ITEM_LIMIT = 3
SORT_CYCLE: tuple[str, ...] = (SORT_RECENT, SORT_NAME, SORT_SESSIONS)
SORT_LABELS: dict[str, str] = {
    SORT_RECENT: "SORT_RECENT",
    SORT_NAME: "SORT_NAME",
    SORT_SESSIONS: "SORT_SESSIONS",
}


def sort_projects(projects: list[Any], key: str) -> list[Any]:
    if key == SORT_NAME:
        return sorted(projects, key=lambda p: (getattr(p, "name", "") or "").lower())
    if key == SORT_SESSIONS:
        return sorted(projects, key=lambda p: -int(getattr(p, "session_count", 0) or 0))
    return list(projects)


def matches_project(project: Any, text: str, flags: set[str]) -> bool:
    if "current" in flags and not getattr(project, "current", False):
        return False
    if "missing" in flags and getattr(project, "exists", True):
        return False
    if not text:
        return True
    haystack = (
        f"{getattr(project, 'name', '')} "
        f"{getattr(project, 'path', '')} "
        f"{getattr(project, 'goal', '')}"
    ).lower()
    return text in haystack


def format_name_cell(project: Any) -> str:
    name = getattr(project, "name", "") or ""
    if not getattr(project, "exists", True):
        return f"[strike dim]{truncate(name, max_chars=28)}[/]  [yellow]{glyph.WARN}[/]"
    return truncate(name, max_chars=28)


def format_when_cell(rel_time: str, bucket_label_key: str | None) -> str:
    if bucket_label_key is not None:
        label = strings.tr(bucket_label_key)
        return f"[dim]{label}[/]\n{rel_time}"
    return rel_time


def format_sessions_cell(project: Any) -> str:
    count = int(getattr(project, "session_count", 0) or 0)
    handoffs = int(getattr(project, "handoff_count", 0) or 0)
    if handoffs > 0:
        return f"{count}  [dim]{glyph.HANDOFF}{handoffs}[/]"
    return str(count)


def format_latest_update(entry: Any) -> str:
    headline = truncate(
        str(
            getattr(entry, "title", "")
            or getattr(entry, "summary", "")
            or getattr(entry, "goal", "")
        ),
        max_chars=220,
    )
    meta_parts: list[str] = []
    provider = str(getattr(entry, "provider", "") or "")
    if provider:
        meta_parts.append(provider)
    ts_start = str(getattr(entry, "ts_start", "") or "")
    if ts_start:
        meta_parts.append(relative_time(ts_start))
    if not meta_parts:
        return headline
    sep = f"  {glyph.SEP_DOT}  "
    return f"{headline}\n[dim]{sep.join(meta_parts)}[/]"


def format_pending_preview(items: tuple[str, ...]) -> str:
    lines = [
        f"{glyph.DOT} {truncate(str(item), max_chars=92)}" for item in items[:PREVIEW_ITEM_LIMIT]
    ]
    if len(items) > PREVIEW_ITEM_LIMIT:
        remaining = len(items) - PREVIEW_ITEM_LIMIT
        lines.append(f"[dim]{glyph.ELLIPSIS} {strings.tr('MORE_ITEMS', count=remaining)}[/]")
    return "\n".join(lines)
