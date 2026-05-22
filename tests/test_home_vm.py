from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from loghop.tui.screens._home_vm import (
    format_latest_update,
    format_name_cell,
    format_pending_preview,
    format_sessions_cell,
    matches_project,
    sort_projects,
)


def _make_project(**overrides: Any) -> Any:
    p = MagicMock()
    p.name = "repo"
    p.path = Path("/tmp/repo")
    p.goal = "ship it"
    p.session_count = 2
    p.handoff_count = 0
    p.last_used = "2024-01-01T10:00:00Z"
    p.current = False
    p.exists = True
    for key, value in overrides.items():
        setattr(p, key, value)
    return p


def _make_entry(**overrides: Any) -> Any:
    e = MagicMock()
    e.title = "Implemented project list"
    e.summary = "fallback summary"
    e.goal = "fallback goal"
    e.provider = "codex"
    e.ts_start = "2024-01-01T10:00:00Z"
    for key, value in overrides.items():
        setattr(e, key, value)
    return e


def test_sort_projects_by_name_case_insensitive() -> None:
    result = sort_projects([_make_project(name="Zebra"), _make_project(name="alpha")], "name")
    assert result[0].name == "alpha"


def test_sort_projects_by_sessions_descending() -> None:
    result = sort_projects(
        [_make_project(session_count=1), _make_project(session_count=9)], "sessions"
    )
    assert result[0].session_count == 9


def test_sort_projects_recent_preserves_service_order() -> None:
    first = _make_project(name="first")
    second = _make_project(name="second")
    assert sort_projects([first, second], "recent") == [first, second]


def test_matches_project_searches_name_path_and_goal() -> None:
    project = _make_project(name="core", path=Path("/tmp/special"), goal="ship tui")
    assert matches_project(project, "special", set()) is True
    assert matches_project(project, "tui", set()) is True
    assert matches_project(project, "missing", set()) is False


def test_matches_project_current_and_missing_flags() -> None:
    assert matches_project(_make_project(current=True), "", {"current"}) is True
    assert matches_project(_make_project(current=False), "", {"current"}) is False
    assert matches_project(_make_project(exists=False), "", {"missing"}) is True
    assert matches_project(_make_project(exists=True), "", {"missing"}) is False


def test_format_name_cell_strikes_missing_project() -> None:
    cell = format_name_cell(_make_project(name="gone", exists=False))
    assert "gone" in cell
    assert "strike" in cell


def test_format_sessions_cell_includes_handoff_count_when_present() -> None:
    cell = format_sessions_cell(_make_project(session_count=5, handoff_count=3))
    assert "5" in cell
    assert "3" in cell


def test_format_latest_update_uses_title_and_provider_metadata() -> None:
    cell = format_latest_update(_make_entry())
    assert "Implemented project list" in cell
    assert "codex" in cell


def test_format_pending_preview_limits_items_and_reports_remaining_count() -> None:
    cell = format_pending_preview(("one", "two", "three", "four"))
    assert "one" in cell
    assert "three" in cell
    assert "1" in cell
