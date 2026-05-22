"""Dynamic user-facing strings.

Existing screens access this module as ``strings.KEY``. ``__getattr__`` keeps
that API while resolving values from the active runtime language.
"""

from loghop.tui.i18n import get_language, init_from_environment, set_language, tr


def __getattr__(name: str) -> str:
    return tr(name)


__all__ = ["get_language", "init_from_environment", "set_language", "tr"]
