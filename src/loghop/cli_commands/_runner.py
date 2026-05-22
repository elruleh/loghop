import os
import subprocess  # nosec B404
from datetime import datetime
from pathlib import Path
from typing import Any

from loghop.errors import (
    E_PROVIDER_LAUNCH_FAILED,
    E_PROVIDER_NONZERO,
    E_TIMEOUT,
    LoghopError,
)
from loghop.logging import get_logger
from loghop.providers import build_launch_command, claude_api_environment
from loghop.redact import redact_text
from loghop.session_lifecycle import (
    CaptureOptions,
    FinalizeOptions,
    SessionContext,
    TranscriptOptions,
    capture_and_finalize_session,
    finalize_session,
)
from loghop.store import update_handoff_status
from loghop.store._constants import DEFAULT_TIMEOUT, SessionStatus
from loghop.store._session import current_files_changed
from loghop.terminal import Terminal

_LOGGER = get_logger()


def _mark_interrupted(
    ctx: SessionContext,
    handoff_id: str,
    prompt: str,
) -> None:
    if handoff_id:
        update_handoff_status(ctx.root, handoff_id, status=SessionStatus.INTERRUPTED)
    capture_and_finalize_session(
        ctx,
        CaptureOptions(
            status=SessionStatus.INTERRUPTED,
            returncode=130,
            opts=TranscriptOptions(match_texts=_capture_hints(prompt)),
            component="runner",
        ),
    )


def _mark_interrupted_defensive(
    ctx: SessionContext,
    handoff_id: str,
    prompt: str,
) -> None:
    try:
        _mark_interrupted(ctx, handoff_id, prompt)
    except Exception as cleanup_exc:  # noqa: BLE001
        _LOGGER.warning(
            "failed to mark interrupted session during exception cleanup",
            exc_info=True,
            extra={
                "component": "runner",
                "session_id": ctx.session_id,
                "handoff_id": handoff_id,
                "error": str(cleanup_exc),
            },
        )


def _launch_subprocess(
    command: list[str],
    root: Path,
    *,
    provider: str,
    interactive: bool,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    env = _provider_env(provider, root, interactive=interactive)
    if interactive:
        return subprocess.run(command, cwd=root, check=False, text=True, env=env)  # nosec B603
    return subprocess.run(  # nosec B603
        command,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
        env=env,
    )


def _provider_env(
    provider: str,
    project_root: Path,
    *,
    interactive: bool = False,
) -> dict[str, str] | None:
    if provider != "claude":
        return None
    env = os.environ.copy()
    env.update(claude_api_environment(project_root))
    auth_token = env.get("ANTHROPIC_AUTH_TOKEN")
    if auth_token and not interactive and not env.get("ANTHROPIC_API_KEY"):
        env["ANTHROPIC_API_KEY"] = auth_token
        del env["ANTHROPIC_AUTH_TOKEN"]
    return env


def _emit_output(
    completed: subprocess.CompletedProcess[str],
    term: Terminal,
    *,
    interactive: bool,
) -> tuple[str, str]:
    stdout = redact_text(getattr(completed, "stdout", ""))
    stderr = redact_text(getattr(completed, "stderr", ""))
    if not interactive and not term.json_mode:
        if stdout:
            term.line(stdout.rstrip())
        if stderr and completed.returncode != 0:
            term.line(stderr.rstrip(), error=True)
    return stdout, stderr


def _finalize_success(
    root: Path,
    handoff_id: str,
    session_id: str,
    provider: str,
    session_status: str,
    effective_returncode: int | None,
    capture: dict[str, Any],
    stdout: str,
    stderr: str,
    completed: subprocess.CompletedProcess[str],
    term: Terminal,
) -> int:
    session_failed = session_status in {
        str(SessionStatus.FAILED),
        str(SessionStatus.LAUNCH_FAILED),
        str(SessionStatus.TIMED_OUT),
    }
    if completed.returncode != 0 or session_failed:
        returncode = int(effective_returncode if effective_returncode is not None else 1)
        if handoff_id:
            update_handoff_status(
                root,
                handoff_id,
                status=SessionStatus.FAILED,
                returncode=returncode,
            )
        term.error(f"{provider} exited with code {returncode}")
        term.capture_result(
            {
                "id": handoff_id,
                "session_id": session_id,
                "provider": provider,
                "returncode": returncode,
                "stdout": stdout,
                "stderr": stderr,
                "error_code": E_PROVIDER_NONZERO,
            }
        )
        return 10

    if handoff_id:
        update_handoff_status(root, handoff_id, status=SessionStatus.SUCCEEDED, returncode=0)
    term.success(f"Recorded session {session_id} (handoff {handoff_id})")
    if capture.get("turns_captured"):
        term.detail(f"Captured {capture['turns_captured']} turns from the {provider} transcript")
    term.capture_result(
        {
            "id": handoff_id,
            "session_id": session_id,
            "provider": provider,
            "returncode": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
    )
    return 0


def run_provider_session(
    root: Path,
    provider: str,
    executable: str,
    session_id: str,
    handoff_id: str,
    prompt: str,
    term: Terminal,
    *,
    interactive: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> int:
    from datetime import UTC

    launch_ts = datetime.now(tz=UTC)
    try:
        command = build_launch_command(provider, executable, prompt, root, interactive=interactive)
        if interactive:
            term.info(f"Starting {provider} (session {session_id}, handoff {handoff_id})")
        else:
            term.info(
                f"Starting {provider} (timeout {timeout}s, session {session_id}, handoff {handoff_id})"
            )
        completed = _launch_subprocess(
            command,
            root,
            provider=provider,
            interactive=interactive,
            timeout=timeout,
        )
    except OSError as exc:
        if handoff_id:
            update_handoff_status(root, handoff_id, status=SessionStatus.LAUNCH_FAILED)
        _LOGGER.exception(
            "failed to launch provider",
            extra={
                "component": "runner",
                "root": str(root),
                "session_id": session_id,
                "handoff_id": handoff_id,
                "provider": provider,
                "executable": executable,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        finalize_session(
            SessionContext.from_args(root, session_id, provider, launch_ts),
            FinalizeOptions(
                status=SessionStatus.LAUNCH_FAILED,
                returncode=None,
                files_changed=current_files_changed(root),
                component="runner",
            ),
        )
        raise LoghopError(
            f"failed to launch provider `{provider}`: {exc}",
            code=E_PROVIDER_LAUNCH_FAILED,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        if handoff_id:
            update_handoff_status(root, handoff_id, status=SessionStatus.TIMED_OUT)
        partial_output = redact_text(str(exc.stdout or ""))
        _LOGGER.warning(
            "provider timed out",
            extra={
                "component": "runner",
                "root": str(root),
                "session_id": session_id,
                "handoff_id": handoff_id,
                "provider": provider,
                "timeout": timeout,
            },
        )
        ctx = SessionContext.from_args(root, session_id, provider, launch_ts)
        capture_and_finalize_session(
            ctx,
            CaptureOptions(
                status=SessionStatus.TIMED_OUT,
                returncode=None,
                output=partial_output,
                opts=TranscriptOptions(match_texts=_capture_hints(prompt)),
                component="runner",
            ),
        )
        raise LoghopError(
            f"provider `{provider}` timed out after {timeout} seconds.",
            code=E_TIMEOUT,
            exit_code=3,
        ) from exc
    except KeyboardInterrupt:
        ctx = SessionContext.from_args(root, session_id, provider, launch_ts)
        _mark_interrupted(ctx, handoff_id, prompt)
        raise
    except BaseException:
        ctx = SessionContext.from_args(root, session_id, provider, launch_ts)
        _mark_interrupted_defensive(ctx, handoff_id, prompt)
        raise

    stdout, stderr = _emit_output(completed, term, interactive=interactive)
    ctx = SessionContext.from_args(root, session_id, provider, launch_ts)
    meta, capture = capture_and_finalize_session(
        ctx,
        CaptureOptions(
            status=SessionStatus.SUCCEEDED if completed.returncode == 0 else SessionStatus.FAILED,
            returncode=int(completed.returncode),
            output=stdout,
            opts=TranscriptOptions(match_texts=_capture_hints(prompt)),
            component="runner",
        ),
    )
    return _finalize_success(
        root,
        handoff_id,
        session_id,
        provider,
        str(meta.status),
        int(meta.returncode) if meta.returncode is not None else None,
        dict(capture),
        stdout,
        stderr,
        completed,
        term,
    )


def _capture_hints(prompt: str) -> list[str]:
    return [line.strip() for line in prompt.splitlines() if line.strip()]
