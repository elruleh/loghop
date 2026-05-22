"""Tests for tui/launcher.py — detect_terminal_emulator, launch_in_new_tab, build commands."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from loghop.tui.launcher import (
    _bash_lc,
    build_resume_command,
    build_wrap_command,
    detect_terminal_emulator,
    launch_in_new_tab,
)


class TestDetectTerminalEmulator:
    def test_returns_none_when_nothing_available(self) -> None:
        with (
            patch("loghop.tui.launcher.shutil.which", return_value=None),
            patch.dict(os.environ, {}, clear=True),
        ):
            assert detect_terminal_emulator() is None

    def test_returns_wt_exe_when_wsl_windows_terminal(self) -> None:
        with (
            patch.dict(os.environ, {"WT_SESSION": "1"}, clear=False),
            patch("loghop.tui.launcher.shutil.which", return_value="/usr/bin/wt.exe"),
        ):
            assert detect_terminal_emulator() == "wt.exe"

    def test_returns_first_found_candidate(self) -> None:
        def fake_which(name: str) -> str | None:
            return "/usr/bin/kitty" if name == "kitty" else None

        with (
            patch("loghop.tui.launcher.shutil.which", side_effect=fake_which),
            patch.dict(os.environ, {}, clear=True),
        ):
            assert detect_terminal_emulator() == "kitty"

    def test_wt_exe_not_returned_when_which_fails(self) -> None:
        with (
            patch.dict(os.environ, {"WT_SESSION": "1"}, clear=False),
            patch("loghop.tui.launcher.shutil.which", return_value=None),
        ):
            assert detect_terminal_emulator() is None


class TestLaunchInNewTab:
    def _launch(self, term_name: str, **kwargs: object) -> list[str]:
        mock_popen = MagicMock()
        with (
            patch("loghop.tui.launcher.detect_terminal_emulator", return_value=term_name),
            patch("loghop.tui.launcher.subprocess.Popen", mock_popen),
        ):
            result = launch_in_new_tab(["echo", "hi"], **kwargs)  # type: ignore[arg-type]
        assert result is True
        return list(mock_popen.call_args[0][0])

    def test_returns_false_when_no_terminal(self) -> None:
        with patch("loghop.tui.launcher.detect_terminal_emulator", return_value=None):
            assert launch_in_new_tab(["echo", "hi"]) is False

    def test_returns_false_on_oserror(self) -> None:
        with (
            patch("loghop.tui.launcher.detect_terminal_emulator", return_value="gnome-terminal"),
            patch("loghop.tui.launcher.subprocess.Popen", side_effect=OSError("nope")),
        ):
            assert launch_in_new_tab(["echo"]) is False

    def test_unknown_terminal_returns_false(self) -> None:
        with patch("loghop.tui.launcher.detect_terminal_emulator", return_value="unknown-term"):
            assert launch_in_new_tab(["echo"]) is False

    def test_safe_command_quoting_with_special_chars(self) -> None:
        args = self._launch("gnome-terminal")
        bash_cmd = args[-1]
        assert "echo" in bash_cmd

    def test_shell_loads_user_profile_before_launch(self) -> None:
        args = self._launch("gnome-terminal")
        assert "-ic" in args
        bash_cmd = args[-1]
        assert ".bash_profile" in bash_cmd
        assert ".profile" in bash_cmd

    def test_gnome_terminal_no_cwd(self) -> None:
        args = self._launch("gnome-terminal")
        assert args[0] == "gnome-terminal"
        assert "--working-directory" not in args

    def test_gnome_terminal_with_cwd(self) -> None:
        args = self._launch("gnome-terminal", cwd=Path("/tmp"))
        assert "--working-directory" in args

    def test_konsole_with_cwd(self) -> None:
        args = self._launch("konsole", cwd=Path("/tmp"))
        assert args[0] == "konsole"
        assert "--new-tab" in args
        assert any("Directory=" in a for a in args)

    def test_konsole_no_cwd(self) -> None:
        args = self._launch("konsole")
        assert not any("Directory=" in a for a in args)

    def test_xfce4_terminal_with_cwd(self) -> None:
        args = self._launch("xfce4-terminal", cwd=Path("/tmp"))
        assert args[0] == "xfce4-terminal"
        assert "--working-directory" in args
        assert "-x" in args

    def test_tilix_with_cwd(self) -> None:
        args = self._launch("tilix", cwd=Path("/tmp"))
        assert args[0] == "tilix"
        assert "--working-directory" in args
        assert "-x" in args

    def test_alacritty_with_cwd(self) -> None:
        args = self._launch("alacritty", cwd=Path("/tmp"))
        assert args[0] == "alacritty"
        assert "-t" in args
        assert "--working-directory" in args
        assert "-e" in args

    def test_kitty_with_cwd(self) -> None:
        args = self._launch("kitty", cwd=Path("/tmp"))
        assert args[0] == "kitty"
        assert "--title" in args
        assert "--directory" in args

    def test_kitty_no_cwd(self) -> None:
        args = self._launch("kitty")
        assert "--directory" not in args

    def test_wezterm_with_cwd(self) -> None:
        args = self._launch("wezterm", cwd=Path("/tmp"))
        assert args[0] == "wezterm"
        assert "cli" in args
        assert "spawn" in args
        bash_cmd = args[-1]
        assert "cd " in bash_cmd

    def test_wezterm_no_cwd(self) -> None:
        args = self._launch("wezterm")
        bash_cmd = args[-1]
        assert "echo" in bash_cmd

    def test_xterm_with_cwd(self) -> None:
        args = self._launch("xterm", cwd=Path("/tmp"))
        assert args[0] == "xterm"
        assert "-T" in args
        bash_cmd = args[-1]
        assert "cd " in bash_cmd

    def test_xterm_no_cwd(self) -> None:
        args = self._launch("xterm")
        bash_cmd = args[-1]
        assert "echo" in bash_cmd
        assert "cd " not in bash_cmd

    def test_tmux_with_cwd(self) -> None:
        args = self._launch("tmux", cwd=Path("/tmp"))
        assert args[0] == "tmux"
        assert "new-window" in args
        assert "-c" in args

    def test_tmux_no_cwd(self) -> None:
        args = self._launch("tmux")
        assert "-c" not in args

    def test_wt_exe_creates_script(self) -> None:
        mock_popen = MagicMock()
        with (
            patch("loghop.tui.launcher.detect_terminal_emulator", return_value="wt.exe"),
            patch("loghop.tui.launcher.subprocess.Popen", mock_popen),
        ):
            result = launch_in_new_tab(["echo", "hi"])
        assert result is True
        args = mock_popen.call_args[0][0]
        assert "wt.exe" in args
        assert "wsl.exe" in args

    def test_wt_exe_script_no_provider_env_leak(self) -> None:
        mock_popen = MagicMock()
        with (
            patch.dict(
                os.environ,
                {
                    "ANTHROPIC_API_KEY": "sk-test-key-123",
                    "ANTHROPIC_AUTH_TOKEN": "tok-abc",
                    "CLAUDE_CODE_FOO": "bar",
                    "HOME": "/tmp",
                    "PATH": "/usr/bin",
                },
                clear=True,
            ),
            patch("loghop.tui.launcher.detect_terminal_emulator", return_value="wt.exe"),
            patch("loghop.tui.launcher.subprocess.Popen", mock_popen),
        ):
            launch_in_new_tab(["echo", "hi"])

        args = mock_popen.call_args[0][0]
        script_path = args[-1]
        try:
            script = Path(script_path).read_text()
        finally:
            Path(script_path).unlink(missing_ok=True)

        assert "export ANTHROPIC_" not in script
        assert "export CLAUDE_CODE_" not in script

    def test_wt_exe_with_cwd(self) -> None:
        mock_popen = MagicMock()
        with (
            patch("loghop.tui.launcher.detect_terminal_emulator", return_value="wt.exe"),
            patch("loghop.tui.launcher.subprocess.Popen", mock_popen),
        ):
            result = launch_in_new_tab(["echo", "hi"], cwd=Path("/tmp"))
        assert result is True

    def test_start_new_session_used(self) -> None:
        mock_popen = MagicMock()
        with (
            patch("loghop.tui.launcher.detect_terminal_emulator", return_value="gnome-terminal"),
            patch("loghop.tui.launcher.subprocess.Popen", mock_popen),
        ):
            launch_in_new_tab(["echo"])
        assert mock_popen.call_args[1].get("start_new_session") is True


class TestBuildResumeCommand:
    def test_returns_argv_list(self) -> None:
        argv = build_resume_command(Path("/tmp/project"), "claude")
        assert isinstance(argv, list)
        assert "run" in argv
        assert "/tmp/project" in argv
        assert "--provider" in argv
        assert "claude" in argv

    def test_interactive_flag(self) -> None:
        argv = build_resume_command(Path("/tmp/x"), "codex", interactive=True)
        assert argv[-1] == "--interactive"

    def test_non_interactive_no_flag(self) -> None:
        argv = build_resume_command(Path("/tmp/p"), "claude", interactive=False)
        assert "--interactive" not in argv

    def test_contains_sys_executable(self) -> None:
        import sys

        argv = build_resume_command(Path("/tmp/p"), "claude")
        assert argv[0] == sys.executable

    def test_rejects_unknown_provider(self) -> None:
        with pytest.raises(Exception, match="unsupported provider"):
            build_resume_command(Path("/tmp/x"), "evil")


class TestBuildWrapCommand:
    def test_produces_shell_safe_string(self) -> None:
        cmd = build_wrap_command("/tmp/project", "codex")
        assert "cd" in cmd
        assert "&&" in cmd
        assert "codex" in cmd

    def test_rejects_unknown_provider(self) -> None:
        with pytest.raises(ValueError, match="unsupported provider"):
            build_wrap_command("/tmp/x", "notreal")

    def test_quotes_path_with_spaces(self) -> None:
        cmd = build_wrap_command("/tmp/my project", "codex")
        assert "'" in cmd or '"' in cmd

    def test_contains_cd_and_wrap(self) -> None:
        cmd = build_wrap_command("/tmp/p", "claude")
        assert cmd.startswith("cd ")
        assert "wrap" in cmd


class TestBashLc:
    def test_includes_profile_prelude(self) -> None:
        result = _bash_lc("echo hi")
        assert result[0] == "bash"
        assert result[1] == "-ic"
        assert ".bash_profile" in result[2]

    def test_ends_with_command_and_exec(self) -> None:
        result = _bash_lc("my-cmd")
        assert "my-cmd" in result[-1]
        assert "exec bash -l" in result[-1]


class TestDetectTerminalPriority:
    def test_gnome_before_konsole(self) -> None:
        found = {"gnome-terminal": "/usr/bin/gnome-terminal", "konsole": "/usr/bin/konsole"}

        def fake_which(name: str) -> str | None:
            return found.get(name)

        with (
            patch("loghop.tui.launcher.shutil.which", side_effect=fake_which),
            patch.dict(os.environ, {}, clear=True),
        ):
            assert detect_terminal_emulator() == "gnome-terminal"

    def test_candidates_scanned_in_order(self) -> None:
        from loghop.tui.launcher import detect_terminal_emulator

        last_checked: list[str] = []

        def fake_which(name: str) -> str | None:
            last_checked.append(name)
            return None

        with (
            patch("loghop.tui.launcher.shutil.which", side_effect=fake_which),
            patch.dict(os.environ, {}, clear=True),
        ):
            detect_terminal_emulator()
        assert last_checked.index("gnome-terminal") < last_checked.index("konsole")
