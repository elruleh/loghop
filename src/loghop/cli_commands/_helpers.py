import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from loghop.errors import (
    AUTH_FAILURE_NEEDLES,
    E_INVALID_INPUT,
    E_MISSING_PROVIDER_ARG,
    E_NOT_GIT_REPO,
    E_NOT_INITIALIZED,
    E_PROVIDER_MISSING,
    E_UNKNOWN_PROVIDER,
    LoghopError,
)
from loghop.gittools import GitRepo
from loghop.logging import get_logger
from loghop.providers import SUPPORTED_PROVIDER_NAMES, detect_provider
from loghop.store import ProjectPaths, find_project_root, load_config, project_paths
from loghop.store._models import ProjectConfig

LOGGER = get_logger()
MAX_INPUT_LENGTH = 4000
DEFAULT_AD_HOC_GOAL = "Ad hoc session"
_AUTH_FAILURE_SUMMARY_NEEDLES = AUTH_FAILURE_NEEDLES


def validate_length(value: str, field: str) -> str:
    if "\x00" in value:
        raise LoghopError(f"{field} contains null bytes", code=E_INVALID_INPUT)
    if "\n" in value or "\r" in value:
        raise LoghopError(f"{field} must be a single line", code=E_INVALID_INPUT)
    if len(value) > MAX_INPUT_LENGTH:
        raise LoghopError(f"{field} exceeds {MAX_INPUT_LENGTH} characters", code=E_INVALID_INPUT)
    return value


def resolve_goal(goal: str | None, config: ProjectConfig, command: str) -> str:
    resolved = str(goal if goal is not None else config.goal or "")
    if not resolved:
        raise LoghopError(
            f'{command} requires a goal. Run `loghop goal "..."` or pass `--goal`.',
            code=E_INVALID_INPUT,
        )
    return validate_length(resolved, "goal")


def resolve_goal_or_default(
    goal: str | None,
    config: ProjectConfig,
    *,
    default: str = DEFAULT_AD_HOC_GOAL,
) -> str:
    resolved = str(goal if goal is not None else config.goal or "").strip()
    return validate_length(resolved or default, "goal")


def resolve_project_target(target: str) -> Path | None:
    from loghop.store._registry import load_registry

    def _is_valid_project(path: Path) -> bool:
        return path.is_dir() and (path / ".loghop" / "config.toml").exists()

    projects = load_registry()
    candidate = Path(target).expanduser()
    if "/" in target and _is_valid_project(candidate):
        resolved_str = str(candidate.resolve())
        for proj in projects:
            if proj.path == resolved_str:
                return Path(resolved_str)
    exact_name_matches = [
        p for p in projects if p.name == target and _is_valid_project(Path(p.path))
    ]
    if len(exact_name_matches) == 1:
        return Path(exact_name_matches[0].path)
    if len(exact_name_matches) > 1:
        exact_match_labels = ", ".join(f"{p.name} -> {p.path}" for p in exact_name_matches)
        raise LoghopError(
            f"ambiguous target `{target}` matches multiple projects: {exact_match_labels}. "
            "Use the full project path.",
            code=E_INVALID_INPUT,
        )
    fuzzy_matches = [
        p for p in projects if target.lower() in p.name.lower() and _is_valid_project(Path(p.path))
    ]
    if len(fuzzy_matches) == 1:
        return Path(fuzzy_matches[0].path)
    if len(fuzzy_matches) > 1:
        names = ", ".join(f"{p.name} -> {p.path}" for p in fuzzy_matches)
        raise LoghopError(
            f"ambiguous target `{target}` matches multiple projects: {names}. "
            "Use the full project name or path.",
            code=E_INVALID_INPUT,
        )
    return None


def require_git_repo() -> GitRepo:
    """Return a GitRepo for cwd or raise."""
    cwd = Path.cwd()
    repo = GitRepo.from_cwd(cwd)
    if repo is None:
        raise LoghopError(
            "loghop requires a Git repository. Run `git init` here, then try again.",
            code=E_NOT_GIT_REPO,
        )
    return repo


def require_git_repository_root() -> Path:
    return require_git_repo().root.resolve()


def require_project_root() -> Path:
    cwd = Path.cwd()
    repo = GitRepo.from_cwd(cwd)
    if repo is None:
        raise LoghopError(
            "loghop is not initialized here. Run `git init`, then `loghop init`.",
            code=E_NOT_INITIALIZED,
            exit_code=20,
        )
    root = find_project_root(cwd)
    if root is None:
        raise LoghopError(
            "loghop is not initialized in this repository. Run `loghop init`.",
            code=E_NOT_INITIALIZED,
            exit_code=20,
        )
    return root


def require_project_config() -> tuple[Path, ProjectPaths, ProjectConfig]:
    root = require_project_root()
    paths = project_paths(root)
    config = load_config(paths)
    return root, paths, config


def require_supported_provider(provider: str) -> str:
    if provider not in SUPPORTED_PROVIDER_NAMES:
        raise LoghopError(
            f"unsupported provider `{provider}`. Supported: {', '.join(SUPPORTED_PROVIDER_NAMES)}.",
            code=E_UNKNOWN_PROVIDER,
        )
    return provider


def require_provider_arg(provider: str | None, command: str) -> str:
    if not provider:
        raise LoghopError(
            f"{command} requires --provider (codex or claude).",
            code=E_MISSING_PROVIDER_ARG,
        )
    return require_supported_provider(provider)


def resolve_enabled_provider(provider: str, _config: ProjectConfig) -> str:
    require_supported_provider(provider)
    exclude_dir: Path | None = None
    if provider == "codex":
        from loghop.install._config import load_codex_shim_prefix

        exclude_dir = load_codex_shim_prefix()
    detection = detect_provider(provider, exclude_dir=exclude_dir)
    if provider == "codex" and detection.path:
        from loghop.install._shim import _is_loghop_shim

        detected = Path(detection.path)
        if _is_loghop_shim(detected):
            detection = detect_provider(provider, exclude_dir=detected.parent)
    if not detection.installed:
        raise LoghopError(
            f"provider `{provider}` is not installed or not in PATH.",
            code=E_PROVIDER_MISSING,
        )
    return detection.path


def resolve_default_provider(root: Path) -> str | None:
    """Pick a provider without --provider: last healthy session, else first installed."""
    from loghop.store._constants import SKIP_FOR_RESUME
    from loghop.store._session import list_sessions

    paths = project_paths(root)
    config = load_config(paths)
    for session in list_sessions(paths):
        status = str(session.status or "").lower()
        summary = str(session.summary or "").lower()
        if (
            status in SKIP_FOR_RESUME
            or status.endswith("_empty")
            or any(needle in summary for needle in _AUTH_FAILURE_SUMMARY_NEEDLES)
        ):
            continue
        candidate = session.provider or ""
        if candidate in SUPPORTED_PROVIDER_NAMES and _provider_available(candidate, config):
            return candidate
    for name in SUPPORTED_PROVIDER_NAMES:
        if _provider_available(name, config):
            return name
    return None


def _provider_available(provider: str, config: ProjectConfig) -> bool:
    try:
        resolve_enabled_provider(provider, config)
    except LoghopError as exc:
        if exc.code == E_PROVIDER_MISSING:
            return False
        raise
    return True


_SINCE_RE = re.compile(r"^(\d+)([dhw])$")


def format_relative_time(ts: str) -> str:
    """Render an ISO timestamp as a human-readable relative string."""
    if not ts:
        return "never"
    try:
        dt = datetime.fromisoformat(ts)
        now = datetime.now(tz=UTC)
        delta = now - dt
        seconds = int(delta.total_seconds())
        if seconds < 60:  # noqa: PLR2004
            return "just now"
        if seconds < 3600:  # noqa: PLR2004
            return f"{seconds // 60}m ago"
        if seconds < 86400:  # noqa: PLR2004
            return f"{seconds // 3600}h ago"
        if seconds < 604800:  # noqa: PLR2004
            return f"{seconds // 86400}d ago"
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return ts


def truncate_text(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, appending '...' if truncated."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def parse_since(raw: str) -> datetime | None:
    if not raw:
        return None
    match = _SINCE_RE.match(raw)
    if not match:
        raise LoghopError(
            f"invalid --since value `{raw}`. Use formats like `7d`, `12h`, `2w`.",
            code=E_INVALID_INPUT,
        )
    value = int(match.group(1))
    if value > 10000:  # noqa: PLR2004
        raise LoghopError(
            f"--since value too large: {value}. Maximum is 10000.",
            code=E_INVALID_INPUT,
        )
    unit = match.group(2)
    now = datetime.now(tz=UTC)
    if unit == "d":
        return now - timedelta(days=value)
    if unit == "h":
        return now - timedelta(hours=value)
    return now - timedelta(weeks=value)
