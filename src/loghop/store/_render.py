from pathlib import Path
from typing import Any

import yaml

from loghop.gittools import GitRepo
from loghop.redact import redact_text
from loghop.store._constants import FILE_MODE, ProjectPaths, project_paths, utc_now
from loghop.store._io import atomic_write_text
from loghop.store._models import ProjectConfig, SessionMeta
from loghop.store._security import filter_paths, load_ignore_patterns
from loghop.store._timeline import recent_timeline_events, timeline_markdown

_MEMORY_TITLE = "Project Memory"
_HANDOFF_TITLE = "Project Handoff"
_PROJECT_SUMMARY_TITLE = "Project Summary"
_REPOSITORY_TITLE = "Repository"
_HANDOFF_CONTEXT_TITLE = "Handoff Context"
_LATEST_SESSION_TITLE = "Latest Session"
_RECENT_SESSIONS_TITLE = "Recent Sessions"
_PREVIOUS_EXCERPT_TITLE = "Previous Session Excerpt"


def render_memory(
    paths: ProjectPaths,
    config: ProjectConfig,
    *,
    repo: GitRepo | None = None,
) -> None:
    _repo = repo or GitRepo.from_cwd(paths.root) or GitRepo(paths.root)
    snapshot = _repo.snapshot()
    ignore_patterns = load_ignore_patterns(paths.root)
    changed_files = filter_paths(snapshot.changed_files, ignore_patterns, root=paths.root)
    ignored_count = max(0, len(snapshot.changed_files) - len(changed_files))
    goal = config.goal or ""
    lines = [
        f"# {_MEMORY_TITLE}",
        "",
        "## Goal",
        goal or "- No goal set yet.",
        "",
        f"## {_REPOSITORY_TITLE}",
        f"- Branch: {snapshot.branch or 'n/a'}",
        f"- Head: {snapshot.head or 'n/a'}",
        f"- Default branch: {snapshot.default_branch or 'n/a'}",
        f"- Dirty: {'yes' if snapshot.dirty else 'no'}",
        f"- Changed files: {len(changed_files)}",
    ]
    if ignored_count:
        lines.append(f"- Ignored by .loghopignore: {ignored_count}")
    lines.extend(f"  - {path}" for path in changed_files[:10])
    if len(changed_files) > 10:  # noqa: PLR2004
        lines.append(f"  - ... {len(changed_files) - 10} more")
    lines.append("")
    lines.extend(_last_session_section(paths))
    lines.extend(_timeline_section(paths))
    atomic_write_text(
        paths.memory,
        redact_text("\n".join(lines).rstrip() + "\n"),
        file_mode=FILE_MODE,
    )


def _last_session_section(paths: ProjectPaths) -> list[str]:
    from loghop.store._session import latest_useful_session

    session = latest_useful_session(paths)
    if not session:
        return []
    lines = [
        f"## {_LATEST_SESSION_TITLE}",
        f"- ID: {session.id or '?'}",
        f"- Provider: {session.provider or '?'}",
        f"- Status: {session.status or '?'}",
    ]
    summary = session.summary
    if summary:
        lines.append(f"- Summary: {redact_text(str(summary))}")
    todos_pending = session.todos_pending
    if todos_pending and isinstance(todos_pending, list):
        lines.append(f"- TODOs pending: {len(todos_pending)}")
        lines.extend(f"  - [ ] {redact_text(str(t))}" for t in todos_pending[:5])
    lines.append("")
    return lines


def _timeline_section(paths: ProjectPaths) -> list[str]:
    events = recent_timeline_events(paths, limit=5)
    return timeline_markdown(events, title=_RECENT_SESSIONS_TITLE)


def build_context_packet(
    root: Path,
    config: ProjectConfig,
    provider: str,
    goal: str,
    *,
    repo: GitRepo | None = None,
    topic_id: str = "",
) -> dict[str, Any]:
    _repo = repo or GitRepo(root)
    snapshot = _repo.snapshot()
    ignore_patterns = load_ignore_patterns(root)
    changed_files = filter_paths(snapshot.changed_files, ignore_patterns, root=root)
    staged = filter_paths(snapshot.staged, ignore_patterns, root=root)
    unstaged = filter_paths(snapshot.unstaged, ignore_patterns, root=root)
    untracked = filter_paths(snapshot.untracked, ignore_patterns, root=root)
    patch = _repo.diff_for_files(changed_files, max_lines=config.handoff_patch_lines)
    ignored_count = max(0, len(snapshot.changed_files) - len(changed_files))
    topic = _topic_packet(root, topic_id)
    return {
        "provider": provider,
        "goal": goal,
        "ts": utc_now(),
        "timeline": recent_timeline_events(project_paths(root), limit=8),
        "topic": topic,
        "topic_timeline": recent_timeline_events(project_paths(root), limit=8, topic_id=topic_id)
        if topic_id
        else [],
        "context": {
            "changed_files_total": len(snapshot.changed_files),
            "changed_files_included": len(changed_files),
            "changed_files_ignored": ignored_count,
            "patch_truncated": "... patch truncated ..." in patch,
        },
        "project": {
            "name": config.project_name or root.name,
            "overview": config.goal,
        },
        "repo_state": {
            **snapshot.to_dict(),
            "changed_files": changed_files,
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
        },
        "patch": patch,
    }


def _topic_packet(root: Path, topic_id: str) -> dict[str, Any]:
    if not topic_id:
        return {}
    try:
        from loghop.store._topic import find_topic

        topic = find_topic(project_paths(root), topic_id)
    except Exception:  # noqa: BLE001
        return {}
    return {
        "id": topic.id,
        "title": topic.title,
        "status": topic.status,
        "summary": topic.summary,
        "session_ids": topic.session_ids,
        "todos_pending": topic.todos_pending,
    }


def render_handoff_markdown(handoff_id: str, packet: dict[str, Any]) -> str:
    repo = packet["repo_state"]
    overview = packet["project"]["overview"] or "- Overview not set yet."

    metadata = {
        "id": handoff_id,
        "ts": packet["ts"],
        "provider": packet["provider"],
        "goal": packet["goal"],
        "status": "built",
        "topic_id": str((packet.get("topic") or {}).get("id") or ""),
    }
    lines = [
        "---",
        yaml.dump(
            metadata,
            sort_keys=True,
            allow_unicode=True,
            default_flow_style=False,
        ).rstrip(),
        "---",
        "",
        f"# {_HANDOFF_TITLE}",
        "",
        "## Goal",
        packet["goal"],
        "",
        f"## {_PROJECT_SUMMARY_TITLE}",
        overview,
        "",
        f"## {_REPOSITORY_TITLE}",
        f"- Branch: {repo.get('branch') or 'n/a'}",
        f"- Head: {repo.get('head') or 'n/a'}",
        f"- Dirty: {'yes' if repo.get('dirty') else 'no'}",
        f"- Default branch: {repo.get('default_branch') or 'n/a'}",
        "",
        f"## {_HANDOFF_CONTEXT_TITLE}",
        f"- Changed files included: {packet['context']['changed_files_included']}",
        f"- Changed files ignored: {packet['context']['changed_files_ignored']}",
        f"- Patch truncated: {'yes' if packet['context']['patch_truncated'] else 'no'}",
        "",
    ]
    lines.extend(_topic_context_markdown(packet))
    lines.extend(timeline_markdown(packet.get("timeline") or []))
    lines.append("## Changed Files")
    changed = packet["repo_state"]["changed_files"]
    if changed:
        lines.extend(f"- {path}" for path in changed)
    else:
        lines.append("- No pending file changes.")
    if packet.get("patch"):
        lines.extend(["", "## Patch", "```diff", packet["patch"], "```"])
    return redact_text("\n".join(lines).rstrip() + "\n")


def _topic_context_markdown(packet: dict[str, Any]) -> list[str]:
    topic = packet.get("topic") or {}
    if not isinstance(topic, dict) or not topic.get("id"):
        return []
    lines = ["## Topic Context", ""]
    lines.append(f"- Topic: `{topic.get('id')}` {topic.get('title')}")
    lines.append(f"- Status: {topic.get('status') or 'active'}")
    raw_session_ids = topic.get("session_ids")
    session_ids: list[object] = raw_session_ids if isinstance(raw_session_ids, list) else []
    lines.append(f"- Sessions in topic: {len(session_ids)}")
    summary = str(topic.get("summary") or "").strip()
    if summary:
        lines.extend(["", f"Summary: {redact_text(summary)}"])
    pending = topic.get("todos_pending") if isinstance(topic.get("todos_pending"), list) else []
    if pending:
        lines.extend(["", "Pending:"])
        lines.extend(f"- [ ] {redact_text(str(item))}" for item in pending[:5])
    topic_timeline = packet.get("topic_timeline") or []
    if topic_timeline:
        lines.extend([""])
        lines.extend(timeline_markdown(topic_timeline, title="Topic Timeline"))
    else:
        lines.append("")
    return lines


def build_resume_packet(
    root: Path,
    config: ProjectConfig,
    provider: str,
    goal: str,
    *,
    previous_session: SessionMeta | None = None,
    repo: GitRepo | None = None,
    topic_id: str = "",
) -> dict[str, Any]:
    packet = build_context_packet(root, config, provider, goal, repo=repo, topic_id=topic_id)
    if previous_session:
        prev: dict[str, Any] = {
            "id": previous_session.id,
            "provider": previous_session.provider,
            "summary": previous_session.summary,
            "decisions": previous_session.decisions,
            "todos_pending": previous_session.todos_pending,
            "todos_done": previous_session.todos_done,
            "status": previous_session.status,
            "transcript_path": previous_session.transcript_path,
        }
        session_id = previous_session.id
        if session_id:
            from loghop.autocapture import last_turns

            prev["last_turns"] = [
                {"role": t.role, "text": t.text, "ts": t.ts}
                for t in last_turns(root, session_id, limit=10)
            ]
        packet["previous_session"] = prev
    return packet


def render_resume_handoff_markdown(handoff_id: str, packet: dict[str, Any]) -> str:
    base = render_handoff_markdown(handoff_id, packet)
    prev = packet.get("previous_session")
    if not prev:
        return base
    resume_lines = ["", "## Previous Session"]
    resume_lines.extend(_prev_session_header(prev))
    resume_lines.extend(_prev_session_sections(prev))
    resume_lines.extend(_prev_conversation_excerpt(prev))
    if prev.get("transcript_path"):
        resume_lines.append(f"Full transcript: `{prev['transcript_path']}`")
        resume_lines.append("")
    return base + redact_text("\n".join(resume_lines))


def _prev_session_header(prev: dict[str, Any]) -> list[str]:
    lines = [
        f"- Session: {prev.get('id')}",
        f"- Provider: {prev.get('provider')}",
        f"- Status: {prev.get('status')}",
    ]
    if prev.get("summary"):
        lines.extend(["", f"**Summary:** {redact_text(str(prev.get('summary')))}", ""])
    return lines


def _prev_session_sections(prev: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if prev.get("decisions"):
        lines.append("**Decisions:**")
        lines.extend(f"- {redact_text(str(d))}" for d in prev.get("decisions", []))
        lines.append("")
    if prev.get("todos_done"):
        lines.append("**Completed:**")
        lines.extend(f"- [x] {redact_text(str(t))}" for t in prev["todos_done"])
        lines.append("")
    if prev.get("todos_pending"):
        lines.append("**Pending:**")
        lines.extend(f"- [ ] {redact_text(str(t))}" for t in prev.get("todos_pending", []))
        lines.append("")
    return lines


def _prev_conversation_excerpt(prev: dict[str, Any]) -> list[str]:
    last_turns_raw = prev.get("last_turns") or []
    if not isinstance(last_turns_raw, list) or not last_turns_raw:
        return []
    lines = ["", f"## {_PREVIOUS_EXCERPT_TITLE}", ""]
    for turn in last_turns_raw:
        if not isinstance(turn, dict):
            continue
        text = redact_text(str(turn.get("text", ""))).strip()
        if not text:
            continue
        if len(text) > 1200:  # noqa: PLR2004
            text = text[:1199].rstrip() + "…"
        role = str(turn.get("role", "?"))
        lines.append(f"**{role}:**")
        lines.append("")
        lines.extend(f"> {line}" if line else ">" for line in text.splitlines())
        lines.append("")
    return lines
