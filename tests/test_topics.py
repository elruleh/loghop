from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import init_repo

from loghop.store import load_config, project_paths
from loghop.store._handoff import create_resume_handoff
from loghop.store._session import create_session, finish_session, latest_useful_session
from loghop.store._timeline import list_timeline_events
from loghop.store._topic import (
    clear_active_topic,
    close_topic,
    create_topic,
    find_topic,
    list_topics,
    rename_topic,
    resolve_or_create_topic,
    set_active_topic,
)

CliRunner = Callable[..., tuple[int, str, str]]


def _fake_provider(bin_dir: Path, name: str = "codex") -> None:
    script = bin_dir / name
    script.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "import os\n"
        "Path(os.environ['HOME'], '.codex', 'sessions', '2026', '05', '21').mkdir(parents=True, exist_ok=True)\n"
        "print('topic run complete')\n",
        encoding="utf-8",
    )
    script.chmod(0o755)


def test_create_topic_persists_frontmatter_and_active_config(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    paths = project_paths(root)

    topic = create_topic(root, "Arreglar sesiones", set_active=True)

    assert topic.id == "T-001"
    assert topic.title == "Arreglar sesiones"
    assert topic.status == "active"
    assert topic.session_ids == []
    assert find_topic(paths, "T-001").title == "Arreglar sesiones"
    assert load_config(paths).active_topic_id == "T-001"
    assert load_config(paths).topic_counter == 1


def test_topic_lifecycle_list_rename_switch_close(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    paths = project_paths(root)
    first = create_topic(root, "First")
    second = create_topic(root, "Second")

    set_active_topic(root, first.id)
    rename_topic(root, first.id, "Renamed")
    close_topic(root, first.id)

    assert [topic.id for topic in list_topics(paths)] == [second.id, first.id]
    assert find_topic(paths, first.id).title == "Renamed"
    assert find_topic(paths, first.id).status == "closed"
    assert load_config(paths).active_topic_id == ""

    set_active_topic(root, second.id)
    assert load_config(paths).active_topic_id == second.id
    clear_active_topic(root)
    assert load_config(paths).active_topic_id == ""


def test_resolve_or_create_topic_uses_active_then_goal_match(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    paths = project_paths(root)
    existing = create_topic(root, "Ship auth", set_active=False)

    matched = resolve_or_create_topic(root, goal="Ship auth", explicit_topic_id="", new_topic=False)
    assert matched.id == existing.id
    assert load_config(paths).active_topic_id == existing.id

    created = resolve_or_create_topic(root, goal="New work", explicit_topic_id="", new_topic=True)
    assert created.id == "T-002"
    assert created.title == "New work"
    assert load_config(paths).active_topic_id == created.id


def test_sessions_attach_to_topics_and_latest_useful_scopes_resume(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    paths = project_paths(root)
    topic_a = create_topic(root, "A")
    topic_b = create_topic(root, "B")

    a1 = create_session(root, provider="codex", goal="a", topic_id=topic_a.id)
    finish_session(root, a1.id, status="succeeded", returncode=0, summary="done a")
    b1 = create_session(root, provider="claude", goal="b", topic_id=topic_b.id)
    finish_session(root, b1.id, status="succeeded", returncode=0, summary="done b")

    assert latest_useful_session(paths, topic_id=topic_a.id).id == a1.id
    assert latest_useful_session(paths, topic_id=topic_b.id).id == b1.id
    assert find_topic(paths, topic_a.id).session_ids == [a1.id]
    assert find_topic(paths, topic_b.id).session_ids == [b1.id]


def test_timeline_and_handoff_include_topic_context(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    paths = project_paths(root)
    topic = create_topic(root, "Grouped work", set_active=True)
    session = create_session(root, provider="codex", goal="step", topic_id=topic.id)
    finish_session(root, session.id, status="succeeded", returncode=0, summary="topic summary")

    events = list_timeline_events(paths, topic_id=topic.id)
    assert [event["session_id"] for event in events] == [session.id]
    assert events[0]["topic_id"] == topic.id

    handoff = create_resume_handoff(
        root,
        "claude",
        "next step",
        previous_session=session,
        topic_id=topic.id,
    )
    assert "## Topic Context" in handoff.markdown
    assert "Grouped work" in handoff.markdown
    assert "topic summary" in handoff.markdown


def test_topics_cli_lists_shows_switches_renames_and_closes(cli: CliRunner, tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    create_topic(root, "Original", set_active=True)

    code, stdout, _ = cli(["topics"], cwd=root)
    assert code == 0
    assert "Original" in stdout
    assert "T-001" in stdout

    code, stdout, _ = cli(["topics", "show", "T-001"], cwd=root)
    assert code == 0
    assert "Original" in stdout

    code, stdout, _ = cli(["topics", "rename", "T-001", "Renamed"], cwd=root)
    assert code == 0
    assert "Renamed" in stdout

    clear_active_topic(root)
    code, stdout, _ = cli(["topics", "switch", "T-001"], cwd=root)
    assert code == 0
    assert "active" in stdout.lower()

    code, stdout, _ = cli(["topics", "close", "T-001"], cwd=root)
    assert code == 0
    assert "closed" in stdout.lower()


def test_run_new_topic_creates_topic_and_session(
    cli: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_provider(bin_dir, "codex")
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")

    code, _stdout, _stderr = cli(
        ["run", "--provider", "codex", "--goal", "Implement grouped sessions", "--new-topic"],
        cwd=root,
    )

    assert code == 0
    topic = list_topics(project_paths(root))[0]
    assert topic.title == "Implement grouped sessions"
    assert topic.session_ids == ["S-001"]
    assert load_config(project_paths(root)).active_topic_id == topic.id
