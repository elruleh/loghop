import contextlib
import dataclasses
import re
from pathlib import Path
from typing import Any

from loghop.gittools import GitRepo
from loghop.logging import get_logger
from loghop.store._config import load_config, save_config
from loghop.store._constants import ProjectPaths, project_paths, utc_now
from loghop.store._frontmatter import meta_to_dataclass, parse_frontmatter_text
from loghop.store._io import atomic_write_private_text, project_lock
from loghop.store._models import HandoffMeta, ProjectConfig, SessionMeta
from loghop.store._registry import touch_project
from loghop.store._render import (
    build_context_packet,
    build_resume_packet,
    render_handoff_markdown,
    render_memory,
    render_resume_handoff_markdown,
)

_LOGGER = get_logger()
_HANDOFF_RE = re.compile(r"^H-(\d+)$")
_MAX_HANDOFFS = 20


def _prune_old_handoffs(paths: ProjectPaths, keep: int = _MAX_HANDOFFS) -> None:
    if not paths.handoffs.exists():
        return
    files = sorted(
        paths.handoffs.glob("H-*.md"),
        key=lambda p: _handoff_sort_key(p.stem),
        reverse=True,
    )
    with contextlib.suppress(OSError):
        for old in files[keep:]:
            old.unlink()


def _next_handoff_id(config: ProjectConfig, paths: ProjectPaths) -> tuple[str, int]:
    existing = _max_existing_handoff_number(paths)
    counter = max(config.handoff_counter, existing) + 1
    return f"H-{counter:03d}", counter


def create_handoff(
    root: Path,
    provider: str,
    goal: str,
    *,
    topic_id: str = "",
) -> HandoffMeta:
    return _create_handoff_record(
        root,
        provider,
        goal,
        packet_builder=lambda config, repo: build_context_packet(
            root, config, provider, goal, repo=repo, topic_id=topic_id
        ),
        markdown_builder=render_handoff_markdown,
    )


def _create_handoff_record(
    root: Path,
    provider: str,
    goal: str,
    *,
    packet_builder: Any,
    markdown_builder: Any,
) -> HandoffMeta:
    paths = project_paths(root)
    repo = GitRepo(root)
    with project_lock(paths.dot / ".lock"):
        config = load_config(paths)
        handoff_id, counter = _next_handoff_id(config, paths)
        packet = packet_builder(config, repo)
        from loghop.store._integrity import sign_markdown

        markdown = sign_markdown(root, markdown_builder(handoff_id, packet))
        md_path = paths.handoffs / f"{handoff_id}.md"
        if md_path.exists():
            raise ValueError(f"handoff `{handoff_id}` already exists")
        atomic_write_private_text(md_path, markdown)
        _prune_old_handoffs(paths)
        config = dataclasses.replace(config, handoff_counter=counter)
        save_config(paths, config)
        render_memory(paths, config, repo=repo)
    touch_project(root, bump_handoff=True)
    return HandoffMeta(
        id=handoff_id,
        provider=provider,
        goal=goal,
        ts=packet["ts"],
        path=str(md_path.relative_to(root)),
        topic_id=str((packet.get("topic") or {}).get("id") or ""),
        md_path=md_path,
        markdown=markdown,
        packet=packet,
    )


def update_handoff_status(
    root: Path,
    handoff_id: str,
    *,
    status: str,
    returncode: int | None = None,
) -> HandoffMeta:
    paths = project_paths(root)
    handoff = find_handoff(paths, handoff_id)
    md_path = root / handoff.path
    updates: dict[str, Any] = {
        "status": str(status),
        "updated_at": utc_now(),
    }
    if returncode is not None:
        updates["returncode"] = str(returncode)

    from loghop.store._frontmatter import rewrite_frontmatter

    meta = rewrite_frontmatter(md_path, updates)

    kwargs: dict[str, Any] = {}
    for k, v in meta.items():
        if isinstance(v, str | int | float | bool | type(None)):
            kwargs[k] = v
        else:
            kwargs[k] = str(v)

    return dataclasses.replace(handoff, **kwargs)


def list_handoffs(paths: ProjectPaths, *, provider: str | None = None) -> list[HandoffMeta]:
    if not paths.handoffs.exists():
        return []
    entries: list[HandoffMeta] = []
    for md_path in sorted(paths.handoffs.glob("H-*.md")):
        meta, _ = parse_frontmatter_text(md_path)
        if not meta:
            continue
        if provider and meta.get("provider") != provider:
            continue
        meta["path"] = str(md_path.relative_to(paths.root))

        kwargs = meta_to_dataclass(meta, HandoffMeta)
        if "id" not in kwargs:
            continue

        entries.append(HandoffMeta(**kwargs))
    entries.sort(key=lambda item: _handoff_sort_key(item.id), reverse=True)
    return entries


def find_handoff(paths: ProjectPaths, handoff_id: str) -> HandoffMeta:
    if not _HANDOFF_RE.match(handoff_id):
        raise ValueError(f"invalid handoff id: {handoff_id}")
    md_path = paths.handoffs / f"{handoff_id}.md"
    if not md_path.exists():
        raise ValueError(f"handoff `{handoff_id}` not found")
    meta, _ = parse_frontmatter_text(md_path)
    if not meta:
        raise ValueError(f"handoff `{handoff_id}` has no frontmatter")
    meta["path"] = str(md_path.relative_to(paths.root))

    kwargs = meta_to_dataclass(meta, HandoffMeta)
    return HandoffMeta(**kwargs)


def _max_existing_handoff_number(paths: ProjectPaths) -> int:
    if not paths.handoffs.exists():
        return 0
    numbers = [
        int(match.group(1))
        for path in paths.handoffs.glob("H-*.md")
        if (match := _HANDOFF_RE.match(path.stem))
    ]
    return max(numbers, default=0)


def _handoff_sort_key(handoff_id: str) -> int:
    match = _HANDOFF_RE.match(handoff_id)
    return int(match.group(1)) if match else 0


def create_resume_handoff(
    root: Path,
    provider: str,
    goal: str,
    *,
    previous_session: SessionMeta | None,
    topic_id: str = "",
) -> HandoffMeta:
    return _create_handoff_record(
        root,
        provider,
        goal,
        packet_builder=lambda config, repo: build_resume_packet(
            root,
            config,
            provider,
            goal,
            previous_session=previous_session,
            repo=repo,
            topic_id=topic_id,
        ),
        markdown_builder=render_resume_handoff_markdown,
    )
