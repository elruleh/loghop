from __future__ import annotations

from pathlib import Path

from conftest import init_repo

from loghop.store._session import create_session, finish_session
from loghop.store._topic import create_topic
from loghop.tui.services import TuiService


def test_tui_service_exposes_topics_with_session_counts(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    topic = create_topic(root, "Grouped TUI work", set_active=True)
    session = create_session(root, provider="codex", goal="step", topic_id=topic.id)
    finish_session(root, session.id, status="succeeded", returncode=0, summary="done")

    topics = TuiService(cwd=root).topics(root)

    assert len(topics) == 1
    assert topics[0].id == topic.id
    assert topics[0].title == "Grouped TUI work"
    assert topics[0].session_count == 1
    assert topics[0].active is True
