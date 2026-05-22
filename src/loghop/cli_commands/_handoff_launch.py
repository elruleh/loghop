import argparse
import os
from pathlib import Path
from typing import Literal

from loghop.cli_commands._helpers import (
    require_project_config,
    require_provider_arg,
    resolve_default_provider,
    resolve_enabled_provider,
    resolve_goal_or_default,
    resolve_project_target,
)
from loghop.cli_commands._runner import run_provider_session
from loghop.errors import E_INVALID_INPUT, E_PROVIDER_AUTH_MISSING, LoghopError
from loghop.logging import get_logger
from loghop.providers import claude_uses_api_transport, ensure_provider_ready
from loghop.reconcile import auto_reconcile_silent
from loghop.resilience import CircuitBreaker
from loghop.store import create_handoff, project_paths
from loghop.store._constants import DEFAULT_TIMEOUT
from loghop.store._handoff import create_resume_handoff
from loghop.store._models import ProjectConfig, TopicMeta
from loghop.store._session import create_session, latest_useful_session
from loghop.store._topic import resolve_or_create_topic
from loghop.terminal import Terminal

_LOGGER = get_logger()

LaunchMode = Literal["fresh", "resume", "auto"]


def launch_handoff_session(
    args: argparse.Namespace,
    term: Terminal,
    *,
    mode: LaunchMode,
    command: str,
) -> int:
    """Build the right handoff, create a session, and launch the provider."""
    _chdir_to_target(args, term, command=command)
    root, paths, config = require_project_config()
    if mode in {"resume", "auto"}:
        auto_reconcile_silent(root)

    provider_arg = getattr(args, "provider", None) or resolve_default_provider(root)
    provider = require_provider_arg(provider_arg, command)
    goal = resolve_goal_or_default(getattr(args, "goal", None), config)
    executable = resolve_enabled_provider(provider, config)
    _reject_unsupported_interactive_api_transport(
        provider,
        root,
        interactive=bool(getattr(args, "interactive", False)),
    )
    _preflight_provider_readiness(term, provider, executable, root)
    _check_circuit_breaker(root, provider)

    topic = _resolve_launch_topic(args, root, goal, config)
    topic_id = topic.id if topic else ""

    previous_session = None
    if mode in {"resume", "auto"}:
        previous_session = latest_useful_session(paths, topic_id=topic_id) if topic_id else None
        if previous_session is None and _should_fallback_to_global_resume(args, topic):
            previous_session = latest_useful_session(paths)
    should_resume = previous_session is not None
    if mode in {"resume", "auto"}:
        prev_id = previous_session.id if previous_session else "none"
        action = "Resuming" if should_resume else "Starting"
        term.info(f"{action} from session {prev_id}")
        _LOGGER.info(
            "building run handoff",
            extra={
                "component": command,
                "root": str(root),
                "provider": provider,
                "mode": mode,
                "previous_session": str(prev_id),
            },
        )

    if should_resume:
        if topic_id:
            record = create_resume_handoff(
                root, provider, goal, previous_session=previous_session, topic_id=topic_id
            )
        else:
            record = create_resume_handoff(root, provider, goal, previous_session=previous_session)
        prompt = _resume_prompt(goal, record.md_path.relative_to(root) if record.md_path else None)
    else:
        record = (
            create_handoff(root, provider, goal, topic_id=topic_id)
            if topic_id
            else create_handoff(root, provider, goal)
        )
        prompt = _fresh_prompt(goal, record.md_path.relative_to(root) if record.md_path else None)

    session = (
        create_session(root, provider=provider, goal=goal, handoff_id=record.id, topic_id=topic_id)
        if topic_id
        else create_session(root, provider=provider, goal=goal, handoff_id=record.id)
    )
    return run_provider_session(
        root,
        provider,
        executable,
        session.id,
        record.id,
        prompt,
        term,
        interactive=bool(getattr(args, "interactive", False)),
        timeout=int(getattr(args, "timeout", DEFAULT_TIMEOUT)),
    )


def _resolve_launch_topic(
    args: argparse.Namespace, root: Path, goal: str, config: ProjectConfig
) -> TopicMeta | None:
    if not isinstance(config, ProjectConfig):
        return None
    if bool(getattr(args, "no_topic", False)):
        return None
    explicit = str(getattr(args, "topic", "") or "").strip()
    new_topic = bool(getattr(args, "new_topic", False))
    return resolve_or_create_topic(
        root,
        goal=goal,
        explicit_topic_id=explicit,
        new_topic=new_topic,
    )


def _should_fallback_to_global_resume(args: argparse.Namespace, topic: TopicMeta | None) -> bool:
    if topic is None:
        return True
    if bool(getattr(args, "new_topic", False)) or bool(getattr(args, "topic", "")):
        return False
    return not bool(topic.session_ids)


def _preflight_provider_readiness(
    term: Terminal,
    provider: str,
    executable: str,
    root: Path,
) -> None:
    try:
        ensure_provider_ready(provider, executable, root)
        _circuit(root, provider).record_success()
    except LoghopError as exc:
        _circuit(root, provider).record_failure()
        if provider != "claude" or exc.code != E_PROVIDER_AUTH_MISSING:
            raise
        detail = str(exc).strip()
        term.warn(f"Claude auth preflight failed. Launch will continue. {detail}")
        _LOGGER.warning(
            "claude auth preflight failed but launch will continue",
            extra={
                "component": "run-preflight",
                "root": str(root),
                "provider": provider,
                "error": detail,
            },
        )


def _check_circuit_breaker(root: Path, provider: str) -> None:
    cb = _circuit(root, provider)
    if not cb.is_allowed():
        raise LoghopError(
            f"provider `{provider}` is temporarily blocked by the circuit breaker "
            f"(state={cb.state}). Recent calls failed repeatedly. "
            "Wait a moment and try again.",
            code=E_PROVIDER_AUTH_MISSING,
        )


def _circuit(root: Path, provider: str) -> CircuitBreaker:
    paths = project_paths(root)
    return CircuitBreaker(state_dir=paths.dot, provider=provider)


def _reject_unsupported_interactive_api_transport(
    provider: str,
    root: Path,
    *,
    interactive: bool,
) -> None:
    if provider != "claude" or not interactive or not claude_uses_api_transport(root):
        return
    raise LoghopError(
        "Claude Code interactive sessions with ANTHROPIC_* API/gateway settings are not "
        "supported by loghop. Use stock Claude login for interactive sessions, or run Claude "
        "through loghop in non-interactive mode with `loghop run --provider claude`.",
        code=E_INVALID_INPUT,
    )


def _chdir_to_target(args: argparse.Namespace, term: Terminal, *, command: str) -> None:
    target = getattr(args, "target", None)
    if not target:
        return
    resolved = resolve_project_target(str(target))
    if resolved is None:
        _LOGGER.warning(
            "project target not found",
            extra={"component": command, "target": str(target)},
        )
        raise LoghopError(
            f"no registered project matches `{target}`. "
            "Run `loghop projects` to see registered projects.",
            code=E_INVALID_INPUT,
        )
    os.chdir(resolved)
    term.info(f"Running in {resolved}")


def _fresh_prompt(goal: str, handoff_rel: Path | None) -> str:
    handoff = handoff_rel or Path("")
    return (
        f"Goal: {goal}\n\n"
        f"Read `{handoff}` in the current repository before acting. "
        "Use that handoff file, its Project Timeline, and repository files as the source of truth. "
        "If the goal is generic, ask the user what to work on and capture the final summary."
    )


def _resume_prompt(goal: str, handoff_rel: Path | None) -> str:
    handoff = handoff_rel or Path("")
    return (
        f"Goal: {goal}\n\n"
        f"Read `{handoff}` in the current repository before acting. "
        "That handoff contains the shared Project Timeline, previous session context, and current repo state. "
        "Continue from where the previous session left off."
    )
