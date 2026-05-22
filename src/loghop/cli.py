import argparse
import contextlib
import importlib.util
import json
import signal
import sys
from collections.abc import Sequence
from pathlib import Path

from loghop import __version__
from loghop.cli_commands._dashboard_no_args import handle_dashboard_no_args
from loghop.cli_commands._helpers import LOGGER
from loghop.cli_parser import _ParseError, build_parser
from loghop.errors import E_INVALID_INPUT, E_TIMEOUT, E_UNEXPECTED, LoghopError
from loghop.logging import configure_project_logging
from loghop.store import find_project_root

__all__ = ["build_parser", "cli_main", "main"]


def _install_sigterm_handler() -> None:
    def _to_interrupt(_signum: int, _frame: object) -> None:  # pragma: no cover
        raise KeyboardInterrupt

    with contextlib.suppress(ValueError, OSError):
        signal.signal(signal.SIGTERM, _to_interrupt)


def _render_parse_error_json(message: str) -> None:
    payload = {
        "schema": "loghop.cli.result",
        "schema_version": 1,
        "ok": False,
        "code": 2,
        "error": message,
        "error_code": "E_INVALID_INPUT",
        "events": [{"type": "error", "text": message, "error": True}],
        "result": {"error": message, "error_code": "E_INVALID_INPUT"},
    }
    print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stdout)  # noqa: T201


_GLOBAL_FLAGS = {"--json", "--plain", "--quiet", "--verbose", "--version", "--global"}
_MIN_PYTHON = (3, 12)


def _check_python_version() -> int | None:
    if sys.version_info < _MIN_PYTHON:
        running = ".".join(str(p) for p in sys.version_info[:3])
        required = ".".join(str(p) for p in _MIN_PYTHON)
        msg = (
            f"loghop requires Python {required}+ (running {running}). "
            "Install with `pipx install --python python3.12 loghop` "
            "or `uv tool install loghop`."
        )
        print(msg, file=sys.stderr)  # noqa: T201
        return 1
    return None


def cli_main() -> None:
    rc = _check_python_version()
    if rc is not None:
        raise SystemExit(rc)
    raise SystemExit(main())


def main(argv: Sequence[str] | None = None) -> int:
    rc = _check_python_version()
    if rc is not None:
        return rc
    parser = build_parser()
    raw_argv = _normalize_argv(list(argv) if argv is not None else sys.argv[1:])
    try:
        args = parser.parse_args(raw_argv)
    except _ParseError as exc:
        if "--json" in raw_argv:
            _render_parse_error_json(exc.message)
            return 2
        exc.parser.print_usage(sys.stderr)
        print(f"{exc.parser.prog}: error: {exc.message}", file=sys.stderr)  # noqa: T201
        return 2
    if getattr(args, "version", False):
        print(f"loghop {__version__}")  # noqa: T201
        return 0
    if not getattr(args, "handler", None):
        if args.json:
            _render_parse_error_json("no command provided")
            return 2
        if _should_open_tui_by_default(args):
            from loghop.cli_commands.tui import handle_tui

            args.command = "tui"
            args.handler = handle_tui
            args.global_view = getattr(args, "global_view", False)
            args.implicit_tui = True
        else:
            return handle_dashboard_no_args(args)
    return _run_command(args, raw_argv)


def _normalize_argv(argv: list[str]) -> list[str]:
    command_index = next((i for i, arg in enumerate(argv) if arg not in _GLOBAL_FLAGS), None)
    if command_index is not None and argv[command_index] == "wrap":
        prefix = argv[:command_index]
        globals_found = [arg for arg in prefix if arg in _GLOBAL_FLAGS]
        others = [arg for arg in prefix if arg not in _GLOBAL_FLAGS]
        return [*globals_found, *others, *argv[command_index:]]
    globals_found = [arg for arg in argv if arg in _GLOBAL_FLAGS]
    others = [arg for arg in argv if arg not in _GLOBAL_FLAGS]
    return [*globals_found, *others]


def _run_command(args: argparse.Namespace, raw_argv: list[str]) -> int:
    from loghop.terminal import Terminal, TerminalOptions

    term = Terminal(
        TerminalOptions(
            plain=args.plain, quiet=args.quiet, verbose=args.verbose, json_mode=args.json
        )
    )
    cwd = Path.cwd()
    project_root = find_project_root(cwd)
    try:
        configure_project_logging(project_root)
        _install_sigterm_handler()
        from loghop.reconcile import auto_reconcile_silent

        auto_reconcile_silent(project_root)
    except (OSError, ValueError, TimeoutError) as exc:
        term.error(str(exc))
        term.capture_result({"error": str(exc), "error_code": E_UNEXPECTED})
        if args.json:
            term.render_json(code=1)
        return 1
    command = _command_name(args)
    LOGGER.info(
        "command start",
        extra={"component": "cli", "command": command, "cwd": str(cwd), "json_mode": args.json},
    )
    try:
        code = args.handler(args, term)
    except KeyboardInterrupt:
        LOGGER.info(
            "command interrupted",
            extra={"component": "cli", "command": command, "cwd": str(cwd)},
        )
        term.error("interrupted")
        term.capture_result({"error": "interrupted", "error_code": E_UNEXPECTED})
        code = 130
    except LoghopError as exc:
        if (
            getattr(args, "implicit_tui", False)
            and exc.code == E_INVALID_INPUT
            and "textual is not installed" in str(exc).lower()
        ):
            return handle_dashboard_no_args(args)
        LOGGER.warning(
            "command failed",
            extra={
                "component": "cli",
                "command": command,
                "cwd": str(cwd),
                "error": str(exc),
                "error_code": exc.code,
            },
        )
        term.error(str(exc))
        term.capture_result({"error": str(exc), "error_code": exc.code})
        code = exc.exit_code
    except ValueError as exc:
        LOGGER.warning(
            "command failed",
            extra={"component": "cli", "command": command, "cwd": str(cwd), "error": str(exc)},
        )
        term.error(str(exc))
        term.capture_result({"error": str(exc)})
        code = 2
    except TimeoutError as exc:
        LOGGER.warning(
            "command timed out",
            extra={"component": "cli", "command": command, "cwd": str(cwd), "error": str(exc)},
        )
        term.error(str(exc))
        term.capture_result({"error": str(exc), "error_code": E_TIMEOUT})
        code = 3
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception(
            "command error",
            extra={"component": "cli", "command": command, "cwd": str(cwd)},
        )
        term.error("unexpected error. See log for details (~/.loghop/logs/ or run with --verbose).")
        term.capture_result({"error": type(exc).__name__, "error_code": E_UNEXPECTED})
        code = 1
    LOGGER.info(
        "command finish",
        extra={"component": "cli", "command": command, "cwd": str(cwd), "code": code},
    )
    if args.json:
        term.render_json(code=code)
    return int(code)


def _should_open_tui_by_default(args: object) -> bool:
    if (
        getattr(args, "plain", False)
        or getattr(args, "quiet", False)
        or getattr(args, "verbose", False)
    ):
        return False
    if not _textual_available():
        return False
    try:
        return bool(sys.stdout.isatty() and sys.stdin.isatty())
    except OSError:
        return False


def _textual_available() -> bool:
    try:
        return importlib.util.find_spec("textual") is not None
    except (ImportError, ValueError):
        return False


def _command_name(args: object) -> str:
    parts = [str(getattr(args, "command", "") or "")]
    for attr in ("providers_command", "handoff_command", "sessions_command", "projects_command"):
        value = getattr(args, attr, "")
        if value:
            parts.append(str(value))
    return " ".join(part for part in parts if part)
