from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from loghop.autocapture import capture_from_transcript
from loghop.errors import AUTH_FAILURE_NEEDLES
from loghop.logging import get_logger
from loghop.store._constants import SessionStatus
from loghop.store._models import SessionMeta
from loghop.store._session import current_files_changed, finish_session

_LOGGER = get_logger()

_AUTH_FAILURE_NEEDLES = AUTH_FAILURE_NEEDLES


@dataclass(frozen=True)
class SessionContext:
    """Context for session operations - groups related identifiers."""

    root: Path
    session_id: str
    provider: str
    launch_ts: datetime

    @classmethod
    def from_args(
        cls,
        root: Path,
        session_id: str,
        provider: str,
        launch_ts: datetime,
    ) -> "SessionContext":
        """Create SessionContext from individual arguments."""
        return cls(root=root, session_id=session_id, provider=provider, launch_ts=launch_ts)


@dataclass(frozen=True)
class TranscriptOptions:
    """Options for transcript capture."""

    source_path: Path | None = None
    transcript_cwd: Path | None = None
    match_texts: list[str] | None = None
    require_match: bool = False


@dataclass(frozen=True)
class FinalizeOptions:
    """Options for finalizing a session."""

    status: str
    returncode: int | None
    capture: dict[str, Any] | None = None
    files_changed: list[str] | None = None
    component: str = "session_lifecycle"


def finalize_session(
    ctx: SessionContext,
    opts: FinalizeOptions,
) -> SessionMeta:
    """Finalize a session with consistent changed-file capture and logging."""
    finished = False
    try:
        changed = (
            opts.files_changed
            if opts.files_changed is not None
            else current_files_changed(ctx.root)
        )
        res = finish_session(
            ctx.root,
            ctx.session_id,
            status=opts.status,
            returncode=opts.returncode,
            files_changed=changed,
            **(opts.capture or {}),
        )
        finished = True
    except Exception as exc:
        _LOGGER.exception(
            "failed to finalize session",
            extra={
                "component": opts.component,
                "root": str(ctx.root),
                "session_id": ctx.session_id,
                "status": opts.status,
                "returncode": opts.returncode,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        raise
    except BaseException as exc:
        if not finished:
            _LOGGER.warning(
                "finalization interrupted by %s, attempting basic finish",
                type(exc).__name__,
                extra={
                    "component": opts.component,
                    "root": str(ctx.root),
                    "session_id": ctx.session_id,
                },
            )
            with suppress(Exception):
                finish_session(
                    ctx.root,
                    ctx.session_id,
                    status=opts.status,
                    returncode=opts.returncode,
                    files_changed=[],
                    **(opts.capture or {}),
                )
        raise
    else:
        return res


@dataclass(frozen=True)
class CaptureOptions:
    """Options for capture and finalize combined operations."""

    status: str
    returncode: int | None
    opts: TranscriptOptions | None = None
    output: str = ""
    component: str = "session_lifecycle"


def capture_and_finalize_session(
    ctx: SessionContext,
    cap_opts: CaptureOptions,
) -> tuple[SessionMeta, dict[str, Any]]:
    """Capture provider transcript and finalize the matching loghop session."""

    transcript_opts = cap_opts.opts or TranscriptOptions()
    ctx_transcript = SessionContext(
        root=ctx.root,
        session_id=ctx.session_id,
        provider=ctx.provider,
        launch_ts=ctx.launch_ts,
    )
    try:
        capture = capture_from_transcript(ctx_transcript, transcript_opts)
    except Exception as exc:
        _LOGGER.exception(
            "failed to capture provider transcript",
            extra={
                "component": cap_opts.component,
                "root": str(ctx.root),
                "session_id": ctx.session_id,
                "provider": ctx.provider,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        capture = {}
    except BaseException as exc:  # noqa: BLE001
        _LOGGER.warning(
            "capture interrupted by %s",
            type(exc).__name__,
            extra={
                "component": cap_opts.component,
                "root": str(ctx.root),
                "session_id": ctx.session_id,
            },
        )
        capture = {}
    status, returncode = _effective_status_and_returncode(
        provider=ctx.provider,
        status=cap_opts.status,
        returncode=cap_opts.returncode,
        capture=dict(capture),
        output=cap_opts.output,
    )
    meta = finalize_session(
        ctx,
        FinalizeOptions(
            status=status,
            returncode=returncode,
            capture={**dict(capture), **({"output": cap_opts.output} if cap_opts.output else {})},
            component=cap_opts.component,
        ),
    )
    return meta, dict(capture)


def _effective_status_and_returncode(
    *,
    provider: str,
    status: str,
    returncode: int | None,
    capture: dict[str, Any],
    output: str,
) -> tuple[str, int | None]:
    if str(status) != str(SessionStatus.SUCCEEDED):
        return status, returncode
    if not _looks_like_provider_auth_failure(provider, capture, output):
        return status, returncode
    return str(SessionStatus.FAILED), returncode if returncode not in (None, 0) else 1


def _looks_like_provider_auth_failure(
    provider: str,
    capture: dict[str, Any],
    output: str,
) -> bool:
    text = "\n".join(
        part
        for part in (
            provider,
            output,
            str(capture.get("summary") or ""),
        )
        if part
    ).lower()
    return any(needle in text for needle in _AUTH_FAILURE_NEEDLES)
