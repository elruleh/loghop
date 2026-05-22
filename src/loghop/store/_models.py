from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProjectConfig:
    version: int
    project_name: str
    goal: str = ""
    handoff_counter: int = 0
    session_counter: int = 0
    topic_counter: int = 0
    active_topic_id: str = ""
    handoff_patch_lines: int = 160


@dataclass(frozen=True)
class RegistryEntry:
    name: str
    path: str
    registered: str
    last_used: str
    goal: str = ""
    last_session: str = ""
    session_count: int = 0
    handoff_count: int = 0


@dataclass(frozen=True)
class HandoffMeta:
    id: str = ""
    provider: str = ""
    goal: str = ""
    ts: str = ""
    status: str = "created"
    updated_at: str = ""
    returncode: str | None = None
    path: str = ""
    topic_id: str = ""

    # Extra fields for backward compatibility or transient state
    md_path: Path | None = None
    markdown: str = ""
    packet: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionMeta:
    id: str = ""
    provider: str = ""
    goal: str = ""
    handoff_id: str = ""
    topic_id: str = ""
    status: str = "running"
    decisions: list[str] = field(default_factory=list)
    todos_pending: list[str] = field(default_factory=list)
    todos_done: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    summary: str = ""
    ts_start: str = ""
    ts_end: str = ""
    path: str = ""
    output: str = ""
    returncode: str | None = None
    transcript_path: str = ""
    claude_session_id: str = ""
    turns_captured: int | None = None

    # Extra fields for backward compatibility or transient state
    md_path: Path | None = None
    markdown: str = ""


@dataclass(frozen=True)
class TopicMeta:
    id: str = ""
    title: str = ""
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""
    summary: str = ""
    session_ids: list[str] = field(default_factory=list)
    todos_pending: list[str] = field(default_factory=list)

    # Extra fields for backward compatibility or transient state
    path: str = ""
    md_path: Path | None = None
    markdown: str = ""
