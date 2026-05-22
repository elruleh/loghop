from loghop.store._constants import project_paths
from loghop.store._session import create_session, list_sessions


def test_index_loss_of_previous_sessions(tmp_path):
    create_session(tmp_path, provider="test", goal="session 1")
    paths = project_paths(tmp_path)
    index_path = paths.dot / "sessions.jsonl"

    assert index_path.exists()
    assert len(list_sessions(paths)) == 1

    # Delete index
    index_path.unlink()

    # Still 1 because it falls back to scanning
    assert len(list_sessions(paths)) == 1

    # Create another session - this should ideally re-index or at least not wipe knowledge of old ones
    create_session(tmp_path, provider="test", goal="session 2")

    # If the bug exists, list_sessions (using the new index) will only see session 2
    sessions = list_sessions(paths)
    session_goals = {s.goal for s in sessions}
    assert "session 1" in session_goals, f"Session 1 lost! Goals: {session_goals}"
    assert len(sessions) == 2
