from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from loghop.errors import AUTH_FAILURE_NEEDLES
from loghop.logging import get_logger
from loghop.redact import redact_dict, redact_text
from loghop.store._config import load_config
from loghop.store._constants import (
    _MAX_SESSIONS_SOFT_LIMIT,
    SKIP_FOR_RESUME,
    ProjectPaths,
    SessionStatus,
    project_paths,
    utc_now,
)
from loghop.store._frontmatter import meta_to_dataclass, parse_frontmatter_text
from loghop.store._index import (
    SESSION_RE,
    session_sort_key,
    update_index,
    validated_sessions_dir,
)
from loghop.store._io import (
    _ensure_directory,
    atomic_write_private_text,
    project_lock,
    safe_read_text,
)
from loghop.store._models import ProjectConfig, SessionMeta
from loghop.store._registry import touch_project

_LOGGER = get_logger()
_MAX_FRONTMATTER_OUTPUT_CHARS = 50_000


def _next_session_id(config: ProjectConfig, paths: ProjectPaths) -> tuple[str, int]:
    sessions_dir = validated_sessions_dir(paths)
    existing = _max_existing_session_number(sessions_dir)
    counter = max(config.session_counter, existing) + 1
    return f"S-{counter:03d}", counter


def create_session(
    root: Path,
    *,
    provider: str,
    goal: str,
    handoff_id: str = "",
    topic_id: str = "",
) -> SessionMeta:
    paths = project_paths(root)
    with project_lock(paths.dot / ".lock"):
        sessions_dir = validated_sessions_dir(paths)
        _ensure_directory(sessions_dir)
        config = load_config(paths)
        session_id, counter = _next_session_id(config, paths)
        # Soft limit: warn when approaching unbounded growth.
        if counter > _MAX_SESSIONS_SOFT_LIMIT:
            _LOGGER.warning(
                "session count exceeded soft limit; consider archiving old sessions",
                extra={
                    "component": "session",
                    "session_id": session_id,
                    "count": counter,
                    "limit": _MAX_SESSIONS_SOFT_LIMIT,
                },
            )
        ts = utc_now()
        meta_dict: dict[str, Any] = {
            "id": session_id,
            "provider": provider,
            "goal": goal,
            "handoff_id": handoff_id,
            "topic_id": topic_id,
            "status": SessionStatus.RUNNING,
            "decisions": [],
            "todos_pending": [],
            "todos_done": [],
            "files_changed": [],
            "summary": "",
            "ts_start": ts,
            "ts_end": "",
        }
        md_path = sessions_dir / f"{session_id}.md"
        from loghop.store._integrity import sign_markdown

        markdown = sign_markdown(root, _render_session_markdown(meta_dict))
        atomic_write_private_text(md_path, markdown)

        config = dataclasses.replace(config, session_counter=counter)
        from loghop.store._config import save_config

        save_config(paths, config)

        session = SessionMeta(
            **meta_dict,
            path=str(md_path.relative_to(root)),
            md_path=md_path,
            markdown=markdown,
        )
        update_index(paths, session)

    if topic_id:
        from loghop.store._topic import add_session_to_topic

        add_session_to_topic(root, topic_id, session_id)
    touch_project(root, last_session=session_id, bump_session=True)
    return session


def finish_session(
    root: Path,
    session_id: str,
    *,
    status: str,
    summary: str = "",
    decisions: list[str] | None = None,
    todos_pending: list[str] | None = None,
    todos_done: list[str] | None = None,
    files_changed: list[str] | None = None,
    output: str = "",
    returncode: int | None = None,
    transcript_path: str = "",
    turns_captured: int | None = None,
) -> SessionMeta:
    if not SESSION_RE.match(session_id):
        raise ValueError(f"invalid session id: {session_id}")
    paths = project_paths(root)
    md_path = validated_sessions_dir(paths) / f"{session_id}.md"
    if not md_path.exists():
        raise ValueError(f"session `{session_id}` not found")

    with project_lock(paths.dot / ".lock"):
        meta = _parse_session_meta(md_path, session_id)
        current_status = str(meta.get("status", ""))
        if current_status != str(SessionStatus.RUNNING):
            raise ValueError(f"session `{session_id}` is not running (status={current_status})")
        _apply_session_meta(
            meta,
            status,
            summary,
            decisions,
            todos_pending,
            todos_done,
            files_changed,
            output,
            returncode,
            transcript_path,
            turns_captured,
        )
        from loghop.store._integrity import sign_markdown

        markdown = sign_markdown(root, _render_session_markdown(meta))
        atomic_write_private_text(md_path, markdown)

        kwargs = meta_to_dataclass(meta, SessionMeta)
        kwargs["path"] = str(md_path.relative_to(root))
        session = SessionMeta(**kwargs)
        update_index(paths, session)

    touch_project(root, last_session=session_id)
    _append_timeline_best_effort(root, session)
    _refresh_memory_best_effort(root)
    return session


def _parse_session_meta(md_path: Path, session_id: str) -> dict[str, Any]:
    try:
        meta, _ = parse_frontmatter_text(md_path)
    except (yaml.YAMLError, ValueError) as exc:
        raise ValueError(f"session `{session_id}` has malformed frontmatter: {exc}") from exc
    if not meta:
        raise ValueError(f"session `{session_id}` has no frontmatter")
    return meta


def _apply_session_meta(
    meta: dict[str, Any],
    status: str,
    summary: str,
    decisions: list[str] | None,
    todos_pending: list[str] | None,
    todos_done: list[str] | None,
    files_changed: list[str] | None,
    output: str,
    returncode: int | None,
    transcript_path: str,
    turns_captured: int | None,
) -> None:
    effective_status = str(status)
    known_statuses = {str(s) for s in SessionStatus}
    if effective_status not in known_statuses and effective_status != "ended":
        _LOGGER.warning(
            "unknown session status %r, using as-is",
            effective_status,
            extra={"component": "session"},
        )
    if (
        turns_captured is not None
        and int(turns_captured) == 0
        and not summary
        and effective_status in {"ended", str(SessionStatus.INTERRUPTED)}
    ):
        effective_status = f"{effective_status}_empty"
    meta["status"] = effective_status
    meta["ts_end"] = utc_now()
    _set_if(meta, "summary", summary)
    _set_if_not_none(meta, "decisions", decisions)
    _set_if_not_none(meta, "todos_pending", todos_pending)
    _set_if_not_none(meta, "todos_done", todos_done)
    if files_changed is not None:
        meta["files_changed"] = [redact_text(str(p)) for p in files_changed]
    if returncode is not None:
        meta["returncode"] = str(returncode)
    if output:
        redacted_output = redact_text(output)
        if len(redacted_output) > _MAX_FRONTMATTER_OUTPUT_CHARS:
            redacted_output = redacted_output[:_MAX_FRONTMATTER_OUTPUT_CHARS] + "\n…[truncated]"
        meta["output"] = redacted_output
    _set_if(meta, "transcript_path", transcript_path)
    if turns_captured is not None:
        meta["turns_captured"] = turns_captured


def _set_if(meta: dict[str, Any], key: str, value: str) -> None:
    if value:
        meta[key] = value


def _set_if_not_none(meta: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        meta[key] = value


def _list_from_index(
    index_path: Path, provider: str | None = None, limit: int | None = None
) -> list[SessionMeta]:
    entries: list[SessionMeta] = []
    for line in safe_read_text(index_path).splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        if provider and data.get("provider") != provider:
            continue
        kwargs = meta_to_dataclass(data, SessionMeta)
        entries.append(SessionMeta(**kwargs))
    entries.sort(key=lambda item: session_sort_key(item.id), reverse=True)
    if limit is not None and limit >= 0:
        return entries[:limit]
    return entries


def _list_from_scan(
    paths: ProjectPaths, provider: str | None = None, limit: int | None = None
) -> list[SessionMeta]:
    sessions_dir = validated_sessions_dir(paths)
    if not sessions_dir.exists():
        return []
    scan_entries: list[SessionMeta] = []
    for md_path in sorted(sessions_dir.glob("S-*.md")):
        try:
            meta, _ = parse_frontmatter_text(md_path)
        except OSError:
            _LOGGER.warning(
                "session file unreadable, skipping",
                extra={"component": "session", "path": str(md_path)},
            )
            continue
        if not meta:
            continue
        if provider and meta.get("provider") != provider:
            continue
        meta["path"] = str(md_path.relative_to(paths.root))

        kwargs = meta_to_dataclass(meta, SessionMeta)
        if "id" not in kwargs:
            continue
        scan_entries.append(SessionMeta(**kwargs))
    scan_entries.sort(key=lambda item: session_sort_key(item.id), reverse=True)
    if limit is not None and limit >= 0:
        return scan_entries[:limit]
    return scan_entries


def list_sessions(
    paths: ProjectPaths, *, provider: str | None = None, limit: int | None = None
) -> list[SessionMeta]:
    index_path = paths.dot / "sessions.jsonl"
    if index_path.exists():
        try:
            return _list_from_index(index_path, provider, limit)
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "failed to read session index, falling back to directory scan",
                exc_info=True,
                extra={"component": "session"},
            )

    return _list_from_scan(paths, provider, limit)


def find_session_by_claude_id(paths: ProjectPaths, claude_session_id: str) -> SessionMeta | None:
    """Find the most-recent session with the given claude_session_id."""
    for session in list_sessions(paths):
        if session.claude_session_id == claude_session_id:
            return session
    return None


def find_session(paths: ProjectPaths, session_id: str) -> SessionMeta:
    if not SESSION_RE.match(session_id):
        raise ValueError(f"invalid session id: {session_id}")
    md_path = validated_sessions_dir(paths) / f"{session_id}.md"
    if not md_path.exists():
        raise ValueError(f"session `{session_id}` not found")
    meta, _ = parse_frontmatter_text(md_path)
    meta["path"] = str(md_path.relative_to(paths.root))

    kwargs = meta_to_dataclass(meta, SessionMeta)
    return SessionMeta(**kwargs)


def delete_session(paths: ProjectPaths, session_id: str) -> None:
    if not SESSION_RE.match(session_id):
        raise ValueError(f"invalid session id: {session_id}")
    sessions_dir = validated_sessions_dir(paths)
    md_path = _safe_session_artifact_path(sessions_dir, f"{session_id}.md")
    transcript_paths = [_safe_session_artifact_path(sessions_dir, f"{session_id}.transcript.jsonl")]
    topic_id = ""
    if _path_exists_or_symlink(md_path):
        try:
            meta, _ = parse_frontmatter_text(md_path)
        except (OSError, yaml.YAMLError, ValueError):
            meta = {}
        topic_id = str(meta.get("topic_id") or "")
        raw_transcript = meta.get("transcript_path", "")
        if isinstance(raw_transcript, str) and raw_transcript.strip():
            extra = _safe_transcript_path_from_meta(paths, sessions_dir, session_id, raw_transcript)
            if extra is not None and extra not in transcript_paths:
                transcript_paths.append(extra)
    with project_lock(paths.dot / ".lock"):
        if _path_exists_or_symlink(md_path):
            md_path.unlink()
        for transcript_path in transcript_paths:
            if _path_exists_or_symlink(transcript_path):
                transcript_path.unlink()
        update_index(paths, delete_id=session_id)

    from loghop.store._timeline import remove_session_timeline_events

    remove_session_timeline_events(paths, session_id)
    if topic_id:
        from loghop.store._topic import remove_session_from_topic

        remove_session_from_topic(paths.root, topic_id, session_id)
    from loghop.store._registry import sync_project

    sync_project(paths.root)
    _refresh_memory_best_effort(paths.root)


def _safe_session_artifact_path(sessions_dir: Path, filename: str) -> Path:
    candidate = sessions_dir / filename
    sessions_root = sessions_dir.resolve(strict=False)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(sessions_root)
    except ValueError as exc:
        raise ValueError("refusing to use session path outside .loghop/sessions") from exc
    return candidate


def _safe_transcript_path_from_meta(
    paths: ProjectPaths,
    sessions_dir: Path,
    session_id: str,
    raw_transcript: str,
) -> Path | None:
    raw_path = Path(raw_transcript)
    candidate = raw_path if raw_path.is_absolute() else paths.root / raw_path
    resolved = candidate.resolve(strict=False)
    sessions_root = sessions_dir.resolve(strict=False)
    try:
        resolved.relative_to(sessions_root)
    except ValueError:
        _LOGGER.warning(
            "ignoring unsafe transcript path during session delete",
            extra={
                "component": "session",
                "session_id": session_id,
                "path": raw_transcript,
            },
        )
        return None
    if resolved.name != f"{session_id}.transcript.jsonl":
        _LOGGER.warning(
            "ignoring mismatched transcript path during session delete",
            extra={
                "component": "session",
                "session_id": session_id,
                "path": raw_transcript,
            },
        )
        return None
    return candidate


def _path_exists_or_symlink(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _refresh_memory_best_effort(root: Path) -> None:
    from loghop.store._side_effects import refresh_memory_best_effort

    refresh_memory_best_effort(root)


def _append_timeline_best_effort(root: Path, session: SessionMeta) -> str | None:
    from loghop.store._side_effects import append_timeline_best_effort

    return append_timeline_best_effort(root, session)


def latest_session(paths: ProjectPaths) -> SessionMeta | None:
    sessions = list_sessions(paths)
    return sessions[0] if sessions else None


def latest_useful_session(
    paths: ProjectPaths, *, topic_id: str | None = None
) -> SessionMeta | None:
    sessions = list_sessions(paths)
    for session in sessions:
        if topic_id is not None and str(session.topic_id or "") != topic_id:
            continue
        status = str(session.status or "").lower()
        summary = str(session.summary or "").lower()
        if (
            status in SKIP_FOR_RESUME
            or status.endswith("_empty")
            or _summary_is_auth_failure(summary)
        ):
            continue
        return session
    return None


def _summary_is_auth_failure(summary: str) -> bool:
    return any(needle in summary for needle in AUTH_FAILURE_NEEDLES)


if TYPE_CHECKING:
    from loghop.gittools import GitRepo


def current_files_changed(root: Path, *, repo: GitRepo | None = None) -> list[str]:
    from loghop.gittools import GitRepo
    from loghop.store._security import filter_paths, load_ignore_patterns

    _repo = repo or GitRepo(root)
    try:
        snapshot = _repo.snapshot()
        ignore_patterns = load_ignore_patterns(root)
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:  # noqa: BLE001
        return []
    return filter_paths(snapshot.changed_files, ignore_patterns, root=root)


def _render_list_section(title: str, items: list[Any], prefix: str = "- ") -> list[str]:
    if not items:
        return []
    lines = [f"## {title}", ""]
    lines.extend(f"{prefix}{redact_text(str(item))}" for item in items)
    lines.append("")
    return lines


def _render_session_markdown(meta: dict[str, Any]) -> str:
    frontmatter = redact_dict(
        {k: v for k, v in meta.items() if k not in ("path", "md_path", "markdown")}
    )
    fm_text = yaml.dump(
        frontmatter, sort_keys=True, allow_unicode=True, default_flow_style=False
    ).rstrip()

    lines = [
        "---",
        fm_text,
        "---",
        "",
        f"# Session {meta.get('id')}",
        "",
        f"**Provider:** {meta.get('provider')}  ",
        f"**Goal:** {redact_text(str(meta.get('goal')))}  ",
        f"**Status:** {meta.get('status', '')}  ",
        f"**Started:** {meta.get('ts_start')}  ",
    ]
    if meta.get("ts_end"):
        lines.append(f"**Finished:** {meta['ts_end']}  ")
    if meta.get("returncode") is not None:
        lines.append(f"**Return code:** {meta.get('returncode')}  ")
    if meta.get("handoff_id"):
        lines.append(f"**Handoff:** {meta['handoff_id']}  ")
    lines.append("")
    summary = meta.get("summary", "")
    if summary:
        lines.extend(["## Summary", "", redact_text(summary), ""])
    lines.extend(_render_list_section("Decisions", meta.get("decisions", [])))
    lines.extend(_render_list_section("Completed", meta.get("todos_done", []), prefix="- [x] "))
    lines.extend(
        _render_list_section("TODOs Pending", meta.get("todos_pending", []), prefix="- [ ] ")
    )
    files_changed = meta.get("files_changed", [])
    if files_changed:
        lines.extend(["## Files Changed", ""])
        lines.extend(f"- `{f}`" for f in files_changed)
        lines.append("")
    if meta.get("output"):
        lines.extend(["## Provider Output", "", "```", str(meta["output"]), "```", ""])
    return "\n".join(lines).rstrip() + "\n"


def _max_existing_session_number(sessions_dir: Path) -> int:
    if not sessions_dir.exists():
        return 0
    numbers = [
        int(match.group(1))
        for path in sessions_dir.glob("S-*.md")
        if (match := SESSION_RE.match(path.stem))
    ]
    return max(numbers, default=0)
