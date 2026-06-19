from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from loghop.logging import get_logger
from loghop.session_lifecycle import (
    CaptureOptions,
    SessionContext,
    TranscriptOptions,
    capture_and_finalize_session,
)
from loghop.store import project_paths
from loghop.store._constants import SessionStatus
from loghop.store._models import SessionMeta
from loghop.store._session import list_sessions

_LOGGER = get_logger()
_RECONCILE_CLOCK_SKEW_TOLERANCE = timedelta(seconds=10)


def find_running_sessions(root: Path, *, older_than: timedelta | None = None) -> list[SessionMeta]:
    """Return running-state sessions, optionally filtered to those older than N."""
    paths = project_paths(root)
    out: list[SessionMeta] = []
    if not paths.sessions.exists():
        return out
    cutoff = (datetime.now(tz=UTC) - older_than) if older_than else None
    for session in list_sessions(paths):
        if (session.status or "") != SessionStatus.RUNNING:
            continue
        if cutoff is None:
            out.append(session)
            continue
        ts = session.ts_start or ""
        if not ts:
            out.append(session)
            continue
        try:
            started = datetime.fromisoformat(ts)
        except ValueError:
            out.append(session)
            continue
        if started <= cutoff:
            out.append(session)
    return out


def reconcile_session(root: Path, session: SessionMeta) -> dict[str, Any]:
    """Try to capture a transcript for a stranded running session and finalize it."""
    session_id = str(session.id or "")
    provider = str(session.provider or "")
    if not session_id or not provider:
        return {"id": session_id, "status": "skipped"}
    ts = str(session.ts_start or "")
    # Conservative fallback: a missing/unparseable ts_start used to default
    # to "1 week ago", which made it easy for reconcile to grab an old,
    # unrelated transcript. Limit to the last hour — wide enough to cover
    # clock skew, narrow enough to avoid cross-session bleeding.
    #
    # We also subtract a small skew tolerance from parsed ts_start. Session
    # timestamps come from `utc_now()` (second-rounded and process-monotonic),
    # while transcript mtimes/timestamps come from the real wall clock. Under
    # fast test runs or slight clock drift, `ts_start` can end up a few seconds
    # ahead of the transcript file, causing explicit `sessions reconcile` to
    # intermittently miss a transcript that was actually created by the same run.
    try:
        parsed_launch_ts = (
            datetime.fromisoformat(ts) if ts else datetime.now(tz=UTC) - timedelta(hours=1)
        )
    except ValueError:
        parsed_launch_ts = datetime.now(tz=UTC) - timedelta(hours=1)
    launch_ts = parsed_launch_ts - _RECONCILE_CLOCK_SKEW_TOLERANCE

    status = SessionStatus.INTERRUPTED
    ctx = SessionContext.from_args(root, session_id, provider, launch_ts)
    _, capture = capture_and_finalize_session(
        ctx,
        CaptureOptions(
            status=status,
            returncode=130,
            opts=TranscriptOptions(
                match_texts=_reconcile_hints(session),
                require_match=True,
            ),
            component="reconcile",
        ),
    )
    return {
        "id": session_id,
        "provider": provider,
        "status": status,
        "turns_captured": int(capture.get("turns_captured", 0) or 0),
        "transcript_path": capture.get("transcript_path", ""),
    }


def _reconcile_hints(session: SessionMeta) -> list[str]:
    return [
        value
        for value in (
            str(session.goal or ""),
            str(session.handoff_id or ""),
        )
        if value.strip()
    ]


def reconcile_running_sessions(
    root: Path, *, older_than: timedelta | None = None
) -> list[dict[str, Any]]:
    """Reconcile every running session in `root`, returning per-session reports.

    Per-session failures are isolated: one stranded session that can't be
    reconciled (e.g. corrupt frontmatter) must not block the rest.
    """
    reports: list[dict[str, Any]] = []
    for session in find_running_sessions(root, older_than=older_than):
        try:
            reports.append(reconcile_session(root, session))
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "reconcile failed for session",
                exc_info=True,
                extra={
                    "component": "reconcile",
                    "session_id": str(session.id or ""),
                    "provider": str(session.provider or ""),
                    "error": str(exc),
                },
            )
            reports.append(
                {
                    "id": str(session.id or ""),
                    "provider": str(session.provider or ""),
                    "status": "reconcile_error",
                    "error": str(exc),
                }
            )
    return reports


def auto_reconcile_silent(root: Path | None) -> None:
    """Best-effort reconcile of stale running sessions on CLI startup.

    Logs at WARN when individual sessions fail (so operators see the
    reason in the log file) but never raises — a broken stranded session
    must not break the next CLI invocation.
    """
    if root is None:
        return
    try:
        reports = reconcile_running_sessions(root, older_than=timedelta(hours=1))
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning(
            "auto-reconcile aborted",
            exc_info=True,
            extra={"component": "reconcile", "root": str(root), "error": str(exc)},
        )
        return
    failed = [r for r in reports if r.get("status") == "reconcile_error"]
    if failed:
        _LOGGER.warning(
            "auto-reconcile finished with %d failed session(s)",
            len(failed),
            extra={"component": "reconcile", "failed_ids": [r.get("id") for r in failed]},
        )
