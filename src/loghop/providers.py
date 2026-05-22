import json
import os
import shutil
import subprocess  # nosec B404
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from loghop import env
from loghop.errors import (
    AUTH_FAILURE_NEEDLES,
    E_PROVIDER_AUTH_MISSING,
    E_UNKNOWN_PROVIDER,
    LoghopError,
)
from loghop.redact import redact_text

SUPPORTED_PROVIDER_NAMES = ("codex", "claude")
_CLAUDE_AUTH_TIMEOUT_SECONDS = 5
_CLAUDE_SHELL_ENV_TIMEOUT_SECONDS = 3
_CLAUDE_AUTH_FAILURE_NEEDLES = AUTH_FAILURE_NEEDLES


@dataclass(frozen=True)
class _ProviderDetection:
    name: str
    path: str

    @property
    def installed(self) -> bool:
        return bool(self.path)


@dataclass(frozen=True)
class _ClaudeAuthCheck:
    available: bool
    message: str = ""


def detect_provider(name: str, *, exclude_dir: Path | None = None) -> _ProviderDetection:
    if name not in SUPPORTED_PROVIDER_NAMES:
        raise LoghopError(f"unsupported provider: {name}", code=E_UNKNOWN_PROVIDER)
    if exclude_dir is not None and name == "codex":
        from loghop.install._shim import detect_real_binary

        path = detect_real_binary(name, exclude_dir=exclude_dir) or ""
    else:
        path = shutil.which(name) or ""
    return _ProviderDetection(name=name, path=path)


def detect_all() -> dict[str, _ProviderDetection]:
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
    - ``executable`` must be an absolute path. ``shutil.which`` already
      returns absolute paths in practice, but we verify here so a malicious
      or malformed config that injected a relative path cannot cause CWD
      hijacking when ``subprocess.run`` resolves it.
    """
    if provider not in SUPPORTED_PROVIDER_NAMES:
        raise ValueError(f"unsupported provider: {provider}")
    if not executable or not Path(executable).is_absolute():
        raise ValueError(f"provider executable must be an absolute path, got: {executable!r}")
    if provider == "codex":
        if interactive:
            return [executable, "--", prompt]
        return [executable, "exec", "--cd", str(project_root), "--color", "never", prompt]
    if provider == "claude":
        claude_args = [executable]
        if _claude_uses_api_transport(project_root) and not interactive:
            claude_args.append("--bare")
        if interactive:
            return [*claude_args, prompt]
        return [*claude_args, "--print", prompt]
    raise ValueError(f"unsupported provider: {provider}")


def ensure_provider_ready(provider: str, executable: str, project_root: Path) -> None:
    """Fail before creating loghop records when provider auth is known-bad."""
    if provider not in SUPPORTED_PROVIDER_NAMES:
        raise ValueError(f"unsupported provider: {provider}")
    if provider != "claude":
        return
    auth_check = _claude_auth_check(executable, project_root)
    if auth_check.available:
        return
    raise LoghopError(
        auth_check.message,
        code=E_PROVIDER_AUTH_MISSING,
    )


def _claude_auth_check(executable: str, project_root: Path) -> _ClaudeAuthCheck:
    if _claude_uses_api_transport(project_root):
        return _ClaudeAuthCheck(available=True)
    try:
        completed = _run_claude_auth_status(executable, project_root)
    except subprocess.TimeoutExpired:
        return _ClaudeAuthCheck(
            available=False,
            message=(
                "Claude auth preflight timed out while running `claude auth status`. "
                f"Timeout: {_CLAUDE_AUTH_TIMEOUT_SECONDS}s. "
                "Claude may still work, but loghop could not verify auth state in time."
            ),
        )
    except OSError as exc:
        return _ClaudeAuthCheck(
            available=False,
            message=(
                "Claude auth preflight could not run `claude auth status`: "
                f"{exc}. Claude may be installed incorrectly for this shell."
            ),
        )

    combined_output = _combined_output(completed.stdout, completed.stderr)
    lowered_output = combined_output.lower()

    # Try JSON first — `claude auth status` outputs structured JSON
    # regardless of whether it exits 0 or 1.
    try:
        data = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        pass
    else:
        if isinstance(data, dict) and "loggedIn" in data:
            if bool(data["loggedIn"]):
                return _ClaudeAuthCheck(available=True)
            return _ClaudeAuthCheck(
                available=False,
                message=(
                    "Claude Code reported `loggedIn: false` for this shell. "
                    "Run `claude /login`, or export `ANTHROPIC_API_KEY`, or configure "
                    "`apiKeyHelper` in Claude settings before launching Claude from loghop."
                ),
            )

    # JSON wasn't available — fall back to keyword heuristics.
    if _looks_like_auth_failure(lowered_output):
        return _ClaudeAuthCheck(
            available=False,
            message=(
                "Claude Code is not authenticated for this shell. "
                "Run `claude /login`, or export `ANTHROPIC_API_KEY`, or configure "
                "`apiKeyHelper` in Claude settings before launching Claude from loghop."
            ),
        )

    if "logged in" in lowered_output:
        return _ClaudeAuthCheck(available=True)

    if completed.returncode != 0:
        detail = _one_line_detail(redact_text(combined_output))
        suffix = f" Detail: {detail}" if detail else ""
        return _ClaudeAuthCheck(
            available=False,
            message=(
                "Claude auth preflight failed while running `claude auth status` "
                f"(exit {completed.returncode}).{suffix}"
            ),
        )

    detail = _one_line_detail(redact_text(combined_output))
    suffix = f" Detail: {detail}" if detail else ""
    return _ClaudeAuthCheck(
        available=False,
        message=(
            "Claude auth preflight returned an unexpected response from "
            "`claude auth status`." + suffix
        ),
    )


def _run_claude_auth_status(
    executable: str, project_root: Path
) -> subprocess.CompletedProcess[str]:
    attempts = max(1, env.provider_auth_retries())
    delay = max(0, env.provider_auth_retry_delay_ms()) / 1000
    last_error: OSError | subprocess.TimeoutExpired | None = None
    for attempt in range(attempts):
        try:
            return subprocess.run(  # nosec B603
                [executable, "auth", "status"],
                cwd=project_root,
                check=False,
                capture_output=True,
                text=True,
                timeout=_CLAUDE_AUTH_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_error = exc
            if attempt < attempts - 1 and delay:
                time.sleep(delay)
    if last_error is not None:
        raise last_error
    raise OSError("Claude auth preflight did not run")


_API_CREDENTIAL_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
)
_API_TRANSPORT_ENV_VARS = ("ANTHROPIC_BASE_URL",)
_CLAUDE_ENV_PREFIXES = (
    "ANTHROPIC_",
    "CLAUDE_CODE_",
)


def claude_api_environment(project_root: Path | None = None) -> dict[str, str]:
    """Return Claude-related environment from the current or interactive shell.

    TUI-launched shells do not always inherit the user's interactive shell
    exports. When the current process lacks credentials, probe an interactive
    bash environment and only keep Claude-scoped variables.
    """
    env = _current_claude_environment()
    if not _has_claude_api_credential(env):
        env.update(_interactive_shell_claude_environment())

    if project_root is not None:
        for path in _claude_settings_paths(project_root):
            for key, value in _settings_claude_environment(_read_json_object(path)).items():
                env.setdefault(key, value)

    return {key: value for key, value in env.items() if value}


def _claude_uses_api_transport(project_root: Path) -> bool:
    return claude_uses_api_transport(project_root)


def claude_uses_api_transport(project_root: Path) -> bool:
    if _has_claude_api_transport(claude_api_environment(project_root)):
        return True
    for path in _claude_settings_paths(project_root):
        data = _read_json_object(path)
        if _settings_enable_api_transport(data):
            return True
    return False


def _current_claude_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if value and _is_claude_environment_name(key)
    }


def invalidate_shell_env_cache() -> None:
    """Clear the cached interactive shell environment probe."""
    _interactive_shell_claude_environment.cache_clear()


@lru_cache(maxsize=1)
def _interactive_shell_claude_environment() -> dict[str, str]:
    if not env.claude_shell_env_probe_enabled():
        return {}
    try:
        completed = subprocess.run(  # nosec B603, B607
            ["bash", "-c", "env -0"],
            check=False,
            capture_output=True,
            timeout=_CLAUDE_SHELL_ENV_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if completed.returncode != 0:
        return {}

    claude_env: dict[str, str] = {}
    for entry in completed.stdout.decode(errors="replace").split("\0"):
        if "=" not in entry:
            continue
        key, value = entry.split("=", 1)
        if value and _is_claude_environment_name(key):
            claude_env[key] = value
    return claude_env


def _is_claude_environment_name(name: str) -> bool:
    return name in _API_CREDENTIAL_ENV_VARS or name.startswith(_CLAUDE_ENV_PREFIXES)


def _has_claude_api_credential(env: dict[str, str]) -> bool:
    return any(bool(env.get(varname)) for varname in _API_CREDENTIAL_ENV_VARS)


def _has_claude_api_transport(env: dict[str, str]) -> bool:
    return _has_claude_api_credential(env) or any(
        bool(env.get(varname)) for varname in _API_TRANSPORT_ENV_VARS
    )


def _claude_settings_paths(project_root: Path) -> tuple[Path, ...]:
    return (
        Path.home() / ".claude" / "settings.json",
        project_root / ".claude" / "settings.json",
        project_root / ".claude" / "settings.local.json",
    )


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        from loghop.store._io import safe_read_text

        data = json.loads(safe_read_text(path))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _settings_enable_api_transport(settings: dict[str, object]) -> bool:
    if settings.get("apiKeyHelper"):
        return True
    return _has_claude_api_transport(_settings_claude_environment(settings))


def _settings_claude_environment(settings: dict[str, object]) -> dict[str, str]:
    env = settings.get("env")
    if not isinstance(env, dict):
        return {}
    return {
        key: value
        for key, value in env.items()
        if isinstance(key, str) and isinstance(value, str) and _is_claude_environment_name(key)
    }


def _combined_output(stdout: str, stderr: str) -> str:
    return "\n".join(part.strip() for part in (stdout, stderr) if part and part.strip())


def _one_line_detail(text: str, *, limit: int = 220) -> str:
    line = " ".join(text.split())
    if len(line) <= limit:
        return line
    return line[: limit - 1].rstrip() + "…"


def _looks_like_auth_failure(text: str) -> bool:
    return any(needle in text for needle in _CLAUDE_AUTH_FAILURE_NEEDLES)
