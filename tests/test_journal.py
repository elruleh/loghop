from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from loghop.cli_commands._helpers import parse_since
from loghop.cli_commands.journal import _after
from loghop.errors import LoghopError


class TestParseSince:
    def test_days(self) -> None:
        result = parse_since("7d")
        assert result is not None
        expected = datetime.now(tz=UTC) - timedelta(days=7)
        assert abs((result - expected).total_seconds()) < 5

    def test_hours(self) -> None:
        result = parse_since("12h")
        assert result is not None
        expected = datetime.now(tz=UTC) - timedelta(hours=12)
        assert abs((result - expected).total_seconds()) < 5

    def test_weeks(self) -> None:
        result = parse_since("2w")
        assert result is not None
        expected = datetime.now(tz=UTC) - timedelta(weeks=2)
        assert abs((result - expected).total_seconds()) < 5

    def test_empty_returns_none(self) -> None:
        assert parse_since("") is None

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(LoghopError, match="invalid --since"):
            parse_since("  ")

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(LoghopError, match="invalid --since"):
            parse_since("abc")

    def test_invalid_unit_raises(self) -> None:
        with pytest.raises(LoghopError, match="invalid --since"):
            parse_since("5m")

    def test_too_large_raises(self) -> None:
        with pytest.raises(LoghopError, match="too large"):
            parse_since("10001d")

    def test_zero_days(self) -> None:
        result = parse_since("0d")
        assert result is not None


class TestAfter:
    def test_recent_ts_is_after(self) -> None:
        now = datetime.now(tz=UTC)
        since = now - timedelta(days=1)
        assert _after(now.isoformat(), since) is True

    def test_old_ts_is_not_after(self) -> None:
        now = datetime.now(tz=UTC)
        since = now - timedelta(days=1)
        old = (now - timedelta(days=5)).isoformat()
        assert _after(old, since) is False

    def test_z_suffix_handled(self) -> None:
        now = datetime.now(tz=UTC)
        since = now - timedelta(hours=1)
        ts = now.isoformat().replace("+00:00", "Z")
        assert _after(ts, since) is True

    def test_invalid_ts_returns_true(self) -> None:
        since = datetime.now(tz=UTC) - timedelta(days=1)
        assert _after("not-a-date", since) is True
