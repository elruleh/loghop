"""Internal subcommand: receives stdin JSON from a Claude Code hook.

Always exits 0 to avoid breaking the host (Claude). Errors are logged.
"""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from loghop.logging import get_logger
from loghop.redact import redact_text
from loghop.session_lifecycle import (
    CaptureOptions,
    SessionContext,
    TranscriptOptions,
    capture_and_finalize_session,
)
from loghop.store import find_project_root, project_paths
from loghop.store._constants import SessionStatus
from loghop.store._session import (
    create_session,
    find_session_by_claude_id,
)
from loghop.terminal import Terminal

_LOGGER = get_logger()

_VALID_EVENTS = {"claude-session-start", "claude-session-end"}


class _HookPayloadError(ValueError):
    """The hook payload from the host (Claude) is malformed or missing fields."""


def handle_hook(args: argparse.Namespace, term: Terminal) -> int:
    event = str(args.event or "").strip()
    if event not in _VALID_EVENTS:
        _LOGGER.warning(
            "hook called with unknown event",
            extra={"component": "hook", "event": event},
        )
        return 0
    payload = _read_stdin_json()
    try:
        cwd = _validate_cwd(payload)
    except _HookPayloadError as exc:
        _LOGGER.warning(
            "hook payload schema error",
            extra={"component": "hook", "event": event, "error": str(exc)},
        )
        return 0
    root = find_project_root(cwd)
    if root is None:
        return 0  # silently ignore: not a loghop project

    log_extra = {"component": "hook", "event": event, "root": str(root)}
    try:
        if event == "claude-session-start":
            return _on_session_start(root, payload, term)
        # event == "claude-session-end" (validated above)
        return _on_session_end(root, payload, term)
    except _HookPayloadError as exc:
        _LOGGER.warning("hook payload schema error", extra={**log_extra, "error": str(exc)})
    except (OSError, ValueError) as exc:
        # Filesystem / store-level failures are recoverable on next hook fire;
        # log and exit 0 so we don't break the Claude host.
        _LOGGER.error(
            "hook handler failed (recoverable)",
            exc_info=True,
            extra={**log_extra, "error": str(exc), "error_type": type(exc).__name__},
        )
    except Exception as exc:
        # Truly unexpected: log with full context. We still exit 0 to keep
        # Claude alive, but the stack should be preserved for debugging.
        _LOGGER.exception(
            "hook handler crashed",
            extra={**log_extra, "error": str(exc), "error_type": type(exc).__name__},
        )
        # Mirror legacy stderr line so existing operators still see it.
        print(f"loghop hook {event} error: {redact_text(str(exc))}", file=sys.stderr)  # noqa: T201
    return 0


def _validate_cwd(payload: dict[str, object]) -> Path:
    raw = payload.get("cwd")
    if raw is None or raw == "":
        return Path.cwd()
    if not isinstance(raw, str):
        raise _HookPayloadError(f"cwd must be a string, got {type(raw).__name__}")
    cwd = Path(raw).resolve()
    if not cwd.is_dir():
        raise _HookPayloadError(f"cwd is not a directory: {raw}")
    return cwd


def _require_session_id(payload: dict[str, object]) -> str:
    raw = payload.get("session_id")
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise _HookPayloadError(f"session_id must be a string, got {type(raw).__name__}")
    return raw


def _optional_string(payload: dict[str, object], key: str) -> str:
    raw = payload.get(key)
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise _HookPayloadError(f"{key} must be a string, got {type(raw).__name__}")
    return raw


def _on_session_start(root: Path, payload: dict[str, object], _term: Terminal) -> int:
    claude_session_id = _require_session_id(payload)
    transcript_path = _optional_string(payload, "transcript_path")
    if not claude_session_id:
        return 0
    paths = project_paths(root)
    # If we already have a session for this Claude session_id, do nothing.
    if find_session_by_claude_id(paths, claude_session_id) is not None:
        return 0
    session = create_session(
        root,
        provider="claude",
        goal="(claude session)",
        handoff_id="",
    )
    session_id = session.id
    md = paths.sessions / f"{session_id}.md"
    _patch_frontmatter(
        md,
        {
            "claude_session_id": claude_session_id,
            "transcript_path": transcript_path,
        },
    )
    return 0


def _on_session_end(root: Path, payload: dict[str, object], _term: Terminal) -> int:
    claude_session_id = _require_session_id(payload)
    transcript_path = _optional_string(payload, "transcript_path")
    if not claude_session_id:
        return 0
    paths = project_paths(root)
    matched = find_session_by_claude_id(paths, claude_session_id)
    if not matched:
        # No SessionStart fired (e.g. hooks installed mid-session). Create one
        # now so the transcript still gets captured.
        matched = create_session(
            root,
            provider="claude",
            goal="(claude session, late capture)",
            handoff_id="",
        )
        md = paths.sessions / f"{matched.id}.md"
        _patch_frontmatter(
            md,
            {
                "claude_session_id": claude_session_id,
                "transcript_path": transcript_path,
            },
        )

    session_id = str(matched.id or "")
    if not session_id:
        return 0

    # Use the explicit transcript_path from the hook if provided. Falling back
    # to the slug+mtime search keeps things working if the hook payload is
    # missing the path.
    launch_ts = _ts_or_default(matched.ts_start)
    ctx = SessionContext(root=root, session_id=session_id, provider="claude", launch_ts=launch_ts)
    initial_status, initial_returncode = _initial_hook_status(payload)
    meta, capture = capture_and_finalize_session(
        ctx,
        CaptureOptions(
            status=initial_status,
            returncode=initial_returncode,
            opts=TranscriptOptions(
                source_path=Path(transcript_path) if transcript_path else None,
            ),
            component="hook",
        ),
    )
    effective_status = _derive_hook_session_status(
        dict(capture),
        fallback=str(meta.status),
        initial_status=initial_status,
    )
    if effective_status != str(meta.status):
        _patch_session_status(root, session_id, effective_status)
    return 0


def _initial_hook_status(
    payload: dict[str, object],
) -> tuple[str, int]:
    """Derive initial session status and returncode from the hook payload.

    Claude Code hooks don't provide an explicit exit code in the payload, but
    they do include a ``stop_reason`` field that indicates how the session ended.
    We use it to pick a more accurate initial status before the transcript is
    captured, which is then further refined by ``_derive_hook_session_status``.
    """
    stop_reason = str(payload.get("stop_reason") or "").strip().lower()
    # Common stop_reason values from Claude Code:
    #   "end_turn"   — normal completion
    #   "tool_use"   — ended after a tool call (also normal)
    #   "max_tokens" — hit token limit, likely incomplete
    #   "stop"       — externally stopped
    #   "error"      — error during generation
    if stop_reason == "error":
        return str(SessionStatus.FAILED), 1
    if stop_reason in ("max_tokens", "stop"):
        return str(SessionStatus.INTERRUPTED), 130
    return str(SessionStatus.SUCCEEDED), 0


def _derive_hook_session_status(
    capture: dict[str, object],
    *,
    fallback: str,
    initial_status: str = "",
) -> str:
    """Derive a safer status for Claude hook-finalized sessions.

    Rules (applied in order):
    1. 0 captured turns → ``interrupted`` (nothing meaningful happened).
    2. Summary contains an auth-failure needle → ``failed`` (even if the
       transcript had turns, the session was unusable).
    3. ``initial_status`` was ``failed`` or ``interrupted`` and the capture
       didn't provide a meaningful summary → keep the initial status.
    4. Otherwise → ``fallback`` (the status assigned by
       ``capture_and_finalize_session`` which applies its own heuristics).
    """
    from loghop.errors import AUTH_FAILURE_NEEDLES

    turns_raw = capture.get("turns_captured")
    turns = turns_raw if isinstance(turns_raw, int) else 0
    if turns == 0:
        return str(SessionStatus.INTERRUPTED)

    summary = str(capture.get("summary") or "").lower()
    if any(needle in summary for needle in AUTH_FAILURE_NEEDLES):
        return str(SessionStatus.FAILED)

    if (
        initial_status in (str(SessionStatus.FAILED), str(SessionStatus.INTERRUPTED))
        and not summary
    ):
        # If the initial status was bad and capture didn't produce a summary,
        # the session likely didn't accomplish anything useful.
        return initial_status

    return fallback


def _patch_session_status(root: Path, session_id: str, status: str) -> None:
    """Patch status after hook finalization and refresh the session index."""
    from loghop.store._frontmatter import (
        meta_to_dataclass,
        parse_frontmatter_text,
        rewrite_frontmatter,
    )
    from loghop.store._index import update_index
    from loghop.store._models import SessionMeta

    paths = project_paths(root)
    md_path = paths.sessions / f"{session_id}.md"
    rewrite_frontmatter(md_path, {"status": status})
    meta, _ = parse_frontmatter_text(md_path)
    meta["path"] = str(md_path.relative_to(root))
    session = SessionMeta(**meta_to_dataclass(meta, SessionMeta))
    update_index(paths, session=session)


_MAX_STDIN_BYTES = 1 << 20  # 1 MiB


def _read_stdin_json() -> dict[str, object]:
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read(_MAX_STDIN_BYTES)
    except OSError:
        return {}
    raw = raw.strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _ts_or_default(value: object) -> datetime:
    # Conservative fallback (was 7 days). Limits cross-session contamination
    # when a transcript timestamp is missing or unparseable.
    text = str(value or "")
    if not text:
        return datetime.now(tz=UTC) - timedelta(hours=1)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(tz=UTC) - timedelta(hours=1)


def _patch_frontmatter(md_path: Path, updates: dict[str, str | None]) -> None:
    """Splice extra keys into the frontmatter of a session markdown file."""
    from loghop.store._frontmatter import parse_frontmatter_text, rewrite_frontmatter
    from loghop.store._index import SESSION_RE, update_index
    from loghop.store._models import SessionMeta

    if not md_path.exists():
        return
    try:
        rewrite_frontmatter(md_path, updates)
    except Exception:
        _LOGGER.exception("failed to patch frontmatter in %s", md_path)
        return

    # Re-read the patched frontmatter and refresh the session index so
    # list_sessions() / find_session_by_claude_id() see the new fields.
    try:
        stem = md_path.stem
        if not SESSION_RE.match(stem):
            return
        meta, _ = parse_frontmatter_text(md_path)
        if not meta or "id" not in meta:
            return
        from loghop.store._constants import project_paths

        root = md_path
        for _ in range(4):  # walk up to find project root (.loghop/)
            root = root.parent
            if (root / ".loghop").is_dir():
                break
        else:
            return
        paths = project_paths(root)
        meta["path"] = str(md_path.relative_to(root))
        from loghop.store._frontmatter import meta_to_dataclass

        kwargs = meta_to_dataclass(meta, SessionMeta)
        session = SessionMeta(**kwargs)
        update_index(paths, session=session)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("could not refresh session index after patch", exc_info=True)
