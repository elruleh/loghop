import json
from unittest.mock import patch

from loghop.store._constants import project_paths
from loghop.store._index import rebuild_index
from loghop.store._session import (
    create_session,
    delete_session,
    find_session_by_claude_id,
    list_sessions,
)


def test_session_index_maintains_list(tmp_path):
    create_session(tmp_path, provider="test", goal="goal 1")
    paths = project_paths(tmp_path)

    # Fast path list
    sessions = list_sessions(paths)
    assert len(sessions) == 1
    assert sessions[0].goal == "goal 1"

    # Create another
    create_session(tmp_path, provider="test", goal="goal 2")
    sessions = list_sessions(paths)
    assert len(sessions) == 2
    assert sessions[0].goal == "goal 2"  # Sorted descending by ID
    assert sessions[1].goal == "goal 1"


def test_session_index_deletion(tmp_path):
    s1 = create_session(tmp_path, provider="test", goal="goal 1")
    s2 = create_session(tmp_path, provider="test", goal="goal 2")
    paths = project_paths(tmp_path)

    assert len(list_sessions(paths)) == 2

    delete_session(paths, s1.id)

    sessions = list_sessions(paths)
    assert len(sessions) == 1
    assert sessions[0].id == s2.id

    # Check index file directly
    index_path = paths.dot / "sessions.jsonl"
    lines = index_path.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["id"] == s2.id


def test_session_index_rebuild_if_missing(tmp_path):
    create_session(tmp_path, provider="test", goal="goal 1")
    paths = project_paths(tmp_path)

    index_path = paths.dot / "sessions.jsonl"
    assert index_path.exists()

    # Delete index
    index_path.unlink()

    # list_sessions should fall back to directory scan and rebuild
    # Wait, list_sessions falls back to directory scan if index missing,
    # but it doesn't necessarily REWRITE the index.
    # Actually, update_index calls rebuild_index if missing.

    sessions = list_sessions(paths)
    assert len(sessions) == 1
    assert sessions[0].goal == "goal 1"

    # If we call create_session now, it should rebuild and add new one
    create_session(tmp_path, provider="test", goal="goal 2")
    assert index_path.exists()
    sessions = list_sessions(paths)
    assert len(sessions) == 2


def test_session_index_rebuild_if_corrupt(tmp_path):
    create_session(tmp_path, provider="test", goal="goal 1")
    paths = project_paths(tmp_path)
    index_path = paths.dot / "sessions.jsonl"

    # Corrupt it
    index_path.write_text("NOT JSON\n")

    # list_sessions should fall back to scan
    sessions = list_sessions(paths)
    assert len(sessions) == 1

    # update_index (via create_session) should rebuild
    create_session(tmp_path, provider="test", goal="goal 2")
    sessions = list_sessions(paths)
    assert len(sessions) == 2

    # Check it was repaired
    content = index_path.read_text()
    assert "goal 1" in content
    assert "goal 2" in content


def test_session_index_redaction(tmp_path):
    secret_goal = "My secret key is sk-ant-api03-12345678901234567890123456789012"
    create_session(tmp_path, provider="test", goal=secret_goal)
    paths = project_paths(tmp_path)

    index_path = paths.dot / "sessions.jsonl"
    assert index_path.exists()

    content = index_path.read_text()
    assert "sk-ant-api03-12345678901234567890123456789012" not in content
    assert "[redacted anthropic api key]" in content


def test_find_session_by_claude_id_uses_index(tmp_path):
    paths = project_paths(tmp_path)
    s1 = create_session(tmp_path, provider="test", goal="goal 1")

    # Manually update the session to have a claude_session_id
    md_path = tmp_path / s1.path
    content = md_path.read_text()
    lines = content.splitlines()
    lines.insert(1, "claude_session_id: my-claude-id")
    md_path.write_text("\n".join(lines))

    # Rebuild index to include the new field
    rebuild_index(paths)

    with patch("loghop.store._session.parse_frontmatter_text") as mock_parse:
        found = find_session_by_claude_id(paths, "my-claude-id")
        assert found is not None
        assert found.id == s1.id
        assert found.claude_session_id == "my-claude-id"
        # Should NOT have called parse_frontmatter_text because it used the index
        assert mock_parse.call_count == 0


def test_find_session_by_claude_id_fallback(tmp_path):
    paths = project_paths(tmp_path)
    s1 = create_session(tmp_path, provider="test", goal="goal 1")

    # Manually update the session to have a claude_session_id
    md_path = tmp_path / s1.path
    content = md_path.read_text()
    lines = content.splitlines()
    lines.insert(1, "claude_session_id: my-claude-id-2")
    md_path.write_text("\n".join(lines))

    # Delete index to force fallback
    index_path = paths.dot / "sessions.jsonl"
    index_path.unlink()

    found = find_session_by_claude_id(paths, "my-claude-id-2")
    assert found is not None
    assert found.id == s1.id
    assert found.claude_session_id == "my-claude-id-2"
