import contextlib
import errno
import json
import os
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from loghop.errors import AUTH_FAILURE_NEEDLES
from loghop.logging import get_logger
from loghop.redact import redact_text
from loghop.store._constants import (
    FILE_MODE,
    SKIP_FOR_RESUME,
    ProjectPaths,
    project_paths,
    utc_now,
)
from loghop.store._io import atomic_write_text, project_lock, safe_read_text
from loghop.store._models import SessionMeta

_AUTH_FAILURE_SUMMARY_NEEDLES = AUTH_FAILURE_NEEDLES
_MAX_SUMMARY_CHARS = 1200
_MAX_TIMELINE_MARKDOWN_SUMMARY_CHARS = 700
_LOGGER = get_logger()


def append_session_timeline_event(root: Path, session: SessionMeta) -> None:
    """Append a normalized project-level event for a finished provider run."""
    paths = project_paths(root)
    event = _session_event(session)
    line = json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n"
    with project_lock(paths.dot / ".lock"):
        fd = _open_timeline_for_append(paths.timeline)
        if fd is None:
            return
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)


def recent_timeline_events(
    paths: ProjectPaths, *, limit: int = 8, topic_id: str | None = None
) -> list[dict[str, Any]]:
    events = _read_events(paths)
    if not events:
        events = _legacy_session_events(paths)
    else:
        events = _merge_missing_session_events(paths, events)
    if topic_id is not None:
        events = [event for event in events if str(event.get("topic_id") or "") == topic_id]
    events = [event for event in events if _event_is_useful(event)]
    return events[-limit:]


def list_timeline_events(
    paths: ProjectPaths,
    *,
    provider: str | None = None,
    since: datetime | None = None,
    include_technical: bool = False,
    limit: int | None = None,
    topic_id: str | None = None,
) -> list[dict[str, Any]]:
    events = _read_events(paths)
    if not events:
        events = _legacy_session_events(paths)
    else:
        events = _merge_missing_session_events(paths, events)
    filtered: list[dict[str, Any]] = []
    for event in events:
        if provider and event.get("provider") != provider:
            continue
        if topic_id is not None and str(event.get("topic_id") or "") != topic_id:
            continue
        if since is not None and not _event_after(event, since):
            continue
        if not include_technical and not _event_is_useful(event):
            continue
        filtered.append(event)
    return filtered[-limit:] if limit else filtered


def remove_session_timeline_events(paths: ProjectPaths, session_id: str) -> None:
    with project_lock(paths.dot / ".lock"):
        events = [
            event
            for event in _read_events(paths)
            if str(event.get("session_id") or "") != session_id
        ]
        _write_events(paths, events)


def timeline_markdown(
    events: Iterable[dict[str, Any]], *, title: str = "Project Timeline"
) -> list[str]:
    items = list(events)
    if not items:
        return []
    lines = [f"## {title}", ""]
    for event in items:
        lines.extend(_event_markdown(event))
    return lines


def _session_event(session: SessionMeta) -> dict[str, Any]:
    return {
        "ts": session.ts_end or utc_now(),
        "kind": "session",
        "session_id": session.id,
        "provider": session.provider,
        "status": session.status,
        "goal": redact_text(session.goal or ""),
        "summary": _clip(redact_text(session.summary or ""), max_chars=_MAX_SUMMARY_CHARS),
        "decisions": _redacted_list(session.decisions),
        "todos_done": _redacted_list(session.todos_done),
        "todos_pending": _redacted_list(session.todos_pending),
        "files_changed": _redacted_list((session.files_changed or [])[:12]),
        "turns_captured": session.turns_captured,
        "transcript_path": session.transcript_path,
        "session_path": session.path,
        "handoff_id": session.handoff_id,
        "topic_id": session.topic_id,
        "returncode": session.returncode,
    }


def _read_events(paths: ProjectPaths) -> list[dict[str, Any]]:
    if _timeline_is_symlink(paths.timeline, action="read"):
        return []
    try:
        raw = safe_read_text(paths.timeline)
    except OSError:
        return []
    events: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            events.append(data)
    return events


def _write_events(paths: ProjectPaths, events: list[dict[str, Any]]) -> None:
    if _timeline_is_symlink(paths.timeline, action="write"):
        return
    text = "".join(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n" for event in events)
    atomic_write_text(paths.timeline, text, file_mode=FILE_MODE)


def _open_timeline_for_append(path: Path) -> int | None:
    if _timeline_is_symlink(path, action="append"):
        return None
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        return os.open(path, flags, FILE_MODE)
    except OSError as exc:
        if exc.errno == errno.ELOOP or _timeline_is_symlink(path, action="append"):
            return None
        raise


def _timeline_is_symlink(path: Path, *, action: str) -> bool:
    try:
        unsafe = path.is_symlink()
    except OSError:
        unsafe = True
    if unsafe:
        _LOGGER.warning(
            "refusing to %s symlinked timeline file",
            action,
            extra={"component": "timeline", "path": str(path)},
        )
    return unsafe


def _legacy_session_events(paths: ProjectPaths) -> list[dict[str, Any]]:
    from loghop.store._session import list_sessions

    return [_session_event(session) for session in reversed(list_sessions(paths))]


def _merge_missing_session_events(
    paths: ProjectPaths, events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    seen = {str(event.get("session_id") or "") for event in events if event.get("session_id")}
    missing = [
        event
        for event in _legacy_session_events(paths)
        if str(event.get("session_id") or "") not in seen
        and str(event.get("status") or "") != "running"
    ]
    if not missing:
        return events
    return sorted([*events, *missing], key=_event_sort_key)


def _event_sort_key(event: dict[str, Any]) -> tuple[str, int]:
    ts = str(event.get("ts") or "")
    session_id = str(event.get("session_id") or "")
    number = 0
    if session_id.startswith("S-"):
        with contextlib.suppress(ValueError):
            number = int(session_id[2:])
    return (ts, number)


def _event_is_useful(event: dict[str, Any]) -> bool:
    status = str(event.get("status") or "").lower()
    summary = str(event.get("summary") or "").lower()
    return (
        status not in SKIP_FOR_RESUME
        and not status.endswith("_empty")
        and not any(needle in summary for needle in _AUTH_FAILURE_SUMMARY_NEEDLES)
    )


def _event_after(event: dict[str, Any], since: datetime) -> bool:
    ts = str(event.get("ts") or "")
    if not ts:
        return True
    try:
        parsed = datetime.fromisoformat(ts)
    except ValueError:
        return True
    return parsed >= since


def _event_markdown(event: dict[str, Any]) -> list[str]:
    session_id = str(event.get("session_id") or "?")
    provider = str(event.get("provider") or "?")
    status = str(event.get("status") or "?")
    ts = str(event.get("ts") or "")
    summary = _clip(
        str(event.get("summary") or "").strip(),
        max_chars=_MAX_TIMELINE_MARKDOWN_SUMMARY_CHARS,
    )
    lines = [f"- `{session_id}` [{provider}] {status}" + (f" · {ts}" if ts else "")]
    if summary:
        lines.append(f"  Summary: {summary}")
    decisions = _list_value(event.get("decisions"))
    if decisions:
        lines.append("  Decisions:")
        lines.extend(f"  - {item}" for item in decisions[:5])
    pending = _list_value(event.get("todos_pending"))
    if pending:
        lines.append("  Pending:")
        lines.extend(f"  - [ ] {item}" for item in pending[:5])
    done = _list_value(event.get("todos_done"))
    if done:
        lines.append("  Completed:")
        lines.extend(f"  - [x] {item}" for item in done[:5])
    files = _list_value(event.get("files_changed"))
    if files:
        lines.append(f"  Files: {', '.join(files[:6])}")
    lines.append("")
    return lines


def _redacted_list(items: Iterable[object]) -> list[str]:
    return [redact_text(str(item)) for item in items if str(item).strip()]


def _list_value(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _clip(text: str, *, max_chars: int) -> str:
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[: max_chars - 1].rstrip() + "…"
