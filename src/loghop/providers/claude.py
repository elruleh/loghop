import json
import os
import shutil
import subprocess  # nosec B404
import time
from pathlib import Path

from loghop import env
from loghop.errors import (
    AUTH_FAILURE_NEEDLES,
    E_PROVIDER_AUTH_MISSING,
    LoghopError,
)
from loghop.providers.base import BaseProvider, ProviderDetection
from loghop.redact import redact_text

_CLAUDE_AUTH_TIMEOUT_SECONDS = 5
_CLAUDE_SHELL_ENV_TIMEOUT_SECONDS = 3
_CLAUDE_SHELL_ENV_CACHE_TTL_SECONDS = 30
_CLAUDE_AUTH_FAILURE_NEEDLES = AUTH_FAILURE_NEEDLES

# Cache for the interactive shell env probe. The shell env may change between
# invocations (e.g. user runs ``export ANTHROPIC_API_KEY=...`` in another
# terminal then calls loghop again), so we keep a TTL-bounded cache rather
# than a process-lifetime one. ``invalidate_shell_env_cache()`` can still force
# a re-probe on demand.
_SHELL_ENV_CACHE: dict[str, tuple[float, dict[str, str]]] = {}

_API_CREDENTIAL_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
)
_API_TRANSPORT_ENV_VARS = ("ANTHROPIC_BASE_URL",)
_CLAUDE_ENV_PREFIXES = (
    "ANTHROPIC_",
    "CLAUDE_CODE_",
)


class ClaudeProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "claude"

    def detect(self, exclude_dir: Path | None = None) -> ProviderDetection:
        path = shutil.which(self.name) or ""
        return ProviderDetection(name=self.name, path=path)

    def build_launch_command(
        self,
        executable: str,
        prompt: str,
        project_root: Path,
        *,
        interactive: bool = False,
    ) -> list[str]:
        claude_args = [executable]
        if claude_uses_api_transport(project_root) and not interactive:
            claude_args.append("--bare")
        if interactive:
            return [*claude_args, prompt]
        return [*claude_args, "--print", prompt]

    def ensure_ready(self, executable: str, project_root: Path) -> None:
        auth_check = _claude_auth_check(executable, project_root)
        if auth_check.available:
            return
        raise LoghopError(
            auth_check.message,
            code=E_PROVIDER_AUTH_MISSING,
        )


class _ClaudeAuthCheck:
    def __init__(self, available: bool, message: str = ""):
        self.available = available
        self.message = message


def _claude_auth_check(executable: str, project_root: Path) -> _ClaudeAuthCheck:
    if claude_uses_api_transport(project_root):
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


def claude_api_environment(project_root: Path | None = None) -> dict[str, str]:
    """Return Claude-related environment from the current or interactive shell."""
    env_dict = _current_claude_environment()
    if not _has_claude_api_credential(env_dict):
        from loghop import providers

        env_dict.update(providers._interactive_shell_claude_environment())

    if project_root is not None:
        for path in _claude_settings_paths(project_root):
            for key, value in _settings_claude_environment(_read_json_object(path)).items():
                env_dict.setdefault(key, value)

    return {key: value for key, value in env_dict.items() if value}


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
    _SHELL_ENV_CACHE.clear()


def _interactive_shell_claude_environment() -> dict[str, str]:
    """Probe the interactive shell for Claude-related env vars.

    The probe is gated by ``LOGHOP_DISABLE_CLAUDE_SHELL_ENV_PROBE`` and the
    result is cached for ``_CLAUDE_SHELL_ENV_CACHE_TTL_SECONDS`` so that short
    bursts of loghop invocations don't keep spawning ``bash``.
    """
    cache_key = "claude"
    now = time.monotonic()
    cached = _SHELL_ENV_CACHE.get(cache_key)
    if cached is not None:
        cached_at, cached_value = cached
        if now - cached_at < _CLAUDE_SHELL_ENV_CACHE_TTL_SECONDS:
            return cached_value

    if not env.claude_shell_env_probe_enabled():
        result: dict[str, str] = {}
    else:
        result = _probe_shell_claude_environment()
    _SHELL_ENV_CACHE[cache_key] = (now, result)
    return result


def _probe_shell_claude_environment() -> dict[str, str]:
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

    stdout = completed.stdout
    stdout_text = stdout if isinstance(stdout, str) else stdout.decode(errors="replace")
    claude_env: dict[str, str] = {}
    for entry in stdout_text.split("\0"):
        if "=" not in entry:
            continue
        key, value = entry.split("=", 1)
        if value and _is_claude_environment_name(key):
            claude_env[key] = value
    return claude_env


def _is_claude_environment_name(name: str) -> bool:
    return name in _API_CREDENTIAL_ENV_VARS or name.startswith(_CLAUDE_ENV_PREFIXES)


def _has_claude_api_credential(env_dict: dict[str, str]) -> bool:
    return any(bool(env_dict.get(varname)) for varname in _API_CREDENTIAL_ENV_VARS)


def _has_claude_api_transport(env_dict: dict[str, str]) -> bool:
    return _has_claude_api_credential(env_dict) or any(
        bool(env_dict.get(varname)) for varname in _API_TRANSPORT_ENV_VARS
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
    env_dict = settings.get("env")
    if not isinstance(env_dict, dict):
        return {}
    return {
        key: value
        for key, value in env_dict.items()
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
