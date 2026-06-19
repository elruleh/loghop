import json
import os
import shutil
import subprocess  # nosec B404
import time
from pathlib import Path

from loghop.providers.base import BaseProvider, ProviderDetection
from loghop.providers.claude import (
    ClaudeProvider,
    _claude_auth_check,
    _combined_output,
    _interactive_shell_claude_environment,
    _looks_like_auth_failure,
    _one_line_detail,
    _read_json_object,
    _settings_claude_environment,
    _settings_enable_api_transport,
    claude_api_environment,
    claude_uses_api_transport,
    invalidate_shell_env_cache,
)
from loghop.providers.codex import CodexProvider

__all__ = [
    "json",
    "os",
    "shutil",
    "subprocess",
    "time",
    "BaseProvider",
    "ProviderDetection",
    "ClaudeProvider",
    "CodexProvider",
    "SUPPORTED_PROVIDER_NAMES",
    "get_provider",
    "detect_provider",
    "detect_all",
    "build_launch_command",
    "ensure_provider_ready",
    "claude_api_environment",
    "claude_uses_api_transport",
    "invalidate_shell_env_cache",
    "_ProviderDetection",
    "_claude_uses_api_transport",
    "_interactive_shell_claude_environment",
    "_claude_auth_check",
    "_read_json_object",
    "_settings_claude_environment",
    "_one_line_detail",
    "_combined_output",
    "_looks_like_auth_failure",
    "_settings_enable_api_transport",
]

SUPPORTED_PROVIDER_NAMES = ("codex", "claude")
_ProviderDetection = ProviderDetection
_claude_uses_api_transport = claude_uses_api_transport

_REGISTRY: dict[str, BaseProvider] = {
    "claude": ClaudeProvider(),
    "codex": CodexProvider(),
}


def get_provider(name: str) -> BaseProvider:
    if name not in _REGISTRY:
        from loghop.errors import E_UNKNOWN_PROVIDER, LoghopError

        raise LoghopError(f"unsupported provider: {name}", code=E_UNKNOWN_PROVIDER)
    return _REGISTRY[name]


def detect_provider(name: str, *, exclude_dir: Path | None = None) -> ProviderDetection:
    return get_provider(name).detect(exclude_dir=exclude_dir)


def detect_all() -> dict[str, ProviderDetection]:
    return {name: detect_provider(name) for name in SUPPORTED_PROVIDER_NAMES}


def build_launch_command(
    provider: str,
    executable: str,
    prompt: str,
    project_root: Path,
    *,
    interactive: bool = False,
) -> list[str]:
    """Return the argv list for launching ``provider``.

    Defense in depth:
    - ``provider`` is validated against ``SUPPORTED_PROVIDER_NAMES``.
    - ``executable`` must be an absolute path.
    """
    if provider not in SUPPORTED_PROVIDER_NAMES:
        raise ValueError(f"unsupported provider: {provider}")
    if not executable or not Path(executable).is_absolute():
        raise ValueError(f"provider executable must be an absolute path, got: {executable!r}")
    return get_provider(provider).build_launch_command(
        executable, prompt, project_root, interactive=interactive
    )


def ensure_provider_ready(provider: str, executable: str, project_root: Path) -> None:
    """Fail before creating loghop records when provider auth is known-bad."""
    get_provider(provider).ensure_ready(executable, project_root)
