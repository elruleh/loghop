import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from loghop.logging import get_logger
from loghop.redact import redact_dict
from loghop.store._constants import ProjectPaths
from loghop.store._frontmatter import parse_frontmatter_text
from loghop.store._io import atomic_write_private_text, safe_read_text
from loghop.store._models import SessionMeta

_LOGGER = get_logger()

SESSION_RE = re.compile(r"^S-(\d+)$")


def session_sort_key(session_id: str) -> int:
    match = SESSION_RE.match(session_id)
    return int(match.group(1)) if match else 0


def sessions_dir_path(paths: ProjectPaths) -> Path:
    return paths.dot / "sessions"


def validated_sessions_dir(paths: ProjectPaths) -> Path:
    sessions_dir = sessions_dir_path(paths)
    if sessions_dir.exists() and sessions_dir.is_symlink():
        raise ValueError("refusing to use a symlinked session directory")
    if sessions_dir.exists() and not sessions_dir.is_dir():
        raise ValueError("invalid session directory")
    return sessions_dir


def rebuild_index(paths: ProjectPaths) -> dict[str, dict[str, Any]]:
    sessions_dir = validated_sessions_dir(paths)
    if not sessions_dir.exists():
        _write_index(paths, {})
        return {}

    sessions_dict = {}
    for md_path in sorted(sessions_dir.glob("S-*.md")):
        try:
            meta, _ = parse_frontmatter_text(md_path)
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "skipping malformed index line",
                exc_info=True,
                extra={"component": "store.index", "path": str(md_path)},
            )
            continue
        if not meta or "id" not in meta:
            continue

        data = dict(meta)
        data.pop("md_path", None)
        data.pop("markdown", None)
        data["path"] = str(md_path.relative_to(paths.root))
        sessions_dict[data["id"]] = redact_dict(data)

    _write_index(paths, sessions_dict)
    return sessions_dict


def _write_index(paths: ProjectPaths, sessions_dict: dict[str, dict[str, Any]]) -> None:
    index_path = paths.dot / "sessions.jsonl"
    # Sort by ID descending for the file? No, sorted() usually defaults to ascending.
    # list_sessions sorts by ID descending.
    # The index file can be sorted ascending, and list_sessions can reverse it.
    lines = [
        json.dumps(s, sort_keys=True)
        for s in sorted(sessions_dict.values(), key=lambda x: session_sort_key(x["id"]))
    ]
    atomic_write_private_text(index_path, "\n".join(lines) + "\n")


def update_index(
    paths: ProjectPaths, session: SessionMeta | None = None, delete_id: str | None = None
) -> None:
    index_path = paths.dot / "sessions.jsonl"
    sessions_dict = {}

    if not index_path.exists():
        sessions_dict = rebuild_index(paths)
    else:
        try:
            content = safe_read_text(index_path)
            for line in content.splitlines():
                if not line.strip():
                    continue
                data = json.loads(line)
                sessions_dict[data["id"]] = data
        except Exception:  # noqa: BLE001
            sessions_dict = rebuild_index(paths)

    if session:
        session_data = asdict(session)
        session_data.pop("md_path", None)
        session_data.pop("markdown", None)
        sessions_dict[session.id] = redact_dict(session_data)

    if delete_id:
        sessions_dict.pop(delete_id, None)

    _write_index(paths, sessions_dict)
