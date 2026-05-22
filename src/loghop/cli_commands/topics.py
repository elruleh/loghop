from __future__ import annotations

import argparse
import dataclasses

from loghop.cli_commands._helpers import require_project_root, truncate_text
from loghop.errors import E_INVALID_INPUT, LoghopError
from loghop.store import load_config, project_paths
from loghop.store._topic import (
    close_topic,
    find_topic,
    list_topics,
    rename_topic,
    set_active_topic,
)
from loghop.terminal import Terminal


def handle_topics_list(args: argparse.Namespace, term: Terminal) -> int:
    root = require_project_root()
    paths = project_paths(root)
    config = load_config(paths)
    topics = list_topics(paths)
    if not topics:
        term.info("No topics yet")
        term.capture_result({"topics": []})
        return 0
    rows = []
    for topic in topics:
        marker = "*" if topic.id == config.active_topic_id else ""
        rows.append(
            (
                topic.id,
                marker,
                topic.status,
                str(len(topic.session_ids or [])),
                topic.updated_at or topic.created_at,
                truncate_text(topic.title, 60),
            )
        )
    term.table(
        rows, headers=("id", "active", "status", "sessions", "updated", "title"), title="topics"
    )
    term.capture_result({"topics": [dataclasses.asdict(topic) for topic in topics]})
    return 0


def handle_topics_show(args: argparse.Namespace, term: Terminal) -> int:
    root = require_project_root()
    topic = find_topic(project_paths(root), args.topic_id)
    term.section(
        "topic",
        (
            ("id", topic.id),
            ("title", topic.title),
            ("status", topic.status),
            ("sessions", str(len(topic.session_ids or []))),
            ("updated", topic.updated_at or topic.created_at),
        ),
    )
    if topic.session_ids:
        term.line("sessions:")
        for session_id in topic.session_ids:
            term.line(f"  - {session_id}")
    term.capture_result(dataclasses.asdict(topic))
    return 0


def handle_topics_switch(args: argparse.Namespace, term: Terminal) -> int:
    root = require_project_root()
    topic = set_active_topic(root, args.topic_id)
    term.success(f"Active topic {topic.id}: {topic.title}")
    term.capture_result(dataclasses.asdict(topic))
    return 0


def handle_topics_close(args: argparse.Namespace, term: Terminal) -> int:
    root = require_project_root()
    topic = close_topic(root, args.topic_id)
    term.success(f"Closed topic {topic.id}: {topic.title}")
    term.capture_result(dataclasses.asdict(topic))
    return 0


def handle_topics_rename(args: argparse.Namespace, term: Terminal) -> int:
    root = require_project_root()
    topic = rename_topic(root, args.topic_id, args.title)
    term.success(f"Renamed topic {topic.id}: {topic.title}")
    term.capture_result(dataclasses.asdict(topic))
    return 0


def require_topic_id(value: str | None) -> str:
    if not value:
        raise LoghopError("topic id is required", code=E_INVALID_INPUT)
    return value
