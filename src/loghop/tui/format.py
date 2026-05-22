"""Shared formatting helpers for the TUI.

Centralizes timestamp parsing, relative-time rendering, temporal bucketing,
and text truncation so that home / project / preview render the same way.
"""

from datetime import UTC, datetime, timedelta

from loghop.tui import strings
from loghop.tui.widgets import glyph


def parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def relative_time(value: str) -> str:
    parsed = parse_timestamp(value)
    if parsed is None:
        return "—" if not value else value[:10]
    delta = datetime.now(UTC) - parsed.astimezone(UTC)
    seconds = int(delta.total_seconds())
    if seconds < 60:  # noqa: PLR2004
        return strings.tr("REL_NOW")
    minutes = seconds // 60
    if minutes < 60:  # noqa: PLR2004
        return strings.tr("REL_MIN_AGO", count=minutes)
    hours = minutes // 60
    if hours < 24:  # noqa: PLR2004
        return strings.tr("REL_HOUR_AGO", count=hours)
    days = hours // 24
    if days < 7:  # noqa: PLR2004
        return strings.tr("REL_DAY_AGO", count=days)
    return parsed.astimezone(UTC).strftime("%Y-%m-%d")


def time_bucket_key(value: str) -> str:
    """Classify a timestamp into a coarse bucket. Returns an i18n key or ''."""
    parsed = parse_timestamp(value)
    if parsed is None:
        return "BUCKET_UNKNOWN"
    now = datetime.now(UTC)
    delta = now - parsed.astimezone(UTC)
    if delta < timedelta(days=1):
        return "BUCKET_TODAY"
    if delta < timedelta(days=2):
        return "BUCKET_YESTERDAY"
    if delta < timedelta(days=7):
        return "BUCKET_THIS_WEEK"
    if delta < timedelta(days=30):
        return "BUCKET_THIS_MONTH"
    return "BUCKET_OLDER"


def truncate(text: str, *, max_chars: int) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    suffix = glyph.ELLIPSIS
    if max_chars <= len(suffix):
        return suffix[:max_chars]
    return text[: max_chars - len(suffix)].rstrip() + suffix


def format_duration(start: str, end: str) -> str:
    """Format the duration between two ISO timestamps as a human-readable string."""
    start_dt = parse_timestamp(start)
    if start_dt is None:
        return "\u2014"
    end_dt = parse_timestamp(end)
    if end_dt is None:
        return strings.tr("TIME_RUNNING")
    if start == end:
        return "\u2014"
    seconds = max(0, int((end_dt - start_dt).total_seconds()))
    if seconds < 60:  # noqa: PLR2004
        return f"{seconds}s"
    minutes, _ = divmod(seconds, 60)
    if minutes < 60:  # noqa: PLR2004
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"
