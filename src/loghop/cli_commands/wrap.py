import argparse
import os
import subprocess  # nosec B404
from datetime import UTC, datetime
from pathlib import Path

from loghop.cli_commands._helpers import (
    require_provider_arg,
    resolve_enabled_provider,
)
from loghop.errors import E_PROVIDER_LAUNCH_FAILED, LoghopError
from loghop.logging import get_logger
from loghop.providers import claude_api_environment
from loghop.session_lifecycle import (
    CaptureOptions,
    FinalizeOptions,
    SessionContext,
    TranscriptOptions,
    capture_and_finalize_session,
    finalize_session,
)
from loghop.store import find_project_root, load_config, project_paths
from loghop.store._constants import SessionStatus
from loghop.store._models import ProjectConfig
from loghop.store._session import create_session, current_files_changed
from loghop.store._topic import resolve_or_create_topic
from loghop.terminal import Terminal

_LOGGER = get_logger()


def handle_wrap(args: argparse.Namespace, term: Terminal) -> int:
    """Transparent passthrough: run the provider binary and capture its transcript.

    If the cwd is not inside a loghop-initialized repository, exec the binary
    directly (no capture, no overhead). Inside a loghop repo: create a session,
    inherit stdio so the user interacts normally, then sweep the transcript on
    exit.
    """
    provider = require_provider_arg(args.provider, "wrap")
    passthrough = list(args.passthrough or [])

    cwd = Path.cwd()
    project_root = find_project_root(cwd)
    if project_root is None:
        return _exec_directly(provider, passthrough)

    paths = project_paths(project_root)
    config = load_config(paths)
    executable = _resolve_wrapped_executable(provider, config)
    goal = config.goal or "(wrapped)"
    topic = resolve_or_create_topic(project_root, goal=goal, explicit_topic_id="", new_topic=False)
    session = create_session(
        project_root, provider=provider, goal=goal, handoff_id="", topic_id=topic.id
    )
    session_id = session.id
    launch_ts = datetime.now(tz=UTC)
    completed = None
    interrupted = False
    finalized = False
    try:
        term.info(f"Wrapping {provider} in session {session_id}")
        completed = subprocess.run(  # nosec B603
            [executable, *passthrough],
            cwd=cwd,
            env=_wrapped_provider_env(provider, project_root),
            check=False,
        )
    except OSError as exc:
        _LOGGER.exception(
            "failed to launch wrapped provider",
            extra={
                "component": "wrap",
                "root": str(project_root),
                "session_id": session_id,
                "provider": provider,
                "executable": executable,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        finalize_session(
            SessionContext.from_args(project_root, session_id, provider, launch_ts),
            FinalizeOptions(
                status=SessionStatus.LAUNCH_FAILED,
                returncode=None,
                files_changed=current_files_changed(project_root),
                component="wrap",
            ),
        )
        finalized = True
        raise LoghopError(
            f"failed to launch provider `{provider}`: {exc}",
            code=E_PROVIDER_LAUNCH_FAILED,
        ) from exc
    except KeyboardInterrupt:
        interrupted = True
    finally:
        if not finalized:
            _finalize_wrapped_session(
                project_root, session_id, provider, launch_ts, completed, interrupted, cwd, term
            )
    if interrupted:
        raise KeyboardInterrupt
    if completed is None:
        return 1
    return int(completed.returncode)


def _finalize_wrapped_session(
    project_root: Path,
    session_id: str,
    provider: str,
    launch_ts: datetime,
    completed: subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str] | None,
    interrupted: bool,
    transcript_cwd: Path,
    term: Terminal,
) -> None:
    if interrupted:
        status = SessionStatus.INTERRUPTED
        returncode = 130
    elif completed is None:
        status = SessionStatus.INTERRUPTED
        returncode = 1
    else:
        status = SessionStatus.SUCCEEDED if completed.returncode == 0 else SessionStatus.FAILED
        returncode = completed.returncode
    _, capture = capture_and_finalize_session(
        SessionContext.from_args(project_root, session_id, provider, launch_ts),
        CaptureOptions(
            status=status,
            returncode=returncode,
            opts=TranscriptOptions(transcript_cwd=transcript_cwd),
            component="wrap",
        ),
    )
    if capture.get("turns_captured"):
        term.detail(f"Captured {capture['turns_captured']} turns from {provider} into {session_id}")
    elif status == SessionStatus.SUCCEEDED:
        term.detail(f"Recorded {session_id} (no transcript found)")
    elif status == SessionStatus.INTERRUPTED:
        term.detail(f"{session_id} interrupted; captured what was on disk")


def _exec_directly(provider: str, passthrough: list[str]) -> int:
    from shutil import which

    path = _real_provider_from_env(provider) or _direct_provider_path(provider) or which(provider)
    if not path:
        raise LoghopError(
            f"provider `{provider}` is not installed or not in PATH.",
            code=E_PROVIDER_LAUNCH_FAILED,
        )
    if not Path(path).is_absolute():
        raise LoghopError(
            f"refusing to exec non-absolute provider path: {path!r}",
            code=E_PROVIDER_LAUNCH_FAILED,
        )
    os.execv(path, [path, *passthrough])  # nosec B606
    return 0  # unreachable


def _direct_provider_path(provider: str) -> str:
    if provider != "codex":
        return ""
    from shutil import which

    from loghop.install._shim import _is_loghop_shim, detect_real_binary

    first = which(provider) or ""
    if not first:
        return ""
    first_path = Path(first)
    if not _is_loghop_shim(first_path):
        return first
    return detect_real_binary(provider, exclude_dir=first_path.parent) or ""


def _resolve_wrapped_executable(provider: str, config: ProjectConfig) -> str:
    override = _real_provider_from_env(provider)
    if override:
        return override
    return resolve_enabled_provider(provider, config)


def _real_provider_from_env(provider: str) -> str:
    raw = os.environ.get(f"LOGHOP_REAL_{provider.upper()}", "").strip()
    if not raw:
        return ""
    path = Path(raw)
    if not path.is_absolute():
        return ""
    return str(path)


def _wrapped_provider_env(provider: str, project_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    if provider != "claude":
        return env
    env.update(claude_api_environment(project_root))
    auth_token = env.get("ANTHROPIC_AUTH_TOKEN")
    if auth_token and not env.get("ANTHROPIC_API_KEY"):
        env["ANTHROPIC_API_KEY"] = auth_token
        del env["ANTHROPIC_AUTH_TOKEN"]
    return env
