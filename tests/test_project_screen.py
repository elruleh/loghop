# mypy: disable-error-code="no-untyped-def"
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from loghop.tui.app import create_app
from loghop.tui.format import format_duration
from loghop.tui.i18n import set_language, tr
from loghop.tui.models import PROVIDER_SHORTCUTS
from loghop.tui.screens._project_vm import (
    _SORT_PROVIDER,
    _SORT_STATUS,
    _SORT_TIME,
    _matches_flag,
    matches_text,
)
from loghop.tui.screens._project_vm import (
    sort_sessions as _sort_sessions,
)
from loghop.tui.screens.help import _session_rows
from loghop.tui.screens.project import ProjectScreen
from loghop.tui.services import TuiService


def _make_session(**overrides) -> Any:
    s = MagicMock()
    s.id = "S-001"
    s.provider = "codex"
    s.status = "succeeded"
    s.summary = "done"
    s.goal = "ship it"
    s.ts_start = "2024-01-01T10:00:00Z"
    s.ts_end = "2024-01-01T11:00:00Z"
    s.returncode = 0
    s.turns_captured = 5
    s.files_changed = ()
    s.decisions = ()
    s.todos_pending = ()
    s.todos_done = ()
    s.handoff_id = ""
    s.path = Path("/tmp/repo/.loghop/sessions/S-001.md")
    s.transcript_path = ""
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _make_timeline_event(**overrides) -> Any:
    event = _make_session(**overrides)
    event.session_id = getattr(event, "id", "S-001")
    event.title = overrides.get(
        "title", overrides.get("summary", getattr(event, "summary", "done"))
    )
    event.is_live = overrides.get("is_live", False)
    return event


def _make_mock_service(sessions=None, providers=None) -> Any:
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

    provider = MagicMock()
    provider.name = "codex"
    provider.installed = True
    provider.path = Path("/usr/bin/codex")
    provider.default = True

    service.projects.return_value = [project]
    service.sessions.return_value = [_make_session()] if sessions is None else sessions
    service.timeline.return_value = [_make_timeline_event()] if sessions is None else sessions
    service.providers.return_value = [provider] if providers is None else providers
    service.default_provider.return_value = "codex"
    service.current_project_root.return_value = Path("/tmp/repo")
    return service


def _make_project_screen(service=None) -> ProjectScreen:
    return ProjectScreen(service or _make_mock_service(), "/tmp/repo")


def test_project_screen_preview_shows_session_summary_and_provider() -> None:
    session = _make_session(summary="fixed preview", files_changed=("src/loghop/tui/app.py",))
    service = _make_mock_service(sessions=[session])

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test(size=(100, 30)) as pilot:
            app.open_project("/tmp/repo")
            await pilot.pause()
            await pilot.pause(0.5)

            preview_text = "\n".join(str(widget.renderable) for widget in app.query("Static"))
            assert "fixed preview" in preview_text
            assert "codex" in preview_text

    asyncio.run(run())


def test_project_vm_format_list_block_limits_items() -> None:
    from loghop.tui.screens._project_vm import format_list_block

    result = format_list_block(("one", "two", "three"), limit=2)

    assert "one" in result
    assert "two" in result
    assert "three" not in result
    assert "1" in result


def test_project_vm_format_files_block_truncates_to_limit() -> None:
    from loghop.tui.screens._project_vm import format_files_block

    result = format_files_block(("src/a.py", "src/b.py", "src/c.py"), limit=2)

    assert "a.py" in result
    assert "b.py" in result
    assert "src" in result
    assert "c.py" not in result
    assert "1" in result


def test_project_vm_format_todos_block_prefers_pending_items() -> None:
    from loghop.tui.screens._project_vm import format_todos_block

    result = format_todos_block(("fix focus",), ("write tests",))

    assert "fix focus" in result
    assert "write tests" in result


def test_project_vm_format_conversation_excerpt_uses_recent_turns() -> None:
    from loghop.tui.screens._project_vm import format_conversation_excerpt

    session = _make_session(conversation_excerpt=("first", "second", "third"))
    result = format_conversation_excerpt(session, limit=2)

    assert "first" in result
    assert "second" in result
    assert "third" not in result


def test_project_search_focus_and_escape_returns_to_table() -> None:
    service = _make_mock_service()

    async def run() -> None:
        app = create_app(service=service)
        async with app.run_test(size=(100, 30)) as pilot:
            app.open_project("/tmp/repo")
            await pilot.pause(0.5)
            await pilot.press("/")
            assert app.focused is app.query_one("#filter-search")
            await pilot.press("escape")
            assert app.focused is app.query_one("#session-table")

    asyncio.run(run())


# ── Pure unit tests ──


class TestMatchesFlag:
    def test_running(self) -> None:
        s = _make_session(status="running")
        assert _matches_flag(s, "running") is True
        assert _matches_flag(s, "failed") is False

    def test_failed(self) -> None:
        s = _make_session(status="failed")
        assert _matches_flag(s, "failed") is True

    def test_launch_failed(self) -> None:
        s = _make_session(status="launch_failed")
        assert _matches_flag(s, "failed") is True

    def test_interrupted_counts_as_failed(self) -> None:
        s = _make_session(status="interrupted")
        assert _matches_flag(s, "failed") is True

    def test_timed_out_counts_as_failed(self) -> None:
        s = _make_session(status="timed_out")
        assert _matches_flag(s, "failed") is True

    def test_done(self) -> None:
        s = _make_session(status="succeeded")
        assert _matches_flag(s, "done") is True

    def test_not_done_when_running(self) -> None:
        s = _make_session(status="running")
        assert _matches_flag(s, "done") is False

    def test_unknown_flag_passes(self) -> None:
        s = _make_session(status="succeeded")
        assert _matches_flag(s, "weird") is True

    def test_empty_status(self) -> None:
        s = _make_session(status="")
        assert _matches_flag(s, "running") is False


class TestSortSessions:
    def test_sort_by_status(self) -> None:
        running = _make_session(status="running", ts_start="2024-01-03")
        succeeded = _make_session(status="succeeded", ts_start="2024-01-01")
        failed = _make_session(status="failed", ts_start="2024-01-02")
        result = _sort_sessions([succeeded, running, failed], _SORT_STATUS)
        assert result[0].status == "running"
        assert result[1].status == "failed"
        assert result[2].status == "succeeded"

    def test_sort_by_provider(self) -> None:
        claude = _make_session(provider="claude", ts_start="2024-01-02")
        codex = _make_session(provider="codex", ts_start="2024-01-01")
        result = _sort_sessions([claude, codex], _SORT_PROVIDER)
        assert result[0].provider == "claude"
        assert result[1].provider == "codex"

    def test_sort_by_time_preserves_order(self) -> None:
        a = _make_session(id="S-1", ts_start="2024-01-01")
        b = _make_session(id="S-2", ts_start="2024-01-02")
        result = _sort_sessions([a, b], _SORT_TIME)
        assert result[0].id == "S-1"

    def test_sort_by_status_tiebreak_by_time(self) -> None:
        a = _make_session(status="failed", ts_start="2024-01-01")
        b = _make_session(status="failed", ts_start="2024-01-02")
        result = _sort_sessions([b, a], _SORT_STATUS)
        assert result[0].ts_start == "2024-01-02"


class TestBuildMetaLines:
    def test_empty_when_no_data(self) -> None:
        primary, secondary = ProjectScreen._build_meta_lines(
            provider="", ts_start="", ts_end="", turns=None, files_count=0, returncode=None
        )
        assert primary == ""
        assert secondary == ""

    def test_shows_provider(self) -> None:
        primary, secondary = ProjectScreen._build_meta_lines(
            provider="codex", ts_start="", ts_end="", turns=None, files_count=0, returncode=None
        )
        assert "codex" in primary or "codex" in secondary

    def test_shows_duration(self) -> None:
        primary, secondary = ProjectScreen._build_meta_lines(
            provider="",
            ts_start="2024-01-01T10:00:00Z",
            ts_end="2024-01-01T10:05:30Z",
            turns=None,
            files_count=0,
            returncode=None,
        )
        combined = f"{primary} {secondary}"
        assert "5m" in combined

    def test_shows_turns(self) -> None:
        primary, secondary = ProjectScreen._build_meta_lines(
            provider="", ts_start="", ts_end="", turns=12, files_count=0, returncode=None
        )
        assert "12" in primary or "12" in secondary

    def test_shows_files_count(self) -> None:
        primary, secondary = ProjectScreen._build_meta_lines(
            provider="", ts_start="", ts_end="", turns=None, files_count=7, returncode=None
        )
        assert "7" in primary or "7" in secondary

    def test_shows_returncode(self) -> None:
        primary, secondary = ProjectScreen._build_meta_lines(
            provider="", ts_start="", ts_end="", turns=None, files_count=0, returncode=1
        )
        assert "1" in primary or "1" in secondary

    def test_shows_timestamp_range(self) -> None:
        primary, secondary = ProjectScreen._build_meta_lines(
            provider="",
            ts_start="2024-01-01T10:00:00Z",
            ts_end="2024-01-01T10:30:00Z",
            turns=None,
            files_count=0,
            returncode=None,
        )
        combined = f"{primary} {secondary}"
        assert "→" in combined

    def test_zero_files_not_shown(self) -> None:
        primary, secondary = ProjectScreen._build_meta_lines(
            provider="codex", ts_start="", ts_end="", turns=None, files_count=0, returncode=None
        )
        combined = f"{primary} {secondary}"
        assert combined.count("0") == 0 or "Files" not in combined


class TestFormatTodosBlock:
    def test_pending_items(self) -> None:
        result = ProjectScreen._format_todos_block(("task1", "task2"), ())
        assert "☐ task1" in result
        assert "☐ task2" in result

    def test_done_items(self) -> None:
        result = ProjectScreen._format_todos_block((), ("done1",))
        assert "☑ done1" in result

    def test_truncates_pending(self) -> None:
        items = tuple(f"t{i}" for i in range(5))
        result = ProjectScreen._format_todos_block(items, ())
        assert "☐ t0" in result
        assert "more" in result.lower() or "…" in result

    def test_truncates_done(self) -> None:
        items = tuple(f"d{i}" for i in range(5))
        result = ProjectScreen._format_todos_block((), items)
        assert "☑ d0" in result

    def test_empty(self) -> None:
        result = ProjectScreen._format_todos_block((), ())
        assert result == ""


class TestPreviewConversation:
    def test_preview_sections_include_conversation_excerpt(self) -> None:
        screen = _make_project_screen()
        preview = MagicMock()
        session = _make_session(
            conversation_excerpt=(
                ("user", "continue from Claude"),
                ("assistant", "Codex picked up the handoff"),
            )
        )

        screen._render_preview_sections(preview, session)

        sections = [call.args for call in preview.add_section.call_args_list]
        assert any(args[0] == tr("SESSION_CONVERSATION") for args in sections)
        body = "\n".join(str(args[1]) for args in sections)
        assert "continue from Claude" in body
        assert "Codex picked up the handoff" in body


class TestHelpBindings:
    def test_provider_shortcuts_match_supported_provider_bindings(self) -> None:
        shortcut_text = next(
            keys for keys, desc in _session_rows() if desc == tr("HELP_RESUME_PROVIDER")
        )
        advertised = {part.strip() for part in shortcut_text.split("/")}

        assert advertised == set(PROVIDER_SHORTCUTS.values())


class TestProjectActions:
    def test_provider_filter_action_copy_is_not_switch_provider(self) -> None:
        actions = dict(ProjectScreen._default_actions())

        assert actions["f"] == tr("ACTION_FILTER_PROVIDER")


class TestFormatListBlock:
    def test_basic_items(self) -> None:
        result = ProjectScreen._format_list_block(("a", "b"), limit=5)
        assert "a" in result
        assert "b" in result

    def test_truncates_at_limit(self) -> None:
        items = tuple(f"x{i}" for i in range(10))
        result = ProjectScreen._format_list_block(items, limit=3)
        assert "more" in result.lower() or "…" in result

    def test_empty(self) -> None:
        result = ProjectScreen._format_list_block((), limit=5)
        assert result == ""


class TestFormatFilesBlock:
    def test_filename_only(self) -> None:
        result = ProjectScreen._format_files_block(("main.py",), limit=5)
        assert "main.py" in result

    def test_file_with_parent(self) -> None:
        result = ProjectScreen._format_files_block(("src/main.py",), limit=5)
        assert "main.py" in result
        assert "src" in result

    def test_truncates_at_limit(self) -> None:
        files = tuple(f"f{i}.py" for i in range(10))
        result = ProjectScreen._format_files_block(files, limit=3)
        assert "more" in result.lower() or "…" in result


class TestFormatDuration:
    def test_seconds(self) -> None:
        result = format_duration("2024-01-01T10:00:00Z", "2024-01-01T10:00:30Z")
        assert result == "30s"

    def test_minutes(self) -> None:
        result = format_duration("2024-01-01T10:00:00Z", "2024-01-01T10:45:00Z")
        assert result == "45m"

    def test_hours(self) -> None:
        result = format_duration("2024-01-01T10:00:00Z", "2024-01-01T12:30:00Z")
        assert result == "2h 30m"

    def test_no_start(self) -> None:
        result = format_duration("", "2024-01-01T10:00:30Z")
        assert result == "—"

    def test_no_end_shows_running(self) -> None:
        result = format_duration("2024-01-01T10:00:00Z", "")
        assert "running" in result.lower() or result != "—"

    def test_same_start_and_end(self) -> None:
        result = format_duration("2024-01-01T10:00:00Z", "2024-01-01T10:00:00Z")
        assert result == "—"

    def test_exactly_one_hour(self) -> None:
        result = format_duration("2024-01-01T10:00:00Z", "2024-01-01T11:00:00Z")
        assert result == "1h 0m"


class TestFormatTimestamp:
    def test_valid_timestamp(self) -> None:
        result = ProjectScreen._format_timestamp("2024-01-15T10:30:00Z")
        assert "2024-01-15" in result
        assert "10:30" in result

    def test_invalid_timestamp(self) -> None:
        result = ProjectScreen._format_timestamp("")
        assert result == "—"


class TestFormatEnd:
    def test_valid_ts(self) -> None:
        result = ProjectScreen._format_end("2024-01-15T10:30:00Z")
        assert "10:30" in result

    def test_empty_ts(self) -> None:
        result = ProjectScreen._format_end("")
        assert "running" in result.lower() or result != ""


class TestTruncateBlock:
    def test_short_text_unchanged(self) -> None:
        result = ProjectScreen._truncate_block("hello", max_lines=3, max_chars=100)
        assert result == "hello"

    def test_truncates_long_lines(self) -> None:
        long_text = "x" * 300
        result = ProjectScreen._truncate_block(long_text, max_lines=3, max_chars=220)
        assert len(result) < 300

    def test_truncates_many_lines(self) -> None:
        many_lines = "\n".join(f"line {i}" for i in range(10))
        result = ProjectScreen._truncate_block(many_lines, max_lines=3, max_chars=10000)
        assert result.count("\n") <= 4

    def test_empty_string(self) -> None:
        result = ProjectScreen._truncate_block("", max_lines=3, max_chars=100)
        assert result == ""

    def test_whitespace_only(self) -> None:
        result = ProjectScreen._truncate_block("   ", max_lines=3, max_chars=100)
        assert result == ""


class TestFormatFileEntry:
    def test_filename_only(self) -> None:
        result = ProjectScreen._format_file_entry("main.py")
        assert result == "main.py"

    def test_with_parent(self) -> None:
        result = ProjectScreen._format_file_entry("src/main.py")
        assert "main.py" in result
        assert "src" in result

    def test_deep_path(self) -> None:
        result = ProjectScreen._format_file_entry("a/b/c/main.py")
        assert "main.py" in result


class TestEntityForKey:
    def test_finds_matching_session(self) -> None:
        screen = MagicMock(spec=ProjectScreen)
        s = _make_session(id="S-001")
        screen._sessions_cache = [s]
        result = ProjectScreen._entity_for_key(screen, MagicMock(value="S-001"))
        assert result is s

    def test_returns_none_for_no_match(self) -> None:
        screen = MagicMock(spec=ProjectScreen)
        screen._sessions_cache = []
        result = ProjectScreen._entity_for_key(screen, MagicMock(value="S-999"))
        assert result is None


class TestYankValue:
    def test_returns_session_id(self) -> None:
        s = _make_session(id="S-042")
        assert ProjectScreen._yank_value(s) == "S-042"

    def test_returns_empty_for_no_id(self) -> None:
        s = _make_session()
        s.id = ""
        assert ProjectScreen._yank_value(s) == ""


class TestMatchesText:
    def test_matches_id(self) -> None:
        s = _make_session(id="S-ABC")
        assert matches_text(s, "s-abc") is True

    def test_matches_provider(self) -> None:
        s = _make_session(provider="claude")
        assert matches_text(s, "claude") is True

    def test_matches_goal(self) -> None:
        s = _make_session(goal="ship the feature")
        assert matches_text(s, "feature") is True

    def test_matches_summary(self) -> None:
        s = _make_session(summary="captured output")
        assert matches_text(s, "output") is True

    def test_matches_status(self) -> None:
        s = _make_session(status="succeeded")
        assert matches_text(s, "succeeded") is True

    def test_no_match(self) -> None:
        s = _make_session(id="S-001", provider="codex", goal="", summary="", status="succeeded")
        assert matches_text(s, "zzz") is False


class TestBuildResumeHint:
    def test_has_enter(self) -> None:
        result = ProjectScreen._build_resume_hint(["codex"])
        assert "resume" in result.lower()

    def test_has_shortcut(self) -> None:
        result = ProjectScreen._build_resume_hint(["codex"])
        assert "codex" in result.lower()

    def test_multiple_providers(self) -> None:
        result = ProjectScreen._build_resume_hint(["codex", "claude"])
        assert "codex" in result.lower()
        assert "claude" in result.lower()


class TestDefaultActions:
    def test_returns_list(self) -> None:
        actions = ProjectScreen._default_actions()
        assert isinstance(actions, list)
        assert len(actions) >= 3

    def test_contains_resume(self) -> None:
        keys = [a[0] for a in ProjectScreen._default_actions()]
        assert "enter" in keys


class TestRelativeToProject:
    def test_within_project(self) -> None:
        screen = MagicMock(spec=ProjectScreen)
        screen._project_path = Path("/tmp/repo")
        result = ProjectScreen._relative_to_project(screen, Path("/tmp/repo/src/main.py"))
        assert result == "src/main.py"

    def test_outside_project(self) -> None:
        screen = MagicMock(spec=ProjectScreen)
        screen._project_path = Path("/tmp/repo")
        result = ProjectScreen._relative_to_project(screen, Path("/other/path"))
        assert result == "/other/path"


class TestSessionsCopy:
    def test_record_labels_are_explicit_in_english(self) -> None:
        set_language("en")

        lines = ProjectScreen._build_record_lines(
            "S-001",
            "H-001",
            Path("/tmp/repo/.loghop/sessions/S-001.md"),
            "/tmp/repo/.loghop/transcripts/S-001.md",
        )

        assert any("Session ID" in line for line in lines)
        assert any("Handoff ID" in line for line in lines)
        assert any("Session file" in line for line in lines)
        assert any("Transcript available" in line for line in lines)

    def test_record_labels_are_explicit_in_spanish(self) -> None:
        set_language("es")

        lines = ProjectScreen._build_record_lines(
            "S-001",
            "H-001",
            Path("/tmp/repo/.loghop/sessions/S-001.md"),
            "/tmp/repo/.loghop/transcripts/S-001.md",
        )

        assert any("ID de sesión" in line for line in lines)
        assert any("ID de handoff" in line for line in lines)
        assert any("Archivo de sesión" in line for line in lines)
        assert any("Transcripción disponible" in line for line in lines)

    def test_next_vocabulary_is_consistent_in_english(self) -> None:
        set_language("en")

        assert tr("PROJECT_NEXT_UP") == "Next"
        assert tr("SESSION_TABLE_PENDING") == "Next"
        assert tr("SESSION_TODOS", pending=2, sep="·", done=1).startswith("Next steps")

    def test_next_vocabulary_is_consistent_in_spanish(self) -> None:
        set_language("es")

        assert tr("PROJECT_NEXT_UP") == "Siguiente"
        assert tr("SESSION_TABLE_PENDING") == "Siguiente"
        assert tr("SESSION_TODOS", pending=2, sep="·", done=1).startswith("Siguientes pasos")

    def test_narrow_actions_are_named_explicitly(self) -> None:
        set_language("en")

        assert tr("ACTION_DETAILS") == "detail"
        assert tr("ACTION_LIST") == "list"


def test_filter_chip_can_be_dismissed_with_keyboard() -> None:
    from textual.app import App, ComposeResult

    from loghop.tui.widgets.filter_chips import ChipDismissed, FilterChips

    dismissed: list[str] = []

    class ChipApp(App[None]):
        def compose(self) -> ComposeResult:
            chips = FilterChips(id="chips")
            chips.set_chips([("Codex ×", "provider:codex")])
            yield chips

        def on_chip_dismissed(self, event: ChipDismissed) -> None:
            dismissed.append(event.key)

    async def run() -> None:
        app = ChipApp()
        async with app.run_test(size=(60, 10)) as pilot:
            await pilot.pause(0.2)
            chip = app.query_one(".filter-chip")
            chip.focus()
            await pilot.press("enter")
            await pilot.pause(0.1)

    asyncio.run(run())

    assert dismissed == ["provider:codex"]


# ── Async TUI tests ──


class TestProjectScreenAsync:
    def test_project_preview_lazy_loads_conversation_excerpt(self) -> None:
        from types import SimpleNamespace

        from textual.widgets import Static

        root = Path("/tmp/demo")
        project = SimpleNamespace(
            name="demo",
            path=root,
            goal="",
            registered="",
            last_used="2026-05-21T10:00:00Z",
            last_session="",
            session_count=1,
            handoff_count=0,
            exists=True,
            current=True,
        )
        session = SimpleNamespace(
            id="S-001",
            session_id="S-001",
            provider="codex",
            goal="Ship preview",
            status="succeeded",
            summary="captured summary",
            title="captured summary",
            ts_start="2026-05-21T10:00:00Z",
            ts_end="2026-05-21T10:10:00Z",
            path=root / ".loghop/sessions/S-001.md",
            handoff_id="",
            topic_id="",
            returncode=0,
            turns_captured=2,
            files_changed=(),
            decisions=(),
            todos_pending=(),
            todos_done=(),
            transcript_path=".loghop/sessions/S-001.transcript.jsonl",
            conversation_excerpt=(),
            is_live=False,
        )
        provider = SimpleNamespace(name="codex", installed=True, default=True)

        service = MagicMock()
        service.current_project_root.return_value = root
        service.projects.return_value = [project]
        service.providers.return_value = [provider]
        service.default_provider.return_value = "codex"
        service.timeline.return_value = [session]
        service.conversation_excerpt.return_value = (
            ("user", "continue from Claude"),
            ("assistant", "Codex picked up the handoff"),
        )

        async def run() -> None:
            app = create_app(service=service, global_view=False)
            async with app.run_test(size=(100, 30)):
                await asyncio.sleep(0.7)
                preview_text = "\n".join(
                    str(node.renderable)
                    for node in app.query(Static)
                    if "preview-section" in " ".join(node.classes)
                )
                assert "Conversation" in preview_text
                assert "continue from Claude" in preview_text
                assert "Codex picked up the handoff" in preview_text

        asyncio.run(run())

        service.conversation_excerpt.assert_called_once_with(root, "S-001")

    def test_project_sessions_loaded(self) -> None:
        s1 = _make_timeline_event(id="S-001", summary="first update", title="first update")
        s2 = _make_timeline_event(id="S-002", summary="second update", title="second update")
        service = _make_mock_service(sessions=[s1, s2])

        async def run() -> None:
            app = create_app(service=service)
            with patch("loghop.tui.screens.project.ProjectScreen._launch"):
                async with app.run_test(size=(80, 24)) as pilot:
                    await pilot.press("r")
                    await pilot.press("enter")
                    await pilot.pause(0.5)
                    from textual.widgets._data_table import DataTable

                    table = app.query_one("#session-table", DataTable)
                    assert table.row_count == 2

        asyncio.run(run())

    def test_project_with_sessions(self) -> None:
        s1 = _make_timeline_event(id="S-001", summary="first update", title="first update")
        s2 = _make_timeline_event(id="S-002", summary="second update", title="second update")
        service = _make_mock_service(sessions=[s1, s2])

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("enter")
                await pilot.wait_for_animation()
                await pilot.pause(0.3)
                from textual.widgets._data_table import DataTable

                table = app.query_one("#session-table", DataTable)
                assert table.row_count == 2

        asyncio.run(run())

    def test_project_service_error(self) -> None:
        service = _make_mock_service()
        service.timeline.side_effect = RuntimeError("fail")

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("enter")
                await pilot.wait_for_animation()
                await pilot.pause(0.3)
                from textual.widgets import Static

                empty = app.query_one("#sessions-empty", Static)
                assert empty.display is True

        asyncio.run(run())

    def test_project_escape_from_search(self) -> None:
        service = _make_mock_service()

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("enter")
                await pilot.wait_for_animation()
                await pilot.pause(0.3)
                await pilot.press("/")
                await pilot.pause(0.3)
                await pilot.press("escape")
                await pilot.pause(0.3)
                from textual.widgets._data_table import DataTable

                table = app.query_one("#session-table", DataTable)
                assert table is not None

        asyncio.run(run())

    def test_project_clear_filters(self) -> None:
        service = _make_mock_service()

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("enter")
                await pilot.wait_for_animation()
                await pilot.pause(0.3)
                await pilot.press("x")
                await pilot.pause(0.3)

        asyncio.run(run())

    def test_project_cycle_provider(self) -> None:
        service = _make_mock_service()

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("enter")
                await pilot.wait_for_animation()
                await pilot.pause(0.3)
                await pilot.press("f")
                await pilot.pause(0.3)
                await pilot.press("f")
                await pilot.pause(0.3)

        asyncio.run(run())

    def test_project_delete_no_selection_no_crash(self) -> None:
        service = _make_mock_service(sessions=[])

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("enter")
                await pilot.wait_for_animation()
                await pilot.pause(0.3)
                await pilot.press("d")
                await pilot.pause(0.3)

        asyncio.run(run())

    def test_project_delete_running_session_is_allowed_after_confirmation(self) -> None:
        service = _make_mock_service(sessions=[_make_timeline_event(status="running")])

        async def run() -> None:
            app = create_app(service=service)
            with patch("loghop.store.delete_session") as delete_session:
                async with app.run_test(size=(80, 24)) as pilot:
                    await pilot.pause(0.3)
                    await pilot.press("enter")
                    await pilot.wait_for_animation()
                    await pilot.pause(0.3)
                    await pilot.press("d")
                    await pilot.pause(0.3)
                    await pilot.click("#btn-confirm-ok")
                    await pilot.pause(0.3)

                delete_session.assert_called_once()

        asyncio.run(run())

    def test_project_no_providers_installed(self) -> None:
        no_prov = MagicMock()
        no_prov.name = "codex"
        no_prov.installed = False
        service = _make_mock_service(providers=[no_prov])

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("enter")
                await pilot.wait_for_animation()
                await pilot.pause(0.3)

        asyncio.run(run())

    def test_project_table_shows_summary_title(self) -> None:
        event = _make_timeline_event(
            id="S-003",
            summary="Refined project timeline preview",
            title="Refined project timeline preview",
            todos_pending=("ship polish",),
        )
        service = _make_mock_service(sessions=[event])

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(100, 28)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("enter")
                await pilot.wait_for_animation()
                await pilot.pause(0.3)
                from textual.widgets import DataTable

                table = app.query_one("#session-table", DataTable)
                cell = table.get_cell_at((0, 1))
                assert "Refined project timeline preview" in str(cell)

        asyncio.run(run())

    def test_project_narrow_hides_preview_until_tab(self) -> None:
        service = _make_mock_service()

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(72, 24)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("enter")
                await pilot.wait_for_animation()
                await pilot.pause(0.3)

                from textual.widgets import Static

                preview = app.query_one("#session-preview")
                actions = app.query_one("#project-command-bar .command-bar-actions", Static)
                assert preview.display is False
                assert "detail" in str(actions.renderable)

                await pilot.press("tab")
                await pilot.pause(0.3)

                actions = app.query_one("#project-command-bar .command-bar-actions", Static)
                assert preview.display is True
                assert "list" in str(actions.renderable)

        asyncio.run(run())

    def test_project_narrow_escape_closes_preview_before_leaving(self) -> None:
        service = _make_mock_service()

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(72, 24)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("enter")
                await pilot.wait_for_animation()
                await pilot.pause(0.3)
                await pilot.press("tab")
                await pilot.pause(0.3)

                preview = app.query_one("#session-preview")
                assert preview.display is True

                await pilot.press("escape")
                await pilot.pause(0.3)

                assert app.query("#session-table")
                assert preview.display is False

        asyncio.run(run())

    def test_project_go_back_action(self) -> None:
        service = _make_mock_service()

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("enter")
                await pilot.wait_for_animation()
                await pilot.pause(0.3)
                await pilot.press("b")
                await pilot.pause(0.3)
                from textual.widgets._data_table import DataTable

                table = app.query_one("#project-table", DataTable)
                assert table is not None

        asyncio.run(run())

    def test_project_provider_shortcut_c(self) -> None:
        claude_prov = MagicMock()
        claude_prov.name = "claude"
        claude_prov.installed = True
        claude_prov.path = Path("/usr/bin/claude")
        claude_prov.default = False
        codex_prov = MagicMock()
        codex_prov.name = "codex"
        codex_prov.installed = True
        codex_prov.path = Path("/usr/bin/codex")
        codex_prov.default = True
        service = _make_mock_service(providers=[claude_prov, codex_prov])

        async def run() -> None:
            app = create_app(service=service)
            with patch("loghop.tui.screens.project.ProjectScreen._launch") as mock_launch:
                async with app.run_test(size=(80, 24)) as pilot:
                    await pilot.pause(0.3)
                    await pilot.press("enter")
                    await pilot.wait_for_animation()
                    await pilot.pause(0.3)
                    await pilot.press("c")
                    await pilot.pause(0.3)
                    mock_launch.assert_called_once_with("claude")

        asyncio.run(run())

    def test_project_escape_narrow_preview(self) -> None:
        service = _make_mock_service()

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(72, 24)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("enter")
                await pilot.wait_for_animation()
                await pilot.pause(0.3)
                await pilot.press("tab")
                await pilot.pause(0.3)
                preview = app.query_one("#session-preview")
                assert preview.display is True
                await pilot.press("escape")
                await pilot.pause(0.3)
                assert preview.display is False

        asyncio.run(run())

    def test_project_narrow_empty_state_keeps_preview_visible(self) -> None:
        service = _make_mock_service(sessions=[])
        service.timeline.return_value = []
        service.projects.return_value[0].session_count = 0

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(72, 24)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("enter")
                await pilot.wait_for_animation()
                await pilot.pause(0.3)

                from textual.widgets import Button

                preview = app.query_one("#session-preview")
                assert preview.display is True
                assert app.query_one("#resume-codex", Button)

        asyncio.run(run())
