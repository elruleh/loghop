# mypy: disable-error-code="no-untyped-def"
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from loghop.tui.app import create_app
from loghop.tui.i18n import set_language
from loghop.tui.screens._home_vm import (
    SORT_NAME as _SORT_NAME,
)
from loghop.tui.screens._home_vm import (
    SORT_RECENT as _SORT_RECENT,
)
from loghop.tui.screens._home_vm import (
    SORT_SESSIONS as _SORT_SESSIONS,
)
from loghop.tui.screens._home_vm import (
    sort_projects as _sort_projects,
)
from loghop.tui.screens.home import HomeScreen
from loghop.tui.services import TuiService

pytestmark = pytest.mark.slow


def _make_project(**overrides) -> Any:
    p = MagicMock()
    p.name = "repo"
    p.path = Path("/tmp/repo")
    p.goal = ""
    p.session_count = 0
    p.handoff_count = 0
    p.last_used = "2024-01-01"
    p.current = False
    p.exists = True
    for k, v in overrides.items():
        setattr(p, k, v)
    return p


def _make_mock_service(**overrides) -> Any:
    set_language("en")
    service = MagicMock(spec=TuiService)

    project = _make_project()

    service.projects.return_value = overrides.get("projects", [project])
    service.current_project_root.return_value = None
    service.sessions.return_value = []
    service.timeline.return_value = []
    service.providers.return_value = []
    service.default_provider.return_value = "codex"
    return service


def test_home_preview_shortcut_and_loading_labels_are_localized() -> None:
    from loghop.tui.i18n import tr

    keys = (
        "PROJECTS_SHORTCUT_OPEN",
        "PROJECTS_SHORTCUT_REMOVE",
        "PROJECTS_SHORTCUT_FORGET",
        "PROJECT_PREVIEW_LOADING_TITLE",
        "PROJECT_PREVIEW_LOADING_BODY",
    )

    for key in keys:
        assert tr(key) != key
        assert tr(key).strip()


# ── Pure unit tests ──


class TestSortProjects:
    def test_sort_by_name(self) -> None:
        a = _make_project(name="banana")
        b = _make_project(name="apple")
        result = _sort_projects([a, b], _SORT_NAME)
        assert result[0].name == "apple"

    def test_sort_by_sessions_desc(self) -> None:
        a = _make_project(session_count=2)
        b = _make_project(session_count=10)
        result = _sort_projects([a, b], _SORT_SESSIONS)
        assert result[0].session_count == 10

    def test_sort_by_recent_returns_as_is(self) -> None:
        a = _make_project(name="first")
        b = _make_project(name="second")
        result = _sort_projects([a, b], _SORT_RECENT)
        assert result[0].name == "first"

    def test_sort_by_name_case_insensitive(self) -> None:
        a = _make_project(name="Zebra")
        b = _make_project(name="alpha")
        result = _sort_projects([a, b], _SORT_NAME)
        assert result[0].name == "alpha"


class TestFormatNameCell:
    def test_basic_name(self) -> None:
        p = _make_project(name="myrepo", exists=True)
        result = HomeScreen._format_name_cell(p)
        assert "myrepo" in result

    def test_missing_project_shows_warning(self) -> None:
        p = _make_project(name="gone", exists=False)
        result = HomeScreen._format_name_cell(p)
        assert "gone" in result
        assert "strike" in result or "dim" in result

    def test_goal_not_in_cell(self) -> None:
        p = _make_project(name="repo", exists=True, goal="ship it")
        result = HomeScreen._format_name_cell(p)
        assert "ship it" not in result
        assert "repo" in result

    def test_empty_goal_no_extra(self) -> None:
        p = _make_project(name="repo", exists=True, goal="")
        result = HomeScreen._format_name_cell(p)
        assert result.endswith("repo")

    def test_multiline_goal_not_in_cell(self) -> None:
        p = _make_project(name="repo", exists=True, goal="line1\nline2")
        result = HomeScreen._format_name_cell(p)
        assert "line1" not in result
        assert "line2" not in result


class TestFormatSessionsCell:
    def test_zero(self) -> None:
        p = _make_project(session_count=0, handoff_count=0)
        assert HomeScreen._format_sessions_cell(p) == "0"

    def test_with_handoffs(self) -> None:
        p = _make_project(session_count=5, handoff_count=3)
        result = HomeScreen._format_sessions_cell(p)
        assert "5" in result
        assert "3" in result

    def test_sessions_only(self) -> None:
        p = _make_project(session_count=7, handoff_count=0)
        assert HomeScreen._format_sessions_cell(p) == "7"


class TestFormatWhenCell:
    def test_no_bucket(self) -> None:
        result = HomeScreen._format_when_cell("2h ago", None)
        assert result == "2h ago"

    def test_with_bucket(self) -> None:
        result = HomeScreen._format_when_cell("2h ago", "TODAY")
        assert "TODAY" in result
        assert "2h ago" in result

    def test_with_none_bucket(self) -> None:
        result = HomeScreen._format_when_cell("5m ago", None)
        assert result == "5m ago"


class TestMatches:
    def _matches(self, project, text, flags) -> bool:
        screen = MagicMock(spec=HomeScreen)
        return HomeScreen._matches(screen, project, text, flags)

    def test_text_in_name(self) -> None:
        p = _make_project(name="myrepo")
        assert self._matches(p, "repo", set()) is True

    def test_text_not_found(self) -> None:
        p = _make_project(name="myrepo")
        assert self._matches(p, "zzz", set()) is False

    def test_text_in_path(self) -> None:
        p = _make_project(name="x", path=Path("/tmp/special"))
        assert self._matches(p, "special", set()) is True

    def test_text_in_goal(self) -> None:
        p = _make_project(name="x", goal="ship the thing")
        assert self._matches(p, "thing", set()) is True

    def test_flag_current(self) -> None:
        p = _make_project(current=True)
        assert self._matches(p, "", {"current"}) is True

    def test_flag_current_not_current(self) -> None:
        p = _make_project(current=False)
        assert self._matches(p, "", {"current"}) is False

    def test_flag_missing(self) -> None:
        p = _make_project(exists=False)
        assert self._matches(p, "", {"missing"}) is True

    def test_flag_missing_but_exists(self) -> None:
        p = _make_project(exists=True)
        assert self._matches(p, "", {"missing"}) is False

    def test_combined_text_and_flag(self) -> None:
        p = _make_project(name="repo", current=True)
        assert self._matches(p, "repo", {"current"}) is True

    def test_combined_text_and_flag_no_match(self) -> None:
        p = _make_project(name="repo", current=True)
        assert self._matches(p, "zzz", {"current"}) is False

    def test_empty_query_matches_all(self) -> None:
        p = _make_project(name="anything")
        assert self._matches(p, "", set()) is True


class TestDefaultActions:
    def test_returns_list_of_tuples(self) -> None:
        actions = HomeScreen._default_actions()
        assert isinstance(actions, list)
        assert all(isinstance(a, tuple) and len(a) == 2 for a in actions)

    def test_contains_add(self) -> None:
        keys = [a[0] for a in HomeScreen._default_actions()]
        assert "a" in keys

    def test_contains_help(self) -> None:
        keys = [a[0] for a in HomeScreen._default_actions()]
        assert "?" in keys

    def test_does_not_contain_search(self) -> None:
        keys = [a[0] for a in HomeScreen._default_actions()]
        assert "/" not in keys


class TestEntityForKey:
    def test_finds_matching_project(self) -> None:
        screen = MagicMock(spec=HomeScreen)
        p = _make_project(path=Path("/tmp/repo"))
        screen._projects_cache = [p]
        result = HomeScreen._entity_for_key(screen, MagicMock(value="/tmp/repo"))
        assert result is p

    def test_returns_none_for_no_match(self) -> None:
        screen = MagicMock(spec=HomeScreen)
        screen._projects_cache = []
        result = HomeScreen._entity_for_key(screen, MagicMock(value="/tmp/x"))
        assert result is None

    def test_returns_none_for_none_value(self) -> None:
        screen = MagicMock(spec=HomeScreen)
        screen._projects_cache = [_make_project()]
        result = HomeScreen._entity_for_key(screen, MagicMock(value=None))
        assert result is None


class TestYankValue:
    def test_returns_path_string(self) -> None:
        p = _make_project(path=Path("/tmp/repo"))
        assert HomeScreen._yank_value(p) == "/tmp/repo"


# ── Async TUI tests ──


class TestHomeScreenAsync:
    def test_home_preview_ignores_stale_timeline_results(self) -> None:
        import time
        from types import SimpleNamespace

        from textual.widgets import Static

        set_language("en")
        alpha = SimpleNamespace(
            name="alpha",
            path=Path("/tmp/alpha"),
            goal="",
            registered="",
            last_used="2026-05-21T10:00:00Z",
            last_session="",
            session_count=1,
            handoff_count=0,
            exists=True,
            current=False,
        )
        beta = SimpleNamespace(
            name="beta",
            path=Path("/tmp/beta"),
            goal="",
            registered="",
            last_used="2026-05-21T09:00:00Z",
            last_session="",
            session_count=1,
            handoff_count=0,
            exists=True,
            current=False,
        )

        def timeline(root: Path, *, limit: int | None = None) -> list[object]:
            name = Path(root).name
            if name == "alpha":
                time.sleep(0.35)
            else:
                time.sleep(0.05)
            return [
                SimpleNamespace(
                    title=f"{name}-title",
                    summary=f"{name}-title",
                    goal="",
                    provider="codex",
                    ts_start="2026-05-21T10:00:00Z",
                    todos_pending=(),
                )
            ]

        service = MagicMock()
        service.current_project_root.return_value = None
        service.projects.return_value = [alpha, beta]
        service.timeline.side_effect = timeline

        async def run() -> None:
            app = create_app(service=service, global_view=True)
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause(0.2)
                await pilot.press("j")
                await pilot.pause(0.7)

                preview_text = "\n".join(
                    str(node.renderable)
                    for node in app.query(Static)
                    if node.id == "preview-empty" or "preview" in " ".join(node.classes)
                )

                assert "[b]beta[/]" in preview_text
                assert "beta-title" in preview_text
                assert "alpha-title" not in preview_text
                assert preview_text.count("enter open") <= 1

        asyncio.run(run())

    def test_home_preview_reuses_latest_timeline_cache(self) -> None:
        import time
        from types import SimpleNamespace

        alpha = SimpleNamespace(
            name="alpha",
            path=Path("/tmp/alpha"),
            goal="",
            registered="",
            last_used="2026-05-21T10:00:00Z",
            last_session="",
            session_count=1,
            handoff_count=0,
            exists=True,
            current=False,
        )
        beta = SimpleNamespace(
            name="beta",
            path=Path("/tmp/beta"),
            goal="",
            registered="",
            last_used="2026-05-21T09:00:00Z",
            last_session="",
            session_count=1,
            handoff_count=0,
            exists=True,
            current=False,
        )
        calls: list[str] = []

        def timeline(root: Path, *, limit: int | None = None) -> list[object]:
            calls.append(Path(root).name)
            time.sleep(0.03)
            return [
                SimpleNamespace(
                    title=f"{Path(root).name}-title",
                    summary=f"{Path(root).name}-title",
                    goal="",
                    provider="codex",
                    ts_start="2026-05-21T10:00:00Z",
                    todos_pending=(),
                )
            ]

        service = MagicMock()
        service.current_project_root.return_value = None
        service.projects.return_value = [alpha, beta]
        service.timeline.side_effect = timeline

        async def run() -> None:
            app = create_app(service=service, global_view=True)
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause(0.25)
                await pilot.press("j")
                await pilot.pause(0.15)
                await pilot.press("k")
                await pilot.pause(0.15)
                await pilot.press("j")
                await pilot.pause(0.15)

        asyncio.run(run())

        assert calls.count("alpha") <= 1
        assert calls.count("beta") <= 1

    def test_home_empty_projects(self) -> None:
        service = _make_mock_service(projects=[])

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                from textual.widgets import Static

                empty = app.query_one("#projects-empty", Static)
                assert empty.display is True

        asyncio.run(run())

    def test_home_with_multiple_projects(self) -> None:
        p1 = _make_project(name="alpha", path=Path("/tmp/alpha"))
        p2 = _make_project(name="beta", path=Path("/tmp/beta"))
        service = _make_mock_service(projects=[p1, p2])

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                from textual.widgets._data_table import DataTable

                table = app.query_one("#project-table", DataTable)
                assert table.row_count == 2

        asyncio.run(run())

    def test_home_service_error_shows_error(self) -> None:
        service = _make_mock_service()
        service.projects.side_effect = RuntimeError("db broken")

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                from textual.widgets import Static

                empty = app.query_one("#projects-empty", Static)
                assert empty.display is True

        asyncio.run(run())

    def test_home_sort_cycle(self) -> None:
        p1 = _make_project(name="b", session_count=1, path=Path("/tmp/b"))
        p2 = _make_project(name="a", session_count=5, path=Path("/tmp/a"))
        service = _make_mock_service(projects=[p1, p2])

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("s")
                await pilot.pause(0.3)
                from textual.widgets._data_table import DataTable

                table = app.query_one("#project-table", DataTable)
                assert table.row_count == 2

        asyncio.run(run())

    def test_home_sort_reorders_visible_rows(self) -> None:
        p1 = _make_project(name="b", session_count=1, path=Path("/tmp/b"))
        p2 = _make_project(name="a", session_count=5, path=Path("/tmp/a"))
        service = _make_mock_service(projects=[p1, p2])

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                from textual.widgets._data_table import DataTable

                table = app.query_one("#project-table", DataTable)
                assert "b" in str(table.get_cell_at((0, 1)))

                await pilot.press("s")
                await pilot.pause(0.3)

                assert "a" in str(table.get_cell_at((0, 1)))

        asyncio.run(run())

    def test_home_narrow_hides_preview_until_tab(self) -> None:
        service = _make_mock_service()

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(72, 24)) as pilot:
                await pilot.pause(0.3)

                from textual.widgets import Static

                preview = app.query_one("#project-preview")
                actions = app.query_one("#home-command-bar .command-bar-actions", Static)
                assert preview.display is False
                assert "detail" in str(actions.renderable)

                await pilot.press("tab")
                await pilot.pause(0.3)

                assert preview.display is True
                actions = app.query_one("#home-command-bar .command-bar-actions", Static)
                assert "list" in str(actions.renderable)

        asyncio.run(run())

    def test_home_focus_search(self) -> None:
        service = _make_mock_service()

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("/")
                await pilot.pause(0.3)
                from textual.widgets import Input

                search = app.query_one("#project-search", Input)
                assert search.has_focus

        asyncio.run(run())

    def test_home_delete_no_selection_no_crash(self) -> None:
        service = _make_mock_service(projects=[])

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("d")
                await pilot.pause(0.3)

        asyncio.run(run())

    def test_home_undo_empty_no_crash(self) -> None:
        service = _make_mock_service()

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("u")
                await pilot.pause(0.3)

        asyncio.run(run())

    def test_home_missing_project_renders(self) -> None:
        p = _make_project(name="gone", exists=False, path=Path("/tmp/gone"))
        service = _make_mock_service(projects=[p])

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                from textual.widgets._data_table import DataTable

                table = app.query_one("#project-table", DataTable)
                assert table.row_count == 1

        asyncio.run(run())

    def test_home_delete_with_confirmation(self) -> None:
        p = _make_project(name="deleteme", path=Path("/tmp/deleteme"))
        service = _make_mock_service(projects=[p])

        async def run() -> None:
            app = create_app(service=service)
            with patch("loghop.tui.screens.home.unregister_project") as mock_unreg:
                async with app.run_test(size=(80, 24)) as pilot:
                    await pilot.pause(0.3)
                    await pilot.press("d")
                    await pilot.pause(0.3)
                    await pilot.click("#btn-confirm-ok")
                    await pilot.pause(0.3)
                    mock_unreg.assert_called_once()

        asyncio.run(run())

    def test_home_undo_restores_project(self) -> None:
        p = _make_project(name="undoable", path=Path("/tmp/undoable"))
        service = _make_mock_service(projects=[p])

        async def run() -> None:
            app = create_app(service=service)
            with patch("loghop.tui.screens.home.unregister_project"):
                async with app.run_test(size=(80, 24)) as pilot:
                    await pilot.pause(0.3)
                    await pilot.press("d")
                    await pilot.pause(0.3)
                    await pilot.click("#btn-confirm-ok")
                    await pilot.pause(0.3)
                    assert app.undo_stack.has_action
                    with patch("loghop.tui.screens.home.register_project") as mock_reg:
                        await pilot.press("u")
                        await pilot.pause(0.3)
                        mock_reg.assert_called_once()

        asyncio.run(run())

    def test_home_yank_project_path(self) -> None:
        p = _make_project(name="yankme", path=Path("/tmp/yankme"))
        service = _make_mock_service(projects=[p])

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                with patch.object(app, "copy_to_clipboard"):
                    await pilot.press("y")
                    await pilot.pause(0.3)

        asyncio.run(run())


def test_home_screen_search_filters_projects_by_goal() -> None:
    first = _make_project(name="alpha", goal="ship tui", path=Path("/tmp/alpha"))
    second = _make_project(name="beta", goal="write docs", path=Path("/tmp/beta"))
    service = _make_mock_service(projects=[first, second])

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.3)
            search = app.query_one("#project-search")
            search.focus()
            search.value = "tui"
            await pilot.press("enter")
            await pilot.pause(0.3)

            from textual.widgets._data_table import DataTable

            table = app.query_one("#project-table", DataTable)
            assert table.row_count == 1
            assert str(next(iter(table.rows.keys())).value) == "/tmp/alpha"

    asyncio.run(run())


def test_home_search_focus_and_escape_returns_to_table() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.3)
            await pilot.press("/")
            assert app.focused is app.query_one("#project-search")
            await pilot.press("escape")
            assert app.focused is app.query_one("#project-table")

    asyncio.run(run())
