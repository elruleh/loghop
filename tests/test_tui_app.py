from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from loghop.tui.app import create_app
from loghop.tui.i18n import get_language, set_language, tr
from loghop.tui.services import TuiService
from loghop.tui.widgets.chrome import CommandBar, TopBar

pytestmark = pytest.mark.slow


def _make_mock_service() -> Any:
    """Create a mock TuiService with standard test data."""
    set_language("en")
    service = MagicMock(spec=TuiService)

    project = MagicMock()
    project.name = "repo"
    project.path = Path("/tmp/repo")
    project.goal = "Ship the TUI"
    project.session_count = 1
    project.handoff_count = 0
    project.last_used = "2024-01-01"
    project.current = True

    session = MagicMock()
    session.id = "S-001"
    session.provider = "codex"
    session.status = "succeeded"
    session.summary = "captured"
    session.goal = "Ship the TUI"
    session.ts_start = "2024-01-01T10:00:00"
    session.ts_end = "2024-01-01T11:00:00"
    session.returncode = 0
    session.turns_captured = 5
    session.files_changed = ()

    provider = MagicMock()
    provider.name = "codex"
    provider.installed = True
    provider.path = Path("/usr/bin/codex")
    provider.default = True

    service.projects.return_value = [project]
    service.sessions.return_value = [session]
    service.timeline.return_value = [session]
    service.providers.return_value = [provider]
    service.default_provider.return_value = "codex"

    return service


def test_tui_app_uses_saved_theme_and_language(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MagicMock()
    service.current_project_root.return_value = None
    service.projects.return_value = []

    monkeypatch.setattr(
        "loghop.tui.app.load_tui_preferences",
        lambda: {"theme": "loghopharborlight", "language": "es"},
    )

    async def run() -> None:
        set_language("en")
        app = create_app(service=service, global_view=True)
        async with app.run_test(size=(80, 24)):
            await asyncio.sleep(0.2)
            assert str(app.theme) == "loghopharborlight"
            assert get_language() == "es"

    asyncio.run(run())


def test_run_uses_textual_log_env_without_log_path_kwarg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from loghop.tui import app as app_module

    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    class _App:
        def run(self, *args: Any, **kwargs: Any) -> None:
            calls.append((args, kwargs))

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TEXTUAL_LOG", raising=False)
    monkeypatch.setattr(app_module, "_create_app", lambda **_kwargs: _App())

    code = app_module.run(tui_debug=True)

    assert code == 0
    assert calls == [((), {})]
    assert os.environ["TEXTUAL_LOG"] == ".loghop/tui-debug.log"
    assert (tmp_path / ".loghop").is_dir()


def test_textual_app_home_screen_shows_projects() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test() as pilot:
            await pilot.press("r")
            from textual.widgets._data_table import DataTable

            table = app.query_one("#project-table", DataTable)
            row_keys = list(table.rows.keys())
            assert len(row_keys) == 1
            assert app.query_one("#home-top-bar", TopBar)
            assert app.query_one("#home-command-bar", CommandBar)

    asyncio.run(run())


def test_textual_app_quit_binding() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test() as pilot:
            await pilot.press("q")

    asyncio.run(run())


def test_textual_app_add_folder_modal() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test() as pilot:
            await pilot.press("a")
            assert len(app.screen_stack) == 3
            from loghop.tui.screens.add_folder import AddFolderModal

            modal = app.query_one(AddFolderModal)
            modal.dismiss(False)
            await pilot.pause()
            assert len(app.screen_stack) == 2

    asyncio.run(run())


def test_textual_app_navigates_to_project() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test() as pilot:
            await pilot.press("r")
            from textual.widgets._data_table import DataTable

            table = app.query_one("#project-table", DataTable)
            row_keys = list(table.rows.keys())
            assert len(row_keys) == 1

            await pilot.press("enter")
            assert len(app.screen_stack) > 2

            assert app.query_one("#project-top-bar", TopBar)
            assert app.query_one("#project-command-bar", CommandBar)

    asyncio.run(run())


def test_textual_app_help_overlay() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test() as pilot:
            await pilot.press("question_mark")
            from loghop.tui.screens.help import HelpScreen

            help_screen = app.query_one(HelpScreen)
            help_screen.dismiss(None)
            await pilot.pause()

    asyncio.run(run())


def test_home_command_bar_exposes_core_actions() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.3)
            bar = app.query_one("#home-command-bar", CommandBar)
            rendered = bar._format_actions()
            assert "enter" in rendered
            assert "a" in rendered
            assert "?" in rendered

    asyncio.run(run())


def test_command_menu_finds_theme_aliases() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test():
            from loghop.tui.commands import LoghopCommands

            provider = LoghopCommands(app.screen)
            hits = [hit async for hit in provider.search("oscuro")]
            texts = [str(hit.text) for hit in hits]
            assert any("Theme: Switch to dark" in text for text in texts)

            light = next(hit for hit in hits if "Theme: Switch to dark" in str(hit.text))
            app.theme = "loghopclassiclight"
            light.command()
            assert app.theme == "loghopclassicdark"

    asyncio.run(run())


def test_textual_app_registers_loghop_themes() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test():
            from loghop.tui.themes import THEME_REGISTRY

            for name in THEME_REGISTRY:
                assert name in app.available_themes

    asyncio.run(run())


def test_command_menu_finds_harbor_themes_and_toggles_family() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test():
            from loghop.tui.commands import LoghopCommands
            from loghop.tui.themes import HARBOR_DARK, HARBOR_LIGHT

            provider = LoghopCommands(app.screen)
            hits = [hit async for hit in provider.search("harbor")]
            texts = [str(hit.text) for hit in hits]
            assert any("Theme: Harbor dark" in text for text in texts)
            assert any("Theme: Harbor light" in text for text in texts)

            dark = next(hit for hit in hits if "Theme: Harbor dark" in str(hit.text))
            dark.command()
            assert app.theme == HARBOR_DARK.name

            toggle_hits = [hit async for hit in provider.search("toggle")]
            toggle = next(hit for hit in toggle_hits if "Theme: Toggle dark/light" in str(hit.text))
            toggle.command()
            assert app.theme == HARBOR_LIGHT.name
            toggle.command()
            assert app.theme == HARBOR_DARK.name

    asyncio.run(run())


def test_command_menu_finds_contextual_session_resume() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test() as pilot:
            await pilot.pause(0.3)
            await pilot.press("enter")
            await pilot.wait_for_animation()
            await pilot.pause(0.3)
            from loghop.tui.commands import LoghopCommands

            provider = LoghopCommands(app.screen)
            hits = [hit async for hit in provider.search("resume codex")]
            texts = [str(hit.text) for hit in hits]
            assert any("Sessions: Resume with codex" in text for text in texts)

    asyncio.run(run())


def test_command_menu_skips_missing_projects() -> None:
    service = _make_mock_service()
    service.projects.return_value[0].exists = False

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test():
            from loghop.tui.commands import LoghopCommands

            provider = LoghopCommands(app.screen)
            hits = [hit async for hit in provider.search("open repo")]
            texts = [str(hit.text) for hit in hits]
            assert not any("Open repo" in text for text in texts)

    asyncio.run(run())


def test_sessions_i18n_strings_are_aligned_in_english() -> None:
    set_language("en")

    assert tr("SESSIONS_TITLE") == "Sessions"
    assert tr("SESSIONS_SEARCH_PLACEHOLDER") == "Search sessions..."
    assert tr("SESSIONS_PREVIEW_EMPTY").startswith("Select a session to inspect it.")
    assert tr("SESSIONS_START_EMPTY").startswith("No sessions yet to inspect.")
    assert tr("PREVIEW_BTN_OPEN") == "Open sessions"
    assert tr("CMD_SESSION_RESUME_WITH", provider="codex") == "Sessions: Resume with codex"


def test_sessions_i18n_strings_are_aligned_in_spanish() -> None:
    set_language("es")

    assert tr("SESSIONS_TITLE") == "Sesiones"
    assert tr("SESSIONS_SEARCH_PLACEHOLDER") == "Buscar sesiones..."
    assert tr("SESSIONS_PREVIEW_EMPTY").startswith("Selecciona una sesión para inspeccionarla.")
    assert tr("SESSIONS_START_EMPTY").startswith("Aún no hay sesiones para inspeccionar.")
    assert tr("PREVIEW_BTN_OPEN") == "Abrir sesiones"
    assert tr("CMD_SESSION_RESUME_WITH", provider="codex") == "Sesiones: Reanudar con codex"


def test_i18n_can_switch_command_language() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test() as pilot:
            from loghop.tui.commands import LoghopCommands

            provider = LoghopCommands(app.screen)
            hits = [hit async for hit in provider.search("idioma español")]
            spanish = next(hit for hit in hits if "Language: Spanish" in str(hit.text))
            spanish.command()
            await pilot.pause()

            assert get_language() == "es"
            assert tr("PROJECTS_TITLE") == "Proyectos"
            from textual.widgets import Static

            actions = app.query_one("#home-command-bar .command-bar-actions", Static)
            assert "ayuda" in str(actions.renderable)

            hits = [hit async for hit in provider.search("idioma inglés")]
            english = next(hit for hit in hits if "Idioma: Inglés" in str(hit.text))
            english.command()

            assert get_language() == "en"

    asyncio.run(run())


def test_project_running_session_renders_spinner() -> None:
    """A running session must render the animated Spinner widget without
    crashing — regression for: Spinner._frame_markup ran before _color was set.
    """
    service = _make_mock_service()
    running = MagicMock()
    running.id = "S-RUN"
    running.provider = "claude"
    running.status = "running"
    running.summary = ""
    running.goal = "long-lived"
    running.ts_start = "2026-04-25T15:54:36Z"
    running.ts_end = ""
    running.returncode = None
    running.turns_captured = None
    running.files_changed = ()
    service.sessions.return_value = [running]
    service.timeline.return_value = [running]

    async def run() -> None:
        app = create_app(service=service)
        with patch("loghop.tui.screens.project.ProjectScreen._launch"):
            async with app.run_test() as pilot:
                await pilot.press("r")
                await pilot.press("enter")
                await pilot.pause()

                from loghop.tui.widgets.preview_pane import Spinner

                spinners = list(app.query(Spinner))
                assert spinners, "expected a Spinner for the running session"

    asyncio.run(run())


def test_project_session_click_does_not_launch_provider() -> None:
    """Mouse click on a session row must only update the preview, never launch.
    Regression: enter and click both fire RowSelected — keyboard-only launch
    must come from a priority Screen binding, not from RowSelected.
    """
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        with patch("loghop.tui.screens.project.ProjectScreen._launch") as launch:
            async with app.run_test() as pilot:
                await pilot.press("r")
                await pilot.press("enter")  # opens project from home
                await pilot.pause()

                from textual.widgets import DataTable

                table = app.query_one("#session-table", DataTable)
                await pilot.click(table)
                await pilot.pause()

                assert launch.call_count == 0

    asyncio.run(run())


def test_project_session_enter_launches_default_provider() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        with patch("loghop.tui.screens.project.ProjectScreen._launch") as launch:
            async with app.run_test() as pilot:
                await pilot.press("r")
                await pilot.press("enter")
                await pilot.pause()

                await pilot.press("enter")
                await pilot.pause()

                launch.assert_called_once_with("codex")

    asyncio.run(run())


def test_project_session_enter_without_goal_launches_default_provider() -> None:
    service = _make_mock_service()
    service.projects.return_value[0].goal = ""

    async def run() -> None:
        app = create_app(service=service)
        with patch("loghop.tui.screens.project.launch_in_new_tab") as launch:
            async with app.run_test() as pilot:
                await pilot.press("r")
                await pilot.press("enter")
                await pilot.pause()

                await pilot.press("enter")
                await pilot.pause()

                launch.assert_called_once()

    asyncio.run(run())


def test_project_back_binding_returns_home() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test() as pilot:
            await pilot.pause(0.3)
            await pilot.press("enter")
            await pilot.wait_for_animation()
            await pilot.pause(0.3)
            assert app.query("#session-table")

            await pilot.press("b")
            await pilot.pause(0.3)
            assert app.query("#project-table")
            assert not app.query("#session-table")

    asyncio.run(run())


def test_project_resume_button_launches_selected_provider() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        with patch("loghop.tui.screens.project.ProjectScreen._launch") as launch:
            async with app.run_test() as pilot:
                await pilot.press("r")
                await pilot.press("enter")
                await pilot.pause()

                from textual.widgets import Button

                app.query_one("#resume-codex", Button).press()
                await pilot.pause()

                launch.assert_called_once_with("codex")

    asyncio.run(run())


def test_project_claude_custom_api_does_not_open_terminal() -> None:
    service = _make_mock_service()
    claude = MagicMock()
    claude.name = "claude"
    claude.installed = True
    claude.path = Path("/usr/bin/claude")
    claude.default = False
    service.providers.return_value = [service.providers.return_value[0], claude]

    async def run() -> None:
        app = create_app(service=service)
        with (
            patch("loghop.providers.claude_uses_api_transport", return_value=True),
            patch("loghop.tui.screens.project.launch_in_new_tab") as launch,
        ):
            async with app.run_test() as pilot:
                await pilot.press("r")
                await pilot.press("enter")
                await pilot.pause()

                from textual.widgets import Button

                app.query_one("#resume-claude", Button).press()
                await pilot.pause()

                launch.assert_not_called()

    asyncio.run(run())


def test_project_empty_state_shows_start_buttons() -> None:
    service = _make_mock_service()
    service.sessions.return_value = []
    service.timeline.return_value = []
    service.projects.return_value[0].session_count = 0

    claude = MagicMock()
    claude.name = "claude"
    claude.installed = True
    claude.path = Path("/usr/bin/claude")
    claude.default = False
    service.providers.return_value = [service.providers.return_value[0], claude]

    async def run() -> None:
        app = create_app(service=service)
        with patch("loghop.tui.screens.project.ProjectScreen._launch") as launch:
            async with app.run_test() as pilot:
                await pilot.press("r")
                await pilot.press("enter")
                await pilot.pause()

                from textual.widgets import Button

                assert app.query_one("#resume-codex", Button)
                app.query_one("#resume-claude", Button).press()
                await pilot.pause()

                launch.assert_called_once_with("claude")

    asyncio.run(run())


def test_textual_app_search_filters_projects() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test() as pilot:
            await pilot.press("r")
            from textual.widgets import Input
            from textual.widgets._data_table import DataTable

            search = app.query_one("#project-search", Input)
            search.value = "no-such-project"
            await pilot.pause(0.4)
            table = app.query_one("#project-table", DataTable)
            assert table.row_count == 0

            search.value = ""
            await pilot.pause(0.4)
            assert table.row_count == 1

    asyncio.run(run())


def test_refresh_translations_avoid_recompose() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test() as pilot:
            await pilot.pause()

            screen = app.screen
            assert hasattr(screen, "refresh_translations")

            screen.refresh = MagicMock(side_effect=screen.refresh)

            app.set_language("es")
            await pilot.pause()

            # Check that screen.refresh was not called with recompose=True
            for call in screen.refresh.call_args_list:
                assert not call.kwargs.get("recompose", False)
            from loghop.tui import strings

            assert screen.sub_title == strings.PROJECTS_TITLE

    asyncio.run(run())


def test_home_screen_latest_cache_bounds() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test() as pilot:
            await pilot.pause()

            screen = app.screen
            screen._latest_cache.clear()
            for i in range(100):
                screen._latest_cache[f"key_{i}"] = f"value_{i}"

            screen._preview_project_key = "/tmp/dummy"
            screen._preview_generation = 1

            class DummyProject:
                exists = True
                path = Path("/tmp/dummy")
                goal = ""

            with patch("textual.worker.get_current_worker") as mock_worker:
                mock_worker.return_value.is_cancelled = False
                screen._fetch_preview_data(DummyProject(), 1, "/tmp/dummy")

            await pilot.pause()
            assert len(screen._latest_cache) <= 100
            assert "key_0" not in screen._latest_cache

    asyncio.run(run())


def test_project_screen_conversation_cache_bounds() -> None:
    from loghop.tui.screens.project import ProjectScreen

    screen = ProjectScreen(MagicMock(), "/tmp/project")

    screen._active = True
    screen._preview_session_id = "new_sid"

    for i in range(100):
        screen._conversation_cache[f"sid_{i}"] = (("user", "msg"),)

    screen._on_conversation_excerpt("new_sid", (("user", "new_msg"),), 1)

    assert len(screen._conversation_cache) <= 100
    assert "sid_0" not in screen._conversation_cache


def test_home_screen_actions_contain_remove() -> None:
    from loghop.tui.screens.home import HomeScreen

    default_actions = HomeScreen._default_actions()
    default_keys = [a[0] for a in default_actions]
    assert "d" in default_keys

    screen = HomeScreen(MagicMock())
    screen._projects_cache = [MagicMock()]
    active_actions = screen._actions()
    active_keys = [a[0] for a in active_actions]
    assert "d" in active_keys


def test_project_screen_actions_contain_delete() -> None:
    from loghop.tui.screens.project import ProjectScreen

    default_actions = ProjectScreen._default_actions()
    default_keys = [a[0] for a in default_actions]
    assert "d" in default_keys

    screen = ProjectScreen(MagicMock(), "/tmp/project")
    screen._sessions_cache = [MagicMock()]
    screen._top_bar = MagicMock()
    screen._command_bar = MagicMock()
    screen._search_input = MagicMock()
    screen._search_input.has_focus = False
    screen._default_provider = "codex"
    screen._loading_spinner = False

    screen._update_chrome(shown=1, total=1, query="", flags=set())

    calls = screen._command_bar.set_actions.call_args_list
    assert len(calls) > 0
    actions = calls[0][0][0]
    keys = [a[0] for a in actions]
    assert "d" in keys


def test_confirm_modal_bindings() -> None:
    from loghop.tui.screens.confirm import ConfirmModal, ConfirmSpec

    spec = ConfirmSpec(
        title="Test Title", message="Test Msg", confirm_label="Confirm", cancel_label="Cancel"
    )
    modal = ConfirmModal(spec)

    # Check that 's' is bound to 'confirm'
    s_binding = next((b for b in modal.BINDINGS if b.key == "s"), None)
    assert s_binding is not None
    assert s_binding.action == "confirm"
    assert s_binding.show is False


def test_add_folder_modal_hints() -> None:
    from loghop.tui.screens.add_folder import AddFolderModal

    service = MagicMock()
    service.current_project_root.return_value = None
    service.projects.return_value = []

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test() as pilot:
            # open the add folder modal
            await pilot.press("a")
            modal = app.query_one(AddFolderModal)

            # verify add-hint exists
            hint = modal.query_one("#add-hint")
            assert hint is not None

            # initially browse is False, so it should display autocomplete hint
            assert tr("ADD_AUTOCOMPLETE_HINT") in str(hint.renderable)

            # toggle browse
            modal._set_browse_open(True)
            assert tr("ADD_BROWSE_HINT") in str(hint.renderable)

            # toggle back
            modal._set_browse_open(False)
            assert tr("ADD_AUTOCOMPLETE_HINT") in str(hint.renderable)

            # test refresh_translations
            set_language("es")
            modal.refresh_translations()
            assert tr("ADD_AUTOCOMPLETE_HINT") in str(hint.renderable)

            # dismiss modal
            modal.dismiss(False)
            await pilot.pause()

    asyncio.run(run())


def test_help_screen_refresh_translations() -> None:
    from loghop.tui.screens.help import HelpScreen

    async def run() -> None:
        app = create_app(service=_make_mock_service())
        async with app.run_test() as pilot:
            # open help screen
            await pilot.press("?")
            help_screen = app.query_one(HelpScreen)

            # verify translation works without raising exceptions
            set_language("es")
            help_screen.refresh_translations()

            # check the title was updated
            title = help_screen.query_one("#help-title")
            assert tr("HELP_TITLE") in str(title.renderable)

            # dismiss screen
            help_screen.dismiss(None)
            await pilot.pause()

    asyncio.run(run())
