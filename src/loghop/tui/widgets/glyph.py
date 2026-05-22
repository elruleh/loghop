"""Centralized iconography with ASCII fallback for terminals without Unicode."""

import sys

from loghop import env


def _supports_unicode() -> bool:
    if env.ascii_glyphs():
        return False
    encoding = (sys.stdout.encoding or "").lower()
    if "utf" not in encoding:
        return False
    lang = (env.locale_lang()).lower()
    return lang not in {"c", "posix"}


_UNICODE = _supports_unicode()


def _pick(unicode: str, ascii_: str) -> str:
    return unicode if _UNICODE else ascii_


CURRENT = _pick("●", "*")
OK = _pick("✓", "v")
FAIL = _pick("✗", "x")
WARN = _pick("⚠", "!")
INFO = _pick("ℹ", "i")
RUN = _pick("◐", "~")
NONE = _pick("·", ".")
SEP_CRUMB = _pick("›", ">")
CHIP_CLOSE = _pick("×", "x")
DOT = _pick("•", "-")
ELLIPSIS = _pick("…", "...")
BRAND_MARK = _pick("●", "*")
KEY_ENTER = _pick("⏎", "<enter>")
SEP_DOT = _pick("·", "-")
CLOCK = _pick("⏱", "@")
HANDOFF = _pick("⤴", "^")

# Spinner frames for animated "running" indicators
SPINNER_FRAMES: tuple[str, ...] = (
    ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏") if _UNICODE else ("|", "/", "-", "\\")
)
