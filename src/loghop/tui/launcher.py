import shlex
import shutil
import subprocess  # nosec B404
from collections.abc import Callable, Sequence
from pathlib import Path

from loghop import env
from loghop.errors import E_UNKNOWN_PROVIDER, LoghopError
from loghop.logging import get_logger
from loghop.providers import SUPPORTED_PROVIDER_NAMES

_LOGGER = get_logger()


def detect_terminal_emulator() -> str | None:
    """Detect available terminal emulator on the system."""

    try:
        from loghop.install._config import _load_global_config

        config = _load_global_config()
        term_config = config.get("terminal", {})
        if "template" in term_config:
            return "custom"
        configured_term = term_config.get("emulator")
        if isinstance(configured_term, str) and configured_term.strip():
            return configured_term.strip()
    except Exception:  # noqa: BLE001
        pass

    candidates = [
        "gnome-terminal",
        "konsole",
        "xfce4-terminal",
        "alacritty",
        "kitty",
        "tilix",
        "wezterm",
        "xterm",
        "tmux",
    ]
    if env.is_wsl_windows_terminal() and shutil.which("wt.exe"):
        return "wt.exe"

    for term in candidates:
        if shutil.which(term):
            return term
    return None


def _bash_lc(cmd: str) -> list[str]:
    profile_prelude = (
        "if [ -f ~/.bash_profile ]; then . ~/.bash_profile; "
        "elif [ -f ~/.bash_login ]; then . ~/.bash_login; "
        "elif [ -f ~/.profile ]; then . ~/.profile; fi"
    )
    return ["bash", "-ic", f"{profile_prelude}; {cmd}; exec bash -l"]


class _TerminalSpec:
    """Declarative description of how a terminal emulator accepts a command.

    The previous implementation had one ~10-line function per terminal
    (gnome-terminal, konsole, xfce4-terminal, tilix, alacritty, kitty,
    wezterm, xterm, tmux). 9 functions doing roughly the same thing made
    adding a new emulator tedious and prone to drift. ``_TerminalSpec``
    captures the variations as data:

    * ``binary``  – the executable name to spawn.
    * ``title_flag`` – ``("-T", "title")`` or similar pair, with a callable
      that converts the user-facing ``title`` into the form the terminal
      expects.
    * ``workdir_arg`` – ``"--working-directory"`` style flag + value flag;
      ``None`` means the terminal does not support an explicit workdir.
    * ``exec_separator`` – argv list inserted between the terminal's own
      flags and the bash command (e.g. ``-e`` for xterm, ``-x`` for
      xfce4-terminal, or empty for terminals like tmux/wezterm).
    * ``inline_workdir`` – if True, ``cd <workdir> &&`` is prepended inside
      the bash invocation rather than passed as a separate flag (needed for
      wezterm/xterm which don't accept workdir).
    """

    __slots__ = (
        "binary",
        "title_flag",
        "workdir_arg",
        "exec_separator",
        "inline_workdir",
    )

    def __init__(
        self,
        binary: str,
        title_flag: tuple[str, Callable[[str], str]] | None,
        workdir_arg: str | None,
        exec_separator: list[str],
        *,
        inline_workdir: bool = False,
    ) -> None:
        self.binary = binary
        self.title_flag = title_flag
        self.workdir_arg = workdir_arg
        self.exec_separator = list(exec_separator)
        self.inline_workdir = inline_workdir

    def build(self, safe_cmd: str, workdir: str | None, title: str) -> list[str]:
        args: list[str] = [self.binary]
        if self.title_flag is not None:
            flag, formatter = self.title_flag
            args.extend([flag, formatter(title)])
        if workdir and self.workdir_arg:
            args.extend([self.workdir_arg, workdir])
        bash_payload = safe_cmd
        if workdir and self.inline_workdir:
            bash_payload = f"cd {shlex.quote(workdir)} && {safe_cmd}"
        args.extend(self.exec_separator)
        args.extend(_bash_lc(bash_payload))
        return args


def _format_title_kv(title: str) -> str:
    return f"tabtitle={title}"


_TERMINAL_SPECS: dict[str, _TerminalSpec] = {
    # Native flag + value, no workdir flag (uses inline cd).
    "xterm": _TerminalSpec(
        binary="xterm",
        title_flag=("-T", str),
        workdir_arg=None,
        exec_separator=["-e"],
        inline_workdir=True,
    ),
    "tmux": _TerminalSpec(
        binary="tmux",
        title_flag=("-n", str),
        workdir_arg="-c",
        exec_separator=["new-window"],
    ),
    # Native flag + value, with native workdir flag.
    "gnome-terminal": _TerminalSpec(
        binary="gnome-terminal",
        title_flag=("--title", str),
        workdir_arg="--working-directory",
        exec_separator=["--"],
    ),
    "xfce4-terminal": _TerminalSpec(
        binary="xfce4-terminal",
        title_flag=("--title", str),
        workdir_arg="--working-directory",
        exec_separator=["-x"],
    ),
    "tilix": _TerminalSpec(
        binary="tilix",
        title_flag=("--title", str),
        workdir_arg="--working-directory",
        exec_separator=["-x"],
    ),
    "alacritty": _TerminalSpec(
        binary="alacritty",
        title_flag=("-t", str),
        workdir_arg="--working-directory",
        exec_separator=["-e"],
    ),
    "kitty": _TerminalSpec(
        binary="kitty",
        title_flag=("--title", str),
        workdir_arg="--directory",
        exec_separator=[],
    ),
    # wezterm needs the workdir inlined because `cli spawn` has no flag for it.
    "wezterm": _TerminalSpec(
        binary="wezterm",
        title_flag=None,
        workdir_arg=None,
        exec_separator=["cli", "spawn", "--"],
        inline_workdir=True,
    ),
}


def _build_konsole(safe_cmd: str, workdir: str | None, title: str) -> list[str]:
    args = ["konsole", "--new-tab", "-p", f"tabtitle={title}"]
    if workdir:
        args.extend(["-p", f"Directory={workdir}"])
    args.extend(["-e", *_bash_lc(safe_cmd)])
    return args


def _build_wt_exe(safe_cmd: str, workdir: str | None, title: str) -> list[str]:
    import os
    import tempfile

    script_fd, script_path = tempfile.mkstemp(suffix=".sh", prefix="loghop_resume_")
    with os.fdopen(script_fd, "w") as f:
        f.write("#!/bin/bash -l\n")
        f.write("if [ -f ~/.profile ]; then source ~/.profile; fi\n")
        f.write("if [ -f ~/.bashrc ]; then source ~/.bashrc; fi\n")
        f.write('rm "$0"\n')
        if workdir:
            f.write(f"cd {shlex.quote(workdir)}\n")
        f.write(f"{safe_cmd}\n")
        f.write("exec bash -l\n")
    os.chmod(script_path, 0o700)
    return ["wt.exe", "-w", "0", "nt", "--title", title, "--", "wsl.exe", "bash", script_path]


_TERMINAL_BUILDERS: dict[str, object] = {
    "gnome-terminal": _TERMINAL_SPECS["gnome-terminal"].build,
    "konsole": _build_konsole,  # uses key=value, keep dedicated
    "xfce4-terminal": _TERMINAL_SPECS["xfce4-terminal"].build,
    "tilix": _TERMINAL_SPECS["tilix"].build,
    "alacritty": _TERMINAL_SPECS["alacritty"].build,
    "kitty": _TERMINAL_SPECS["kitty"].build,
    "wezterm": _TERMINAL_SPECS["wezterm"].build,
    "xterm": _TERMINAL_SPECS["xterm"].build,
    "tmux": _TERMINAL_SPECS["tmux"].build,
    "wt.exe": _build_wt_exe,
}


def launch_in_new_tab(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    title: str = "loghop",
) -> bool:
    """Launch a command in a new terminal tab/window.

    Returns True if launch was attempted successfully.
    """
    safe_cmd = shlex.join(argv)
    term = detect_terminal_emulator()
    if term is None:
        _LOGGER.warning(
            "no terminal emulator detected; cannot launch command",
            extra={"component": "launcher", "command": safe_cmd},
        )
        return False

    workdir = str(cwd) if cwd else None

    # Load custom template if available
    template = None
    try:
        from loghop.install._config import _load_global_config

        config = _load_global_config()
        term_config = config.get("terminal", {})
        template = term_config.get("template")
    except Exception:  # noqa: BLE001
        pass

    if template:
        if isinstance(template, str):
            template_args = shlex.split(template)
        elif isinstance(template, list):
            template_args = [str(x) for x in template]
        else:
            template_args = []

        if template_args:
            bash_cmd_list = _bash_lc(safe_cmd)
            args = []
            for arg in template_args:
                if arg == "{bash_command}":
                    args.extend(bash_cmd_list)
                else:
                    val = arg.replace("{title}", title)
                    val = val.replace("{workdir}", workdir or str(Path.cwd()))
                    val = val.replace("{command}", safe_cmd)
                    args.append(val)
        else:
            _LOGGER.warning(
                "custom terminal template is empty",
                extra={"component": "launcher"},
            )
            return False
    else:
        builder = _TERMINAL_BUILDERS.get(term)
        if builder is None:
            # Fallback to generic builder for custom emulators with no builder
            _LOGGER.info(
                "no custom builder for %s, falling back to generic execution",
                term,
                extra={"component": "launcher", "terminal": term},
            )
            args = [term, "-e"] + _bash_lc(safe_cmd)
        else:
            args = builder(safe_cmd, workdir, title)  # type: ignore[operator]

    try:
        subprocess.Popen(args, start_new_session=True)  # nosec B603
    except OSError as exc:
        _LOGGER.warning(
            "failed to launch terminal command",
            extra={"component": "launcher", "terminal": term, "error": str(exc)},
        )
        return False
    else:
        return True


def build_resume_command(
    project_path: Path,
    provider: str,
    *,
    interactive: bool = False,
) -> list[str]:
    """Build the loghop run argv for a project.

    The provider is validated against the supported allowlist as a
    defense-in-depth check (it should already be validated upstream).
    """
    import sys

    if provider not in SUPPORTED_PROVIDER_NAMES:
        raise LoghopError(f"unsupported provider: {provider}", code=E_UNKNOWN_PROVIDER)

    parts = [
        sys.executable,
        "-m",
        "loghop",
        "run",
        str(project_path),
        "--provider",
        provider,
    ]
    if interactive:
        parts.append("--interactive")
    return parts


def build_wrap_command(
    project_path: str,
    provider: str,
) -> str:
    """Build the loghop wrap command string with shell-safe quoting."""
    import sys

    if provider not in SUPPORTED_PROVIDER_NAMES:
        raise ValueError(f"unsupported provider: {provider}")

    return (
        f"cd {shlex.quote(project_path)} && "
        f"{shlex.quote(sys.executable)} -m loghop wrap {shlex.quote(provider)}"
    )
