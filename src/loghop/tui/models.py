from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TuiProject:
    name: str
    path: Path
    goal: str
    registered: str
    last_used: str
    last_session: str
    session_count: int
    handoff_count: int
    exists: bool
    current: bool = False


@dataclass(frozen=True)
class _TuiEntry:
    """Shared fields between sessions and timeline events."""

    id: str
    provider: str
    goal: str
    status: str
    summary: str
    ts_start: str
    ts_end: str
    path: Path
    handoff_id: str = ""
    topic_id: str = ""
    returncode: int | None = None
    turns_captured: int | None = None
    files_changed: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    todos_pending: tuple[str, ...] = ()
    todos_done: tuple[str, ...] = ()
    transcript_path: str = ""
    conversation_excerpt: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class TuiSession(_TuiEntry):
    pass


@dataclass(frozen=True)
class TuiTimelineEvent(_TuiEntry):
    session_id: str = ""
    title: str = ""
    kind: str = "timeline"
    is_live: bool = False


PROVIDER_SHORTCUTS: dict[str, str] = {
    "claude": "c",
    "codex": "o",
}


@dataclass(frozen=True)
class TuiProvider:
    name: str
    installed: bool
    path: Path | None
    default: bool = False


@dataclass(frozen=True)
class TuiTopic:
    id: str
    title: str
    status: str
    created_at: str
    updated_at: str
    session_count: int
    active: bool = False
