from __future__ import annotations

from unittest.mock import MagicMock

from loghop.tui.screens._list_shared import (
    ListScreen,
    _parse_search,
    _render_error_str,
)


class TestParseSearch:
    def test_empty(self) -> None:
        text, flags = _parse_search("")
        assert text == ""
        assert flags == set()

    def test_plain_text(self) -> None:
        text, flags = _parse_search("foo bar")
        assert text == "foo bar"
        assert flags == set()

    def test_flags_only(self) -> None:
        text, flags = _parse_search("!running !failed")
        assert text == ""
        assert flags == {"running", "failed"}

    def test_mixed(self) -> None:
        text, flags = _parse_search("auth !running !timed_out")
        assert text == "auth"
        assert flags == {"running", "timed_out"}

    def test_bare_exclamation(self) -> None:
        text, flags = _parse_search("foo !")
        assert text == "foo"
        assert flags == set()

    def test_whitespace_normalization(self) -> None:
        text, flags = _parse_search("  foo   bar  ")
        assert text == "foo bar"
        assert flags == set()

    def test_case_lowered(self) -> None:
        text, flags = _parse_search("Auth !RUNNING")
        assert text == "auth"
        assert "running" in flags

    def test_flag_single_char(self) -> None:
        _text, flags = _parse_search("!a")
        assert flags == {"a"}

    def test_flag_empty_ignored(self) -> None:
        text, flags = _parse_search("!")
        assert text == ""
        assert flags == set()

    def test_multiple_exclamations(self) -> None:
        text, flags = _parse_search("foo !bar !baz qux")
        assert text == "foo qux"
        assert flags == {"bar", "baz"}

    def test_only_flags(self) -> None:
        text, flags = _parse_search("!a !b !c")
        assert text == ""
        assert flags == {"a", "b", "c"}

    def test_none_input(self) -> None:
        text, flags = _parse_search(None)  # type: ignore[arg-type]
        assert text == ""
        assert flags == set()


class TestRenderErrorStr:
    def test_contains_error_text(self) -> None:
        result = _render_error_str("disk full")
        assert "disk full" in result

    def test_contains_red_markup(self) -> None:
        result = _render_error_str("oops")
        assert "[red]" in result

    def test_contains_hint(self) -> None:
        result = _render_error_str("oops")
        assert "[dim]" in result

    def test_empty_error(self) -> None:
        result = _render_error_str("")
        assert isinstance(result, str)
        assert len(result) > 0


class TestListScreenRenderEmpty:
    def test_no_items_no_filters(self) -> None:
        screen = MagicMock(spec=ListScreen)
        screen._empty_key = "PROJECTS_EMPTY"
        result = ListScreen._render_empty(screen, text="", flags=set(), total=0)
        assert result != ""

    def test_no_items_with_search(self) -> None:
        screen = MagicMock(spec=ListScreen)
        screen._empty_filtered_key = "EMPTY_FILTERED_PROJECTS"
        result = ListScreen._render_empty(screen, text="foo", flags=set(), total=0)
        assert "foo" in result

    def test_no_items_with_flags(self) -> None:
        screen = MagicMock(spec=ListScreen)
        screen._empty_filtered_key = "EMPTY_FILTERED_PROJECTS"
        result = ListScreen._render_empty(screen, text="", flags={"running"}, total=0)
        assert "running" in result

    def test_items_but_no_match(self) -> None:
        screen = MagicMock(spec=ListScreen)
        screen._empty_filtered_key = "EMPTY_FILTERED_PROJECTS"
        result = ListScreen._render_empty(screen, text="xyz", flags=set(), total=5)
        assert "xyz" in result

    def test_no_items_no_text_no_flags_shows_no_matches(self) -> None:
        screen = MagicMock(spec=ListScreen)
        screen._empty_filtered_key = "EMPTY_FILTERED_PROJECTS"
        result = ListScreen._render_empty(screen, text="", flags=set(), total=5)
        assert "[dim]" in result

    def test_with_text_and_flags(self) -> None:
        screen = MagicMock(spec=ListScreen)
        screen._empty_filtered_key = "EMPTY_FILTERED_PROJECTS"
        result = ListScreen._render_empty(screen, text="q", flags={"running"}, total=3)
        assert "q" in result
        assert "running" in result


class TestListScreenRenderError:
    def test_delegates_to_render_error_str(self) -> None:
        result = ListScreen._render_error("broken")
        assert "broken" in result
        assert "[red]" in result
