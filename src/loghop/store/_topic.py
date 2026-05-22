from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any

import yaml

from loghop.errors import E_INVALID_INPUT, LoghopError
from loghop.redact import redact_text
from loghop.store._config import load_config, save_config
from loghop.store._constants import ProjectPaths, project_paths, utc_now
from loghop.store._frontmatter import meta_to_dataclass, parse_frontmatter_text, rewrite_frontmatter
from loghop.store._io import atomic_write_private_text, project_lock
from loghop.store._models import TopicMeta

TOPIC_RE = re.compile(r"^T-(\d+)$")


def validated_topics_dir(paths: ProjectPaths) -> Path:
    topics_dir = paths.topics
    if topics_dir.exists() and topics_dir.is_symlink():
        raise ValueError("refusing to use a symlinked topic directory")
    if topics_dir.exists() and not topics_dir.is_dir():
        raise ValueError("invalid topic directory")
    return topics_dir


def _topic_sort_key(topic_id: str) -> int:
    match = TOPIC_RE.match(topic_id)
    return int(match.group(1)) if match else 0


def _next_topic_id(paths: ProjectPaths) -> tuple[str, int]:
    config = load_config(paths)
    existing = _max_existing_topic_number(paths)
    counter = max(config.topic_counter, existing) + 1
    return f"T-{counter:03d}", counter


def create_topic(root: Path, title: str, *, set_active: bool = True) -> TopicMeta:
    clean_title = _validate_title(title)
    paths = project_paths(root)
    with project_lock(paths.dot / ".lock"):
        topics_dir = validated_topics_dir(paths)
        topics_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        topic_id, counter = _next_topic_id(paths)
        now = utc_now()
        meta: dict[str, Any] = {
            "id": topic_id,
            "title": clean_title,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "summary": "",
            "session_ids": [],
            "todos_pending": [],
        }
        md_path = topics_dir / f"{topic_id}.md"
        markdown = _render_topic_markdown(meta)
        atomic_write_private_text(md_path, markdown)

        config = load_config(paths)
        config = dataclasses.replace(
            config,
            topic_counter=counter,
            active_topic_id=topic_id if set_active else config.active_topic_id,
        )
        save_config(paths, config)

    return _topic_from_meta(root, md_path, meta, markdown)


def list_topics(paths: ProjectPaths) -> list[TopicMeta]:
    topics_dir = validated_topics_dir(paths)
    if not topics_dir.exists():
        return []
    entries: list[TopicMeta] = []
    for md_path in sorted(topics_dir.glob("T-*.md")):
        try:
            meta, markdown_lines = parse_frontmatter_text(md_path)
        except (OSError, yaml.YAMLError, ValueError):
            continue
        if not meta:
            continue
        meta["path"] = str(md_path.relative_to(paths.root))
        kwargs = meta_to_dataclass(meta, TopicMeta)
        if "id" not in kwargs:
            continue
        entries.append(TopicMeta(**kwargs, md_path=md_path, markdown="\n".join(markdown_lines)))
    entries.sort(
        key=lambda topic: (
            0 if topic.status == "closed" else 1,
            topic.updated_at or topic.created_at,
            _topic_sort_key(topic.id),
        ),
        reverse=True,
    )
    return entries


def find_topic(paths: ProjectPaths, topic_id: str) -> TopicMeta:
    _validate_topic_id(topic_id)
    md_path = validated_topics_dir(paths) / f"{topic_id}.md"
    if not md_path.exists():
        raise LoghopError(f"topic `{topic_id}` not found", code=E_INVALID_INPUT)
    meta, body_lines = parse_frontmatter_text(md_path)
    meta["path"] = str(md_path.relative_to(paths.root))
    kwargs = meta_to_dataclass(meta, TopicMeta)
    return TopicMeta(**kwargs, md_path=md_path, markdown="\n".join(body_lines))


def set_active_topic(root: Path, topic_id: str) -> TopicMeta:
    paths = project_paths(root)
    topic = find_topic(paths, topic_id)
    if topic.status == "closed":
        raise LoghopError(f"topic `{topic_id}` is closed", code=E_INVALID_INPUT)
    with project_lock(paths.dot / ".lock"):
        config = dataclasses.replace(load_config(paths), active_topic_id=topic_id)
        save_config(paths, config)
    return topic


def clear_active_topic(root: Path) -> None:
    paths = project_paths(root)
    with project_lock(paths.dot / ".lock"):
        save_config(paths, dataclasses.replace(load_config(paths), active_topic_id=""))


def close_topic(root: Path, topic_id: str) -> TopicMeta:
    paths = project_paths(root)
    topic = _rewrite_topic(root, topic_id, {"status": "closed", "updated_at": utc_now()})
    config = load_config(paths)
    if config.active_topic_id == topic_id:
        save_config(paths, dataclasses.replace(config, active_topic_id=""))
    return topic


def rename_topic(root: Path, topic_id: str, title: str) -> TopicMeta:
    return _rewrite_topic(
        root, topic_id, {"title": _validate_title(title), "updated_at": utc_now()}
    )


def resolve_or_create_topic(
    root: Path,
    *,
    goal: str,
    explicit_topic_id: str = "",
    new_topic: bool = False,
) -> TopicMeta:
    paths = project_paths(root)
    if explicit_topic_id:
        return set_active_topic(root, explicit_topic_id)
    if new_topic:
        return create_topic(root, _title_from_goal(goal), set_active=True)
    config = load_config(paths)
    if config.active_topic_id:
        try:
            topic = find_topic(paths, config.active_topic_id)
            if topic.status != "closed":
                return topic
        except (LoghopError, ValueError):
            clear_active_topic(root)
    normalized_goal = _normalize_title(goal)
    if normalized_goal:
        for topic in list_topics(paths):
            if topic.status != "closed" and _normalize_title(topic.title) == normalized_goal:
                set_active_topic(root, topic.id)
                return topic
    return create_topic(root, _title_from_goal(goal), set_active=True)


def remove_session_from_topic(root: Path, topic_id: str, session_id: str) -> TopicMeta | None:
    if not topic_id:
        return None
    paths = project_paths(root)
    topic = find_topic(paths, topic_id)
    session_ids = [sid for sid in list(topic.session_ids or []) if sid != session_id]
    return _rewrite_topic(
        root,
        topic_id,
        {
            "session_ids": session_ids,
            "updated_at": utc_now(),
        },
    )


def add_session_to_topic(root: Path, topic_id: str, session_id: str) -> TopicMeta | None:
    if not topic_id:
        return None
    paths = project_paths(root)
    topic = find_topic(paths, topic_id)
    session_ids = list(topic.session_ids or [])
    if session_id not in session_ids:
        session_ids.append(session_id)
    summary = topic.summary
    return _rewrite_topic(
        root,
        topic_id,
        {
            "session_ids": session_ids,
            "summary": summary,
            "updated_at": utc_now(),
        },
    )


def _rewrite_topic(root: Path, topic_id: str, updates: dict[str, Any]) -> TopicMeta:
    paths = project_paths(root)
    _validate_topic_id(topic_id)
    md_path = validated_topics_dir(paths) / f"{topic_id}.md"
    with project_lock(paths.dot / ".lock"):
        meta = rewrite_frontmatter(md_path, updates)
        parsed, body_lines = parse_frontmatter_text(md_path)
    merged = {**meta, **parsed, "path": str(md_path.relative_to(root))}
    kwargs = meta_to_dataclass(merged, TopicMeta)
    return TopicMeta(**kwargs, md_path=md_path, markdown="\n".join(body_lines))


def _topic_from_meta(root: Path, md_path: Path, meta: dict[str, Any], markdown: str) -> TopicMeta:
    data = dict(meta)
    data["path"] = str(md_path.relative_to(root))
    kwargs = meta_to_dataclass(data, TopicMeta)
    return TopicMeta(**kwargs, md_path=md_path, markdown=markdown)


def _render_topic_markdown(meta: dict[str, Any]) -> str:
    frontmatter = yaml.dump(
        meta, sort_keys=True, allow_unicode=True, default_flow_style=False
    ).rstrip()
    lines = [
        "---",
        frontmatter,
        "---",
        "",
        f"# Topic {meta.get('id')}: {redact_text(str(meta.get('title') or ''))}",
        "",
        f"**Status:** {meta.get('status', '')}  ",
        f"**Created:** {meta.get('created_at', '')}  ",
        f"**Updated:** {meta.get('updated_at', '')}  ",
        "",
    ]
    session_ids = meta.get("session_ids") or []
    if session_ids:
        lines.extend(["## Sessions", ""])
        lines.extend(f"- `{session_id}`" for session_id in session_ids)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _max_existing_topic_number(paths: ProjectPaths) -> int:
    topics_dir = validated_topics_dir(paths)
    if not topics_dir.exists():
        return 0
    numbers = [
        int(match.group(1))
        for path in topics_dir.glob("T-*.md")
        if (match := TOPIC_RE.match(path.stem))
    ]
    return max(numbers, default=0)


def _validate_topic_id(topic_id: str) -> str:
    if not TOPIC_RE.match(topic_id):
        raise LoghopError(f"invalid topic id: {topic_id}", code=E_INVALID_INPUT)
    return topic_id


def _validate_title(title: str) -> str:
    clean = redact_text(str(title or "").strip())
    if not clean:
        raise LoghopError("topic title is required", code=E_INVALID_INPUT)
    if "\x00" in clean or "\n" in clean or "\r" in clean:
        raise LoghopError("topic title must be a single line", code=E_INVALID_INPUT)
    return clean[:200]


def _normalize_title(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _title_from_goal(goal: str) -> str:
    return str(goal or "Ad hoc session").strip() or "Ad hoc session"
