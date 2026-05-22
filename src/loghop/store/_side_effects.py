"""Post-write side effects that span multiple store modules.

These helpers are called after session mutations (create, finish, delete) to
keep the timeline, memory file, and registry in sync.  They live in a
dedicated module to avoid circular imports between ``_session`` and
``_timeline`` / ``_render``.
"""

from pathlib import Path

from loghop.logging import get_logger
from loghop.store._constants import project_paths
from loghop.store._models import SessionMeta

_LOGGER = get_logger()


def refresh_memory_best_effort(root: Path) -> None:
    """Re-render ``loghop.md`` if possible; never raise."""
    try:
        from loghop.store._config import load_config
        from loghop.store._render import render_memory

        paths = project_paths(root)
        render_memory(paths, load_config(paths))
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "failed to refresh loghop memory",
            extra={"component": "side_effects", "path": str(root)},
            exc_info=True,
        )


def append_timeline_best_effort(root: Path, session: SessionMeta) -> str | None:
    """Append a session event to the timeline; return error message on failure."""
    try:
        from loghop.store._timeline import append_session_timeline_event

        append_session_timeline_event(root, session)
        return None
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "failed to append session to timeline",
            extra={
                "component": "side_effects",
                "path": str(root),
                "session_id": session.id,
            },
            exc_info=True,
        )
        return f"timeline append failed for session {session.id}"
