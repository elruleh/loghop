import argparse

from loghop.errors import E_INVALID_INPUT, LoghopError
from loghop.terminal import Terminal

_TUI_INSTALL_HINT = (
    "Textual is not installed. Install the optional TUI with `pipx install "
    "'loghop[tui]'` or `uv tool install 'loghop[tui]'`."
)


def handle_tui(args: argparse.Namespace, term: Terminal) -> int:
    if term.json_mode:
        raise LoghopError("`loghop tui` does not support `--json`.", code=E_INVALID_INPUT)

    try:
        from loghop.tui.app import run
    except ModuleNotFoundError as exc:
        if exc.name != "textual" and not str(exc.name).startswith("textual."):
            raise
        raise LoghopError(_TUI_INSTALL_HINT, code=E_INVALID_INPUT) from exc

    try:
        return run(
            global_view=bool(getattr(args, "global_view", False)),
            tui_debug=bool(getattr(args, "tui_debug", False)),
        )
    except RuntimeError as exc:
        if "textual" not in str(exc).lower():
            raise
        raise LoghopError(_TUI_INSTALL_HINT, code=E_INVALID_INPUT) from exc
