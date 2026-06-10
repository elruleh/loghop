"""Unit tests for the declarative terminal spec launcher.

The previous implementation had nine near-duplicate functions for each
terminal. The new ``_TerminalSpec`` captures the variations as data and a
single ``build()`` method assembles the argv. These tests pin down each
terminal's expected argv so that refactors don't drift the wire format.
"""

from __future__ import annotations

import pytest

from loghop.tui.launcher import _TERMINAL_SPECS, _build_wt_exe, _TerminalSpec


@pytest.mark.parametrize(
    "name,expected_prefix",
    [
        # Native flag + native workdir flag.
        ("gnome-terminal", ["gnome-terminal", "--title", "t", "--working-directory", "/w", "--"]),
        ("xfce4-terminal", ["xfce4-terminal", "--title", "t", "--working-directory", "/w", "-x"]),
        ("tilix", ["tilix", "--title", "t", "--working-directory", "/w", "-x"]),
        ("alacritty", ["alacritty", "-t", "t", "--working-directory", "/w", "-e"]),
        # Native flag + native workdir flag (kitty uses --directory).
        ("kitty", ["kitty", "--title", "t", "--directory", "/w"]),
        # No native workdir flag -> inline cd.
        ("xterm", ["xterm", "-T", "t", "-e"]),
        # tmux subcommand.
        ("tmux", ["tmux", "-n", "t", "-c", "/w", "new-window"]),
    ],
)
def test_terminal_specs(name: str, expected_prefix: list[str]) -> None:
    spec = _TERMINAL_SPECS[name]
    args = spec.build("cmd", "/w", "t")
    # Verify the static prefix and the bash invocation at the tail.
    for prefix_part, expected_part in zip(
        args[: len(expected_prefix)], expected_prefix, strict=True
    ):
        assert prefix_part == expected_part, f"{name}: {args}"
    # bash -ic <payload> closes every spec; payload contains the user command.
    assert args[-3] == "bash"
    assert args[-2] == "-ic"
    assert "cmd" in args[-1]
    # No workdir-related leakage on specs that don't support it inline.
    if name not in {"xterm", "wezterm"}:
        assert "cd" not in args[-1] or "/w" not in args[-1]


def test_specs_with_no_workdir() -> None:
    """When workdir is None, no workdir flag is emitted."""
    args = _TERMINAL_SPECS["gnome-terminal"].build("cmd", None, "t")
    assert "--working-directory" not in args


def test_xterm_inlines_cd() -> None:
    args = _TERMINAL_SPECS["xterm"].build("cmd", "/work", "t")
    # The bash payload is a single string; workdir is inlined via `cd`.
    payload = args[-1]
    assert "/work" in payload
    assert "cmd" in payload


def test_specs_dict_includes_all_eight_tabular_emulators() -> None:
    """konsole and wt.exe keep dedicated builders; the rest go through _TerminalSpec."""
    tabular = {
        "gnome-terminal",
        "xfce4-terminal",
        "tilix",
        "alacritty",
        "kitty",
        "wezterm",
        "xterm",
        "tmux",
    }
    assert set(_TERMINAL_SPECS) == tabular


def test_build_wt_exe_uses_wsl() -> None:
    args = _build_wt_exe("cmd", None, "t")
    # wt.exe on Windows Subsystem for Linux is invoked as:
    # wt.exe -w 0 nt --title t -- wsl.exe bash <script>
    assert args[0] == "wt.exe"
    assert "wsl.exe" in args
    assert "bash" in args


def test_terminal_spec_handles_all_optional_fields() -> None:
    """A spec with no title/workdir flags and no inline workdir stays minimal."""
    spec = _TerminalSpec("x", None, None, [])
    args = spec.build("cmd", None, "t")
    assert args[0] == "x"
    assert args[-3] == "bash"


def test_terminal_spec_title_formatter() -> None:
    """title_flag supports a custom formatter callable."""
    spec = _TerminalSpec("x", ("-p", str.upper), None, [])
    args = spec.build("cmd", None, "hello")
    assert args[0] == "x"
    assert args[1] == "-p"
    assert args[2] == "HELLO"
