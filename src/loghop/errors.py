"""Stable error codes for loghop CLI surface.

Exit code table:

- 0   success
- 1   unexpected internal error
- 2   usage / validation error
- 3   timeout
- 10  provider run exited non-zero
- 20  project not initialized
"""

from pathlib import Path


def _sanitize_path(text: str) -> str:
    """Replace absolute home directory prefix with ~ for error messages."""
    home = str(Path.home())
    if home and text.startswith(home):
        return "~" + text[len(home) :]
    return text


def sanitize_error_message(message: str) -> str:
    """Sanitize absolute paths in error messages for non-interactive output.

    Replaces $HOME prefixes with ~ so that structured output (JSON, --quiet)
    does not leak full directory layouts to shared logs.
    """
    return _sanitize_path(message)


class LoghopError(ValueError):
    """Typed error for the CLI surface."""

    def __init__(self, message: str, *, code: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


E_NOT_INITIALIZED = "E_NOT_INITIALIZED"
E_NOT_GIT_REPO = "E_NOT_GIT_REPO"
E_UNKNOWN_PROVIDER = "E_UNKNOWN_PROVIDER"
E_PROVIDER_MISSING = "E_PROVIDER_MISSING"
E_PROVIDER_AUTH_MISSING = "E_PROVIDER_AUTH_MISSING"
E_PROVIDER_LAUNCH_FAILED = "E_PROVIDER_LAUNCH_FAILED"
E_PROVIDER_NONZERO = "E_PROVIDER_NONZERO"
E_INVALID_INPUT = "E_INVALID_INPUT"
E_MISSING_PROVIDER_ARG = "E_MISSING_PROVIDER_ARG"
E_TIMEOUT = "E_TIMEOUT"
E_UNEXPECTED = "E_UNEXPECTED"

AUTH_FAILURE_NEEDLES: tuple[str, ...] = (
    "not logged in",
    "please run /login",
    "invalid api key",
    "authentication failed",
    "unauthorized",
)
