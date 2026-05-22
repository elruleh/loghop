import argparse
import dataclasses

from loghop.cli_commands._handoff_launch import launch_handoff_session
from loghop.cli_commands._helpers import (
    require_project_config,
    require_project_root,
    require_provider_arg,
    resolve_default_provider,
    resolve_goal,
    validate_length,
)
from loghop.errors import E_INVALID_INPUT, LoghopError
from loghop.redact import redact_text
from loghop.store import (
    ProjectPaths,
    create_handoff,
    find_handoff,
    list_handoffs,
    project_paths,
)
from loghop.store._io import safe_read_text
from loghop.store._topic import resolve_or_create_topic
from loghop.terminal import Terminal


def handle_handoff_list(args: argparse.Namespace, term: Terminal) -> int:
    root = require_project_root()
    paths = project_paths(root)
    handoffs = list_handoffs(paths, provider=args.provider)
    if handoffs:
        term.table(
            [
                (
                    h.id,
                    h.provider,
                    h.status,
                    h.returncode or "",
                    h.ts,
                    h.goal,
                )
                for h in handoffs
            ],
            headers=("id", "provider", "status", "code", "created", "goal"),
            title="handoffs",
        )
    else:
        term.info("No handoffs yet")
    term.capture_result({"handoffs": handoffs})
    return 0


def handle_handoff_show(args: argparse.Namespace, term: Terminal) -> int:
    root = require_project_root()
    paths = project_paths(root)
    handoff_id = _resolve_handoff_id(paths, args.handoff_id, latest=bool(args.latest))
    handoff = find_handoff(paths, handoff_id)
    text = safe_read_text(root / handoff.path)
    term.line(text.rstrip())
    term.capture_result({**dataclasses.asdict(handoff), "markdown": text})
    return 0


def handle_handoff_build(args: argparse.Namespace, term: Terminal) -> int:
    root, _paths, config = require_project_config()
    provider_arg = args.provider or resolve_default_provider(root)
    provider = require_provider_arg(provider_arg, "handoff build")
    goal = resolve_goal(args.goal, config, "handoff")
    validate_length(goal, "goal")
    topic = None
    explicit_topic_id = str(getattr(args, "topic", "") or "")
    new_topic = bool(getattr(args, "new_topic", False))
    should_use_topic = bool(config.active_topic_id or explicit_topic_id or new_topic)
    if should_use_topic and not bool(getattr(args, "no_topic", False)):
        topic = resolve_or_create_topic(
            root,
            goal=goal,
            explicit_topic_id=explicit_topic_id,
            new_topic=new_topic,
        )
    record = create_handoff(root, provider, goal, topic_id=topic.id if topic else "")
    term.section(
        "handoff",
        (
            ("id", record.id),
            ("provider", provider),
            ("goal", redact_text(goal)),
            ("path", record.path),
        ),
    )
    term.success(f"Built handoff {record.id}")
    term.capture_result(
        {
            "id": record.id,
            "provider": provider,
            "goal": redact_text(goal),
            "path": record.path,
        }
    )
    return 0


def handle_handoff_run(args: argparse.Namespace, term: Terminal) -> int:
    return launch_handoff_session(args, term, mode="fresh", command="handoff run")


def _resolve_handoff_id(paths: ProjectPaths, handoff_id: str | None, *, latest: bool) -> str:
    if latest:
        handoffs = list_handoffs(paths)
        if not handoffs:
            raise LoghopError("no handoffs found", code=E_INVALID_INPUT)
        return handoffs[0].id
    if not handoff_id:
        raise LoghopError("handoff id is required unless --latest is used", code=E_INVALID_INPUT)
    return handoff_id
