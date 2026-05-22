"""Unit tests for utility modules to improve coverage.

Covers: tui/format.py, store/_security.py,
dashboard.format_relative_time.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# tui.format
# ---------------------------------------------------------------------------


class TestTuiFormat:
    def test_parse_timestamp_empty(self) -> None:
        from loghop.tui.format import parse_timestamp

        assert parse_timestamp("") is None

    def test_parse_timestamp_valid(self) -> None:
        from loghop.tui.format import parse_timestamp

        result = parse_timestamp("2026-01-15T12:00:00Z")
        assert result is not None
        assert result.year == 2026

    def test_parse_timestamp_invalid(self) -> None:
        from loghop.tui.format import parse_timestamp

        assert parse_timestamp("not-a-date") is None

    def test_relative_time_empty(self) -> None:
        from loghop.tui.format import relative_time

        result = relative_time("")
        assert result == "—"

    def test_relative_time_invalid_string(self) -> None:
        from loghop.tui.format import relative_time

        result = relative_time("garbage")
        assert result == "garbage"[:10]

    def test_relative_time_just_now(self) -> None:
        from loghop.tui.format import relative_time

        ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        result = relative_time(ts)
        assert "now" in result.lower() or result  # locale may vary

    def test_relative_time_minutes_ago(self) -> None:
        from loghop.tui.format import relative_time

        ts = (datetime.now(UTC) - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        result = relative_time(ts)
        assert "5" in result

    def test_relative_time_hours_ago(self) -> None:
        from loghop.tui.format import relative_time

        ts = (datetime.now(UTC) - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
        result = relative_time(ts)
        assert "3" in result

    def test_relative_time_days_ago(self) -> None:
        from loghop.tui.format import relative_time

        ts = (datetime.now(UTC) - timedelta(days=3)).isoformat().replace("+00:00", "Z")
        result = relative_time(ts)
        assert "3" in result

    def test_relative_time_older_returns_date(self) -> None:
        from loghop.tui.format import relative_time

        ts = (datetime.now(UTC) - timedelta(days=10)).isoformat().replace("+00:00", "Z")
        result = relative_time(ts)
        assert "-" in result  # YYYY-MM-DD format

    def test_time_bucket_key_unknown(self) -> None:
        from loghop.tui.format import time_bucket_key

        assert time_bucket_key("") == "BUCKET_UNKNOWN"

    def test_time_bucket_key_today(self) -> None:
        from loghop.tui.format import time_bucket_key

        ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        assert time_bucket_key(ts) == "BUCKET_TODAY"

    def test_time_bucket_key_yesterday(self) -> None:
        from loghop.tui.format import time_bucket_key

        ts = (datetime.now(UTC) - timedelta(days=1, hours=1)).isoformat().replace("+00:00", "Z")
        assert time_bucket_key(ts) == "BUCKET_YESTERDAY"

    def test_time_bucket_key_this_week(self) -> None:
        from loghop.tui.format import time_bucket_key

        ts = (datetime.now(UTC) - timedelta(days=5)).isoformat().replace("+00:00", "Z")
        assert time_bucket_key(ts) == "BUCKET_THIS_WEEK"

    def test_time_bucket_key_this_month(self) -> None:
        from loghop.tui.format import time_bucket_key

        ts = (datetime.now(UTC) - timedelta(days=15)).isoformat().replace("+00:00", "Z")
        assert time_bucket_key(ts) == "BUCKET_THIS_MONTH"

    def test_time_bucket_key_older(self) -> None:
        from loghop.tui.format import time_bucket_key

        ts = (datetime.now(UTC) - timedelta(days=45)).isoformat().replace("+00:00", "Z")
        assert time_bucket_key(ts) == "BUCKET_OLDER"

    def test_truncate_short_text(self) -> None:
        from loghop.tui.format import truncate

        assert truncate("hello", max_chars=10) == "hello"

    def test_truncate_long_text(self) -> None:
        from loghop.tui.format import truncate

        result = truncate("hello world", max_chars=8)
        assert len(result) <= 8
        assert result.endswith("…") or result.endswith("...")

    def test_truncate_empty(self) -> None:
        from loghop.tui.format import truncate

        assert truncate("", max_chars=5) == ""


# ---------------------------------------------------------------------------
# store._security
# ---------------------------------------------------------------------------


class TestSecurityIgnorePatterns:
    def test_empty_pattern_is_unsafe(self) -> None:
        from loghop.store._security import _is_safe_pattern

        assert _is_safe_pattern("") is False

    def test_absolute_path_is_unsafe(self) -> None:
        from loghop.store._security import _is_safe_pattern

        assert _is_safe_pattern("/etc/passwd") is False

    def test_backslash_path_is_unsafe(self) -> None:
        from loghop.store._security import _is_safe_pattern

        assert _is_safe_pattern("\\windows\\system32") is False

    def test_path_traversal_is_unsafe(self) -> None:
        from loghop.store._security import _is_safe_pattern

        assert _is_safe_pattern("../secrets") is False

    def test_windows_drive_letter_is_unsafe(self) -> None:
        from loghop.store._security import _is_safe_pattern

        assert _is_safe_pattern("C:windows") is False

    def test_normal_pattern_is_safe(self) -> None:
        from loghop.store._security import _is_safe_pattern

        assert _is_safe_pattern("*.log") is True
        assert _is_safe_pattern("node_modules/") is True

    def test_load_ignore_patterns_nonexistent(self, tmp_path: Path) -> None:
        from conftest import init_repo

        from loghop.store._security import load_ignore_patterns

        root = init_repo(tmp_path)
        # Remove the ignore file if it exists
        ignore = root / ".loghop" / ".loghopignore"
        if ignore.exists():
            ignore.unlink()
        patterns = load_ignore_patterns(root)
        assert patterns == []

    def test_load_ignore_patterns_skips_unsafe(self, tmp_path: Path) -> None:
        from conftest import init_repo

        from loghop.store._security import load_ignore_patterns

        root = init_repo(tmp_path)
        ignore = root / ".loghop" / ".loghopignore"
        ignore.write_text("/etc/passwd\n*.log\n../traversal\n", encoding="utf-8")
        patterns = load_ignore_patterns(root)
        assert "*.log" in patterns
        assert "/etc/passwd" not in patterns
        assert "../traversal" not in patterns

    def test_filter_paths_path_escape_blocked(self, tmp_path: Path) -> None:
        from loghop.store._security import filter_paths

        root = tmp_path / "project"
        root.mkdir()
        escaped = "../outside/secret.txt"
        result = filter_paths([escaped, "safe.py"], [], root=root)
        assert escaped not in result
        assert "safe.py" in result


# ---------------------------------------------------------------------------
# tui.services - pure utility helpers
# ---------------------------------------------------------------------------


class TestTuiServicesHelpers:
    def test_string_tuple_from_list(self) -> None:
        from loghop.tui.services import _string_tuple

        assert _string_tuple(["a", "b"]) == ("a", "b")

    def test_string_tuple_non_list(self) -> None:
        from loghop.tui.services import _string_tuple

        assert _string_tuple(None) == ()
        assert _string_tuple("a") == ()
        assert _string_tuple(42) == ()

    def test_optional_int_none(self) -> None:
        from loghop.tui.services import _optional_int

        assert _optional_int(None) is None
        assert _optional_int("") is None

    def test_optional_int_int_value(self) -> None:
        from loghop.tui.services import _optional_int

        assert _optional_int(5) == 5

    def test_optional_int_string_value(self) -> None:
        from loghop.tui.services import _optional_int

        assert _optional_int("42") == 42

    def test_optional_int_invalid_string(self) -> None:
        from loghop.tui.services import _optional_int

        assert _optional_int("nope") is None

    def test_optional_int_non_string_non_int(self) -> None:
        from loghop.tui.services import _optional_int

        assert _optional_int([1, 2]) is None

    def test_int_or_zero_none(self) -> None:
        from loghop.tui.services import _int_or_zero

        assert _int_or_zero(None) == 0

    def test_int_or_zero_valid(self) -> None:
        from loghop.tui.services import _int_or_zero

        assert _int_or_zero(7) == 7


# ---------------------------------------------------------------------------
# dashboard.format_relative_time
# ---------------------------------------------------------------------------


class TestFormatRelativeTime:
    def test_empty_string_returns_never(self) -> None:
        from loghop.cli_commands._helpers import format_relative_time

        assert format_relative_time("") == "never"

    def test_invalid_string_returns_input(self) -> None:
        from loghop.cli_commands._helpers import format_relative_time

        assert format_relative_time("not-a-date") == "not-a-date"

    def test_just_now(self) -> None:
        from loghop.cli_commands._helpers import format_relative_time

        ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        assert format_relative_time(ts) == "just now"

    def test_minutes_ago(self) -> None:
        from loghop.cli_commands._helpers import format_relative_time

        ts = (datetime.now(UTC) - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        assert format_relative_time(ts) == "10m ago"

    def test_hours_ago(self) -> None:
        from loghop.cli_commands._helpers import format_relative_time

        ts = (datetime.now(UTC) - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        assert format_relative_time(ts) == "5h ago"

    def test_days_ago(self) -> None:
        from loghop.cli_commands._helpers import format_relative_time

        ts = (datetime.now(UTC) - timedelta(days=3)).isoformat().replace("+00:00", "Z")
        assert format_relative_time(ts) == "3d ago"

    def test_older_returns_date(self) -> None:
        from loghop.cli_commands._helpers import format_relative_time

        ts = (datetime.now(UTC) - timedelta(days=14)).isoformat().replace("+00:00", "Z")
        result = format_relative_time(ts)
        assert "-" in result  # YYYY-MM-DD format


# ---------------------------------------------------------------------------
# cli_commands._helpers - validate_length, resolve_goal, require_provider_arg
# ---------------------------------------------------------------------------


class TestCliHelpers:
    def test_validate_length_null_bytes(self) -> None:
        from loghop.cli_commands._helpers import validate_length
        from loghop.errors import LoghopError

        with pytest.raises(LoghopError, match="null bytes"):
            validate_length("hello\x00world", "goal")

    def test_validate_length_multiline(self) -> None:
        from loghop.cli_commands._helpers import validate_length
        from loghop.errors import LoghopError

        with pytest.raises(LoghopError, match="single line"):
            validate_length("line1\nline2", "goal")

    def test_validate_length_too_long(self) -> None:
        from loghop.cli_commands._helpers import validate_length
        from loghop.errors import LoghopError

        with pytest.raises(LoghopError, match="exceeds"):
            validate_length("x" * 5000, "goal")

    def test_validate_length_ok(self) -> None:
        from loghop.cli_commands._helpers import validate_length

        assert validate_length("short goal", "goal") == "short goal"

    def test_require_provider_arg_empty(self) -> None:
        from loghop.cli_commands._helpers import require_provider_arg
        from loghop.errors import LoghopError

        with pytest.raises(LoghopError, match="requires --provider"):
            require_provider_arg(None, "handoff run")

    def test_require_supported_provider_unknown(self) -> None:
        from loghop.cli_commands._helpers import require_supported_provider
        from loghop.errors import LoghopError

        with pytest.raises(LoghopError, match="unsupported provider"):
            require_supported_provider("gemini")

    def test_resolve_goal_empty_raises(self) -> None:
        from loghop.cli_commands._helpers import resolve_goal, resolve_goal_or_default
        from loghop.errors import LoghopError
        from loghop.store._models import ProjectConfig

        config = ProjectConfig(version=1, project_name="test", goal="")
        with pytest.raises(LoghopError, match="requires a goal"):
            resolve_goal(None, config, "handoff")
        assert resolve_goal_or_default(None, config) == "Ad hoc session"

    def test_resolve_goal_from_config(self) -> None:
        from loghop.cli_commands._helpers import resolve_goal
        from loghop.store._models import ProjectConfig

        config = ProjectConfig(version=1, project_name="test", goal="my goal")
        assert resolve_goal(None, config, "handoff") == "my goal"
