from __future__ import annotations

from datetime import UTC, datetime

import pytest

from loghop.cli_commands._helpers import format_relative_time
from loghop.cli_commands.dashboard import _match_project
from loghop.errors import LoghopError
from loghop.store._models import RegistryEntry


class TestFormatRelativeTime:
    def test_empty_returns_never(self) -> None:
        assert format_relative_time("") == "never"

    def test_just_now(self) -> None:
        ts = datetime.now(tz=UTC).isoformat()
        assert format_relative_time(ts) == "just now"

    def test_minutes_ago(self) -> None:
        ts = (datetime.now(tz=UTC) - __import__("datetime").timedelta(minutes=5)).isoformat()
        result = format_relative_time(ts)
        assert result == "5m ago"

    def test_hours_ago(self) -> None:
        ts = (datetime.now(tz=UTC) - __import__("datetime").timedelta(hours=3)).isoformat()
        result = format_relative_time(ts)
        assert result == "3h ago"

    def test_days_ago(self) -> None:
        ts = (datetime.now(tz=UTC) - __import__("datetime").timedelta(days=2)).isoformat()
        result = format_relative_time(ts)
        assert result == "2d ago"

    def test_weeks_ago_shows_date(self) -> None:
        ts = (datetime.now(tz=UTC) - __import__("datetime").timedelta(days=14)).isoformat()
        result = format_relative_time(ts)
        assert result.count("-") == 2

    def test_invalid_ts_returns_as_is(self) -> None:
        assert format_relative_time("not-a-date") == "not-a-date"


class TestMatchProject:
    def _entry(self, name: str, path: str) -> RegistryEntry:
        return RegistryEntry(
            name=name,
            path=path,
            registered="2025-01-01T00:00:00Z",
            last_used="2025-01-01T00:00:00Z",
        )

    def test_match_by_name(self) -> None:
        entries = [self._entry("myapp", "/home/user/myapp")]
        assert _match_project(entries, "myapp") is entries[0]

    def test_match_by_path(self) -> None:
        entries = [self._entry("myapp", "/home/user/myapp")]
        assert _match_project(entries, "/home/user/myapp") is entries[0]

    def test_no_match(self) -> None:
        entries = [self._entry("myapp", "/home/user/myapp")]
        assert _match_project(entries, "other") is None

    def test_fuzzy_match_single(self) -> None:
        entries = [self._entry("myapp-alpha", "/a"), self._entry("other", "/b")]
        result = _match_project(entries, "alpha")
        assert result is entries[0]

    def test_fuzzy_match_multiple_raises_ambiguous_target(self) -> None:
        entries = [
            self._entry("myapp-alpha", "/a"),
            self._entry("alpha-beta", "/b"),
        ]
        with pytest.raises(LoghopError, match="ambiguous target"):
            _match_project(entries, "alpha")

    def test_empty_list(self) -> None:
        assert _match_project([], "anything") is None
