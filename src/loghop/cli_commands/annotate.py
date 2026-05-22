import argparse
from pathlib import Path
from typing import Any

from loghop.cli_commands._helpers import require_project_root
from loghop.store import project_paths
from loghop.store._session import find_session, latest_session
from loghop.terminal import Terminal


def handle_session_annotate(args: argparse.Namespace, term: Terminal) -> int:
    root = require_project_root()
    paths = project_paths(root)
    session_id = _resolve_annotation_session(args, paths)
    if session_id is None:
        term.error("No sessions available to annotate")
        return 2

    # Guard: refuse to annotate a running session — it would break the
    # active provider's lifecycle by overwriting status to "annotated".
    session_meta = find_session(paths, session_id)
    if session_meta.status == "running":
        term.error(
            f"Session {session_id} is still running. "
            "Wait for the provider to finish or reconcile first."
        )
        return 2

    updates = _build_annotation_updates(args)
    if not updates:
        term.error("Provide at least one of: --summary, --decision, --todo, --done")
        return 2

    _annotate_finished_session(root, session_id, updates)
    term.success(f"Updated session {session_id}")
    _report_annotation_details(updates, term)
    term.capture_result(
        {"session_id": session_id, "updates": {k: v for k, v in updates.items() if k != "status"}}
    )
    return 0


def _annotate_finished_session(
    root: Path,
    session_id: str,
    updates: dict[str, object],
) -> None:
    """Patch frontmatter of a finished session with annotation data.

    Uses ``rewrite_frontmatter`` (atomic write) and refreshes the JSONL index.
    """
    from loghop.store._frontmatter import (
        meta_to_dataclass,
        parse_frontmatter_text,
        rewrite_frontmatter,
    )
    from loghop.store._index import update_index, validated_sessions_dir
    from loghop.store._models import SessionMeta

    paths = project_paths(root)
    md_path = validated_sessions_dir(paths) / f"{session_id}.md"
    frontmatter_updates: dict[str, Any] = {"status": "annotated"}
    if updates.get("summary"):
        frontmatter_updates["summary"] = updates["summary"]
    if updates.get("decisions") is not None:
        frontmatter_updates["decisions"] = updates["decisions"]
    if updates.get("todos_pending") is not None:
        frontmatter_updates["todos_pending"] = updates["todos_pending"]
    if updates.get("todos_done") is not None:
        frontmatter_updates["todos_done"] = updates["todos_done"]

    rewrite_frontmatter(md_path, frontmatter_updates)
    parsed, _ = parse_frontmatter_text(md_path)
    parsed["path"] = str(md_path.relative_to(root))
    kwargs = meta_to_dataclass(parsed, SessionMeta)
    session = SessionMeta(**kwargs)
    update_index(paths, session=session)


def _resolve_annotation_session(args: argparse.Namespace, paths: Any) -> str | None:
    session_id: str | None = args.session_id
    if not session_id:
        session = latest_session(paths)
        if not session or not session.id:
            return None
        session_id = session.id
    return str(session_id)


def _build_annotation_updates(args: argparse.Namespace) -> dict[str, object]:
    updates: dict[str, object] = {"status": "annotated"}
    if args.summary:
        updates["summary"] = args.summary
    if args.decision:
        updates["decisions"] = args.decision
    if args.todo:
        updates["todos_pending"] = args.todo
    if args.done:
        updates["todos_done"] = args.done
    if (
        not updates.get("summary")
        and not updates.get("decisions")
        and not updates.get("todos_pending")
        and not updates.get("todos_done")
    ):
        return {}
    return updates


def _report_annotation_details(updates: dict[str, object], term: Terminal) -> None:
    if updates.get("summary"):
        term.detail(f"  summary: {updates['summary']}")
    decisions = updates.get("decisions")
    if isinstance(decisions, list):
        term.detail(f"  decisions: {len(decisions)} added")
    todos = updates.get("todos_pending")
    if isinstance(todos, list):
        term.detail(f"  todos pending: {len(todos)}")
    done = updates.get("todos_done")
    if isinstance(done, list):
        term.detail(f"  todos done: {len(done)}")
