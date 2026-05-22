from pathlib import Path
from typing import Any

from loghop.providers import SUPPORTED_PROVIDER_NAMES, detect_all
from loghop.store import find_project_root, list_sessions, list_timeline_events, project_paths
from loghop.store._config import load_config
from loghop.store._models import RegistryEntry, SessionMeta
from loghop.store._registry import load_registry
from loghop.store._topic import list_topics
from loghop.tui.models import (
    TuiProject,
    TuiProvider,
    TuiSession,
    TuiTimelineEvent,
    TuiTopic,
)


class TuiService:
    """Read-only adapter between loghop's storage APIs and TUI view models."""

    def __init__(self, cwd: Path | None = None) -> None:
        self.cwd = (cwd or Path.cwd()).resolve()

    def current_project_root(self) -> Path | None:
        return find_project_root(self.cwd)

    def projects(self) -> list[TuiProject]:
        current_root = self.current_project_root()
        projects = [_project_from_registry(entry, current_root) for entry in load_registry()]
        projects.sort(key=lambda project: project.last_used, reverse=True)
        return projects

    def sessions(
        self,
        root: Path | None = None,
        *,
        provider: str | None = None,
        limit: int | None = None,
    ) -> list[TuiSession]:
        project_root = self._resolve_root(root)
        if project_root is None:
            return []
        return [
            _session_from_store(project_root, item)
            for item in list_sessions(project_paths(project_root), provider=provider, limit=limit)
        ]

    def timeline(
        self,
        root: Path | None = None,
        *,
        provider: str | None = None,
        limit: int | None = None,
    ) -> list[TuiTimelineEvent]:
        project_root = self._resolve_root(root)
        if project_root is None:
            return []
        paths = project_paths(project_root)
        events: list[TuiTimelineEvent] = []
        seen_ids = set()
        for item in list_timeline_events(
            paths, provider=provider, include_technical=True, limit=limit
        ):
            event = _timeline_event_from_store(project_root, item)
            if event.id and event.id in seen_ids:
                continue
            if event.id:
                seen_ids.add(event.id)
            events.append(event)
        seen_session_ids = {event.session_id for event in events if event.session_id}
        for session in list_sessions(paths, provider=provider):
            if session.status != "running" or session.id in seen_session_ids:
                continue
            events.append(_timeline_event_from_running_session(project_root, session))
        events.sort(key=_timeline_sort_key, reverse=True)
        return events[:limit] if limit is not None else events

    def topics(self, root: Path | None = None) -> list[TuiTopic]:
        project_root = self._resolve_root(root)
        if project_root is None:
            return []
        paths = project_paths(project_root)
        active_topic_id = load_config(paths).active_topic_id
        return [
            TuiTopic(
                id=topic.id,
                title=topic.title,
                status=topic.status,
                created_at=topic.created_at,
                updated_at=topic.updated_at,
                session_count=len(topic.session_ids or []),
                active=topic.id == active_topic_id,
            )
            for topic in list_topics(paths)
        ]

    def providers(self, root: Path | None = None) -> list[TuiProvider]:
        project_root = self._resolve_root(root)
        if project_root is None:
            return []
        default_provider = self.default_provider(project_root)
        detections = detect_all()
        return [
            TuiProvider(
                name=name,
                installed=detections[name].installed,
                path=Path(detections[name].path) if detections[name].path else None,
                default=name == default_provider,
            )
            for name in SUPPORTED_PROVIDER_NAMES
        ]

    def default_provider(self, root: Path | None = None) -> str | None:
        from loghop.cli_commands._helpers import resolve_default_provider

        project_root = self._resolve_root(root)
        if project_root is None:
            return None
        return resolve_default_provider(project_root)

    def _resolve_root(self, root: Path | None) -> Path | None:
        if root is None:
            return self.current_project_root()
        candidate = root.expanduser().resolve()
        return candidate if (candidate / ".loghop" / "config.toml").exists() else None

    def conversation_excerpt(
        self, root: Path, session_id: str, *, limit: int = 4
    ) -> tuple[tuple[str, str], ...]:
        return _conversation_excerpt(root, session_id, limit=limit)


def _project_from_registry(entry: RegistryEntry, current_root: Path | None) -> TuiProject:
    path = Path(entry.path).expanduser()
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    return TuiProject(
        name=entry.name or resolved.name,
        path=resolved,
        goal=entry.goal or "",
        registered=entry.registered or "",
        last_used=entry.last_used or "",
        last_session=entry.last_session or "",
        session_count=_int_or_zero(entry.session_count),
        handoff_count=_int_or_zero(entry.handoff_count),
        exists=(resolved / ".loghop" / "config.toml").exists(),
        current=current_root == resolved,
    )


def _session_from_store(root: Path, item: SessionMeta) -> TuiSession:
    return TuiSession(
        id=item.id or "",
        provider=item.provider or "",
        goal=item.goal or "",
        status=item.status or "",
        summary=item.summary or "",
        ts_start=item.ts_start or "",
        ts_end=item.ts_end or "",
        path=root / (item.path or ""),
        handoff_id=item.handoff_id or "",
        topic_id=item.topic_id or "",
        returncode=_optional_int(item.returncode),
        turns_captured=_optional_int(item.turns_captured),
        files_changed=_string_tuple(item.files_changed),
        decisions=_string_tuple(item.decisions),
        todos_pending=_string_tuple(item.todos_pending),
        todos_done=_string_tuple(item.todos_done),
        transcript_path=item.transcript_path or "",
        conversation_excerpt=(),
    )


def _timeline_event_from_store(root: Path, item: dict[str, Any]) -> TuiTimelineEvent:
    session_id = str(item.get("session_id") or "")
    summary = str(item.get("summary") or "")
    goal = str(item.get("goal") or "")
    session_path = str(item.get("session_path") or "")
    return TuiTimelineEvent(
        id=session_id or str(item.get("ts") or ""),
        session_id=session_id,
        provider=str(item.get("provider") or ""),
        goal=goal,
        status=str(item.get("status") or ""),
        summary=summary,
        title=_timeline_title(summary, goal, session_id),
        ts_start=str(item.get("ts") or ""),
        ts_end=str(item.get("ts") or ""),
        path=root / session_path if session_path else root,
        kind=str(item.get("kind") or "timeline"),
        turns_captured=_optional_int(item.get("turns_captured")),
        files_changed=_string_tuple(item.get("files_changed")),
        decisions=_string_tuple(item.get("decisions")),
        todos_pending=_string_tuple(item.get("todos_pending")),
        todos_done=_string_tuple(item.get("todos_done")),
        transcript_path=str(item.get("transcript_path") or ""),
        handoff_id=str(item.get("handoff_id") or ""),
        topic_id=str(item.get("topic_id") or ""),
        returncode=_optional_int(item.get("returncode")),
        conversation_excerpt=(),
        is_live=False,
    )


def _timeline_event_from_running_session(root: Path, item: SessionMeta) -> TuiTimelineEvent:
    summary = item.summary or ""
    goal = item.goal or ""
    return TuiTimelineEvent(
        id=item.id or "",
        session_id=item.id or "",
        provider=item.provider or "",
        goal=goal,
        status=item.status or "",
        summary=summary,
        title=_timeline_title(summary, goal, item.id or ""),
        ts_start=item.ts_start or "",
        ts_end=item.ts_end or "",
        path=root / (item.path or ""),
        kind="running",
        handoff_id=item.handoff_id or "",
        topic_id=item.topic_id or "",
        returncode=_optional_int(item.returncode),
        turns_captured=_optional_int(item.turns_captured),
        files_changed=_string_tuple(item.files_changed),
        decisions=_string_tuple(item.decisions),
        todos_pending=_string_tuple(item.todos_pending),
        todos_done=_string_tuple(item.todos_done),
        transcript_path=item.transcript_path or "",
        conversation_excerpt=(),
        is_live=True,
    )


def _timeline_title(summary: str, goal: str, session_id: str) -> str:
    for value in (summary, goal, session_id):
        stripped = value.strip()
        if stripped:
            return stripped
    return "Untitled run"


def _timeline_sort_key(item: TuiTimelineEvent) -> tuple[str, int, int]:
    return (
        item.ts_start or item.ts_end or "",
        1 if item.is_live else 0,
        _session_number(item.session_id),
    )


def _session_number(session_id: str) -> int:
    if not session_id.startswith("S-"):
        return 0
    try:
        return int(session_id[2:])
    except ValueError:
        return 0


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _conversation_excerpt(
    root: Path, session_id: str, *, limit: int = 4
) -> tuple[tuple[str, str], ...]:
    if not session_id:
        return ()
    try:
        from loghop.autocapture import last_turns

        turns = last_turns(root, session_id, limit=limit)
    except Exception:  # noqa: BLE001
        return ()
    return tuple((turn.role, turn.text) for turn in turns if turn.text.strip())


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _int_or_zero(value: object) -> int:
    parsed = _optional_int(value)
    if parsed is None:
        return 0
    return parsed
