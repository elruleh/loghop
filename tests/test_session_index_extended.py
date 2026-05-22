from loghop.store._constants import project_paths
from loghop.store._session import create_session, delete_session, list_sessions


def test_session_index_maintains_list(tmp_path):
    create_session(tmp_path, provider="test", goal="goal 1")
    paths = project_paths(tmp_path)

    # Fast path list
    sessions = list_sessions(paths)
    assert len(sessions) == 1
    assert sessions[0].goal == "goal 1"


def test_session_index_stale_after_delete(tmp_path):
    s = create_session(tmp_path, provider="test", goal="goal 1")
    paths = project_paths(tmp_path)

    delete_session(paths, s.id)

    sessions = list_sessions(paths)
    # If the index is not updated, this will still be 1
    assert len(sessions) == 0, f"Expected 0 sessions after delete, but got {len(sessions)}"
