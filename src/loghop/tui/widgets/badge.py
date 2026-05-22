"""Status badge formatting — single source of truth for session/handoff states.

Status colors come from the theme token system. The active theme is resolved at
render time via ``App.app.theme`` so badges keep matching the surrounding
chrome when the user toggles themes.
"""

from loghop import env
from loghop.logging import get_logger
from loghop.tui import strings
from loghop.tui.themes import CLASSIC_DARK, semantic_color, theme_is_light, theme_key
from loghop.tui.widgets import glyph

# (semantic role, glyph, i18n label key) — colors are resolved from theme tokens below.
_LOGGER = get_logger()

_STATUS_ROLE: dict[str, tuple[str, str, str]] = {
    "running": ("warning", glyph.RUN, "STATUS_RUNNING"),
    "succeeded": ("success", glyph.OK, "STATUS_DONE"),
    "failed": ("error", glyph.FAIL, "STATUS_FAILED"),
    "launch_failed": ("error", glyph.FAIL, "STATUS_LAUNCH_FAILED"),
    "interrupted": ("warning", glyph.WARN, "STATUS_STOPPED"),
    "timed_out": ("warning", glyph.CLOCK, "STATUS_TIMED_OUT"),
}


def _active_theme_key() -> str:
    """Return the active registered theme key based on the running App's theme.

    Falls back to Classic Dark outside an App context (e.g. unit tests that
    invoke render() directly).
    """
    try:
        from textual.app import App

        active = (App.app.theme or "").lower()  # type: ignore[attr-defined]  # Textual exposes active app via dynamic App.app
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Failed to resolve active Textual theme", exc_info=True)
        return CLASSIC_DARK.name
    return theme_key(active)


def _resolve_theme(theme: str | None) -> str:
    return theme_key(theme or _active_theme_key())


def render(status: str, *, compact: bool = False, theme: str | None = None) -> str:
    """Return a Rich-marked-up badge for a status string.

    With ``compact=True`` only the icon is rendered (good for dense tables).
    Pass ``theme="dark"|"light"`` to force a theme; otherwise the active
    App theme is used.
    """
    role_map = _STATUS_ROLE.get((status or "").lower())
    if not status or role_map is None:
        body = glyph.NONE if compact else f"{glyph.NONE} {status or '—'}"
        return f"[dim]{body}[/]"
    role, icon, label_key = role_map
    color = semantic_color(role, theme=_resolve_theme(theme))
    body = icon if compact else f"{icon} {strings.tr(label_key)}"
    return f"[bold {color}]{body}[/]"


def is_running(status: str) -> bool:
    return (status or "").lower() == "running"


def color_for(status: str, *, theme: str | None = None) -> str:
    """Return the hex color used for a given status — theme-aware."""
    role_map = _STATUS_ROLE.get((status or "").lower())
    if role_map is None:
        return semantic_color("neutral", theme=_resolve_theme(theme))
    return semantic_color(role_map[0], theme=_resolve_theme(theme))


def role_color(role: str, *, theme: str | None = None) -> str:
    """Resolve a semantic role (``success`` / ``warning`` / ``error``) to its
    theme-appropriate hex color.

    Useful for inline Rich markup outside the status badge (modals, banners).
    """
    return semantic_color(role, theme=_resolve_theme(theme))


_PROVIDER_BADGES_DARK: dict[str, tuple[str, str]] = {
    "claude": ("#a78bfa", "C"),
    "codex": ("#2dd4bf", "X"),
}

_PROVIDER_BADGES_LIGHT: dict[str, tuple[str, str]] = {
    "claude": ("#7c3aed", "C"),
    "codex": ("#0d9488", "X"),
}


def _provider_badges() -> dict[str, tuple[str, str]]:
    theme = _active_theme_key()
    return _PROVIDER_BADGES_LIGHT if theme_is_light(theme) else _PROVIDER_BADGES_DARK


def provider_badge(provider: str, *, compact: bool = False) -> str:
    """Render a provider as a colored letter (compact) or letter + name."""
    if env.no_color():
        letter = {"claude": "C", "codex": "X"}.get((provider or "").lower(), "?")
        if compact:
            return f"[bold]{letter}[/]"
        return f"[bold]{letter}[/] {provider}"
    info = _provider_badges().get((provider or "").lower())
    if info is None:
        return f"[dim]{provider or '—'}[/]"
    color, letter = info
    if compact:
        return f"[bold {color}]{letter}[/]"
    return f"[bold {color}]{letter}[/] {provider}"
