"""Loghop store — convenience re-exports for CLI commands and tests.

Each symbol is imported from its canonical sub-module so that:

* The public API surface is discoverable in one place.
* Callers may also import directly from the sub-module for clarity.

Internal modules should import from each other directly rather than
going through this re-export layer.
"""

# --- config ---
from loghop.store._config import default_config, load_config, save_config

# --- constants ---
from loghop.store._constants import ProjectPaths, SessionStatus, project_paths, utc_now

# --- handoff ---
from loghop.store._handoff import (
    create_handoff,
    create_resume_handoff,
    find_handoff,
    list_handoffs,
    update_handoff_status,
)

# --- project ---
from loghop.store._project_init import find_project_root, init_project

# --- registry ---
from loghop.store._registry import delete_project_data

# --- session ---
from loghop.store._session import (
    create_session,
    current_files_changed,
    delete_session,
    find_session,
    finish_session,
    latest_session,
    list_sessions,
)

# --- timeline ---
from loghop.store._timeline import list_timeline_events

# --- topic ---
from loghop.store._topic import (
    clear_active_topic,
    close_topic,
    create_topic,
    find_topic,
    list_topics,
    rename_topic,
    resolve_or_create_topic,
    set_active_topic,
)

__all__ = [
    # constants
    "ProjectPaths",
    "SessionStatus",
    # topic
    "clear_active_topic",
    "close_topic",
    # handoff
    "create_handoff",
    "create_resume_handoff",
    # session
    "create_session",
    "create_topic",
    "current_files_changed",
    # config
    "default_config",
    # project
    "delete_project_data",
    "delete_session",
    "find_handoff",
    "find_project_root",
    "find_session",
    "find_topic",
    "finish_session",
    "init_project",
    "latest_session",
    "list_handoffs",
    "list_sessions",
    # timeline
    "list_timeline_events",
    "list_topics",
    "load_config",
    "project_paths",
    "rename_topic",
    "resolve_or_create_topic",
    "save_config",
    "set_active_topic",
    "update_handoff_status",
    "utc_now",
]
