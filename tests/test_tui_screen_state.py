"""Unit tests for the TUI's pure helpers (no Pilot needed).

The TUI screens themselves are covered by ``test_home_screen``,
``test_project_screen`` and ``test_tui_app`` (all marked ``slow``). This
file covers the small, testable helpers and the search-query parser that
the list screens use, so we can keep at least the contract-level
correctness covered when the TUI tests are skipped.
"""

from __future__ import annotations

import pytest

from loghop.tui.screens._list_shared import _parse_search, _render_error_str
from loghop.tui.screens._screen_state import (
    ChromeMeta,
    format_flags,
    is_stale_generation,
    should_show_loading_spinner,
)

# --- _parse_search --------------------------------------------------------------


def test_parse_search_extracts_text_and_flags() -> None:
    text, flags = _parse_search("auth !failed !claude")
    assert text == "auth"
    assert flags == {"failed", "claude"}


def test_parse_search_handles_empty() -> None:
    text, flags = _parse_search("")
    assert text == ""
    assert flags == set()


def test_parse_search_handles_only_flags() -> None:
    text, flags = _parse_search("!failed !running")
    assert text == ""
    assert flags == {"failed", "running"}


def test_parse_search_drops_bare_bang() -> None:
    """A lone `!` is not a flag, just a stray punctuation mark."""
    text, flags = _parse_search("! what")
    assert "what" in text
    assert "!" not in flags


def test_parse_search_is_case_insensitive() -> None:
    text, flags = _parse_search("FOO !FAILED")
    assert text == "foo"
    assert flags == {"failed"}


# --- _render_error_str ---------------------------------------------------------


def test_render_error_str_includes_message() -> None:
    rendered = _render_error_str("connection refused")
    assert "connection refused" in rendered
    assert "[" in rendered  # contains Rich markup


# --- ChromeMeta / format_flags -------------------------------------------------


def test_format_flags_sorted_with_prefix() -> None:
    assert format_flags({"b", "a"}) == ["!a", "!b"]


def test_format_flags_empty() -> None:
    assert format_flags(set()) == []


def test_chrome_meta_is_filtered_with_query() -> None:
    meta = ChromeMeta(shown=1, total=10, query="auth")
    assert meta.is_filtered is True


def test_chrome_meta_is_filtered_with_flags() -> None:
    meta = ChromeMeta(shown=1, total=10, flags={"failed"})
    assert meta.is_filtered is True


def test_chrome_meta_is_not_filtered_when_empty() -> None:
    meta = ChromeMeta(shown=10, total=10)
    assert meta.is_filtered is False


def test_chrome_meta_flag_labels() -> None:
    meta = ChromeMeta(shown=0, total=0, flags={"claude", "running"})
    assert meta.flag_labels == ["!claude", "!running"]


# --- is_stale_generation / should_show_loading_spinner -------------------------


@pytest.mark.parametrize(
    "current,incoming,expected",
    [
        (0, 0, False),
        (0, 1, True),
        (5, 5, False),
        (5, 6, True),
    ],
)
def test_is_stale_generation(current: int, incoming: int, expected: bool) -> None:
    assert is_stale_generation(current=current, incoming=incoming) == expected


def test_should_show_loading_spinner_respects_stale() -> None:
    """A stale generation hides the spinner (a new fetch is in progress)."""
    assert should_show_loading_spinner(current=0, incoming=1, elapsed_seconds=10.0) is False


def test_should_show_loading_spinner_respects_delay() -> None:
    assert should_show_loading_spinner(current=1, incoming=1, elapsed_seconds=0.0) is False
    assert should_show_loading_spinner(current=1, incoming=1, elapsed_seconds=0.5) is True
