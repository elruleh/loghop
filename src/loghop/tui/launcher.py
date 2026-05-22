import shlex
import shutil
import subprocess  # nosec B404
from collections.abc import Sequence
from pathlib import Path

from loghop import env
from loghop.errors import E_UNKNOWN_PROVIDER, LoghopError
from loghop.logging import get_logger
from loghop.providers import SUPPORTED_PROVIDER_NAMES

_LOGGER = get_logger()


def detect_terminal_emulator() -> str | None:
    """Detect available terminal emulator on the system."""

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


def _build_gnome_terminal(safe_cmd: str, workdir: str | None, title: str) -> list[str]:
    args = ["gnome-terminal", "--title", title]
    if workdir:
        args.extend(["--working-directory", workdir])
    args.extend(["--", *_bash_lc(safe_cmd)])
    return args


def _build_konsole(safe_cmd: str, workdir: str | None, title: str) -> list[str]:
    args = ["konsole", "--new-tab", "-p", f"tabtitle={title}"]
    if workdir:
        args.extend(["-p", f"Directory={workdir}"])
    args.extend(["-e", *_bash_lc(safe_cmd)])
    return args


def _build_xfce4_terminal(safe_cmd: str, workdir: str | None, title: str) -> list[str]:
    args = ["xfce4-terminal", "--title", title]
    if workdir:
        args.extend(["--working-directory", workdir])
    args.extend(["-x", *_bash_lc(safe_cmd)])
    return args


def _build_tilix(safe_cmd: str, workdir: str | None, title: str) -> list[str]:
    args = ["tilix", "--title", title]
    if workdir:
        args.extend(["--working-directory", workdir])
    args.extend(["-x", *_bash_lc(safe_cmd)])
    return args


def _build_alacritty(safe_cmd: str, workdir: str | None, title: str) -> list[str]:
    args = ["alacritty", "-t", title]
    if workdir:
        args.extend(["--working-directory", workdir])
    args.extend(["-e", *_bash_lc(safe_cmd)])
    return args


def _build_kitty(safe_cmd: str, workdir: str | None, title: str) -> list[str]:
    args = ["kitty", "--title", title]
    if workdir:
        args.extend(["--directory", workdir])
    args.extend(_bash_lc(safe_cmd))
    return args


def _build_wezterm(safe_cmd: str, workdir: str | None, title: str) -> list[str]:
    args = ["wezterm", "cli", "spawn", "--"]
    if workdir:
        args.extend(_bash_lc(f"cd {shlex.quote(workdir)} && {safe_cmd}"))
    else:
        args.extend(_bash_lc(safe_cmd))
    return args


def _build_xterm(safe_cmd: str, workdir: str | None, title: str) -> list[str]:
    args = ["xterm", "-T", title]
    if workdir:
        args.extend(["-e", *_bash_lc(f"cd {shlex.quote(workdir)} && {safe_cmd}")])
    else:
        args.extend(["-e", *_bash_lc(safe_cmd)])
    return args


def _build_tmux(safe_cmd: str, workdir: str | None, title: str) -> list[str]:
    args = ["tmux", "new-window", "-n", title]
    if workdir:
        args.extend(["-c", workdir])
    args.extend(_bash_lc(safe_cmd))
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
    "gnome-terminal": _build_gnome_terminal,
    "konsole": _build_konsole,
    "xfce4-terminal": _build_xfce4_terminal,
    "tilix": _build_tilix,
    "alacritty": _build_alacritty,
    "kitty": _build_kitty,
    "wezterm": _build_wezterm,
    "xterm": _build_xterm,
    "tmux": _build_tmux,
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

    builder = _TERMINAL_BUILDERS.get(term)
    if builder is None:
        _LOGGER.warning(
            "detected terminal %s has no launcher builder",
            extra={"component": "launcher", "terminal": term},
        )
        return False

    workdir = str(cwd) if cwd else None
    args = builder(safe_cmd, workdir, title)  # type: ignore[operator]  # builder is narrowed by runtime terminal capability dispatch

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
