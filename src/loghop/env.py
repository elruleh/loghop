import os


def log_level() -> str:
    return os.environ.get("LOGHOP_LOG_LEVEL", "INFO").upper()


def log_max_bytes(default: int = 256 * 1024) -> int:
    return _env_int("LOGHOP_LOG_MAX_BYTES", default)


def log_backup_count(default: int = 3) -> int:
    return _env_int("LOGHOP_LOG_BACKUP_COUNT", default)


def provider_auth_retries(default: int = 2) -> int:
    return _env_int("LOGHOP_PROVIDER_AUTH_RETRIES", default)


def provider_auth_retry_delay_ms(default: int = 100) -> int:
    return _env_int("LOGHOP_PROVIDER_AUTH_RETRY_DELAY_MS", default)


def claude_shell_env_probe_enabled() -> bool:
    raw = os.environ.get("LOGHOP_DISABLE_CLAUDE_SHELL_ENV_PROBE", "").strip().lower()
    return raw not in {"1", "true", "yes", "on"}


def no_color() -> bool:
    return bool(os.environ.get("NO_COLOR") or os.environ.get("LOGHOP_NO_COLOR"))


def ascii_glyphs() -> bool:
    return bool(os.environ.get("LOGHOP_ASCII") or os.environ.get("NO_COLOR"))


def lang() -> str:
    return os.environ.get("LOGHOP_LANG", "")


def language() -> str:
    return os.environ.get("LANGUAGE", "")


def locale_lang() -> str:
    return os.environ.get("LANG", "")


def is_wsl_windows_terminal() -> bool:
    return bool(os.environ.get("WT_SESSION"))


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default
