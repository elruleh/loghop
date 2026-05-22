from __future__ import annotations

from loghop.tui.screens._screen_state import (
    ChromeMeta,
    format_flags,
    is_stale_generation,
    should_show_loading_spinner,
)


def test_is_stale_generation_when_generation_differs() -> None:
    assert is_stale_generation(current=3, incoming=2) is True


def test_is_stale_generation_when_generation_matches() -> None:
    assert is_stale_generation(current=3, incoming=3) is False


def test_should_show_loading_spinner_after_delay_for_current_generation() -> None:
    assert should_show_loading_spinner(current=4, incoming=4, elapsed_seconds=0.25) is True


def test_should_not_show_loading_spinner_before_delay() -> None:
    assert should_show_loading_spinner(current=4, incoming=4, elapsed_seconds=0.19) is False


def test_should_not_show_loading_spinner_for_stale_generation() -> None:
    assert should_show_loading_spinner(current=5, incoming=4, elapsed_seconds=1.0) is False


def test_format_flags_sorts_and_prefixes_flags() -> None:
    assert format_flags({"missing", "current"}) == ["!current", "!missing"]


def test_chrome_meta_tracks_filtered_query_flags_and_sort() -> None:
    meta = ChromeMeta(
        shown=2,
        total=5,
        query="repo",
        flags={"current"},
        sort_label="name",
    )

    assert meta.is_filtered is True
    assert meta.flag_labels == ["!current"]
