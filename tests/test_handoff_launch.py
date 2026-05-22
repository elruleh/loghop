"""Unit tests for _handoff_launch module.

Covers: _reject_unsupported_interactive_api_transport, _chdir_to_target,
_fresh_prompt, _resume_prompt.
"""

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from loghop.errors import E_INVALID_INPUT, LoghopError
from loghop.terminal import Terminal


def _term() -> Terminal:
    term = MagicMock(spec=Terminal)
    term.json_mode = False
    return term


class TestRejectUnsupportedInteractiveApiTransport:
    """_reject_unsupported_interactive_api_transport should block claude+interactive+api."""

    def test_non_claude_passes(self) -> None:
        from loghop.cli_commands._handoff_launch import (
            _reject_unsupported_interactive_api_transport,
        )

        _reject_unsupported_interactive_api_transport("codex", Path("/tmp"), interactive=True)

    def test_non_interactive_passes(self, tmp_path: Path) -> None:
        from loghop.cli_commands._handoff_launch import (
            _reject_unsupported_interactive_api_transport,
        )

        _reject_unsupported_interactive_api_transport("claude", tmp_path, interactive=False)

    def test_interactive_without_api_passes(self, tmp_path: Path) -> None:
        from loghop.cli_commands._handoff_launch import (
            _reject_unsupported_interactive_api_transport,
        )

        with patch(
            "loghop.cli_commands._handoff_launch.claude_uses_api_transport",
            return_value=False,
        ):
            _reject_unsupported_interactive_api_transport("claude", tmp_path, interactive=True)

    def test_interactive_with_api_raises(self, tmp_path: Path) -> None:
        from loghop.cli_commands._handoff_launch import (
            _reject_unsupported_interactive_api_transport,
        )

        with patch(
            "loghop.cli_commands._handoff_launch.claude_uses_api_transport",
            return_value=True,
        ):
            with pytest.raises(LoghopError, match="interactive sessions") as exc_info:
                _reject_unsupported_interactive_api_transport("claude", tmp_path, interactive=True)
            assert exc_info.value.code == E_INVALID_INPUT


class TestChdirToTarget:
    """_chdir_to_target should resolve project target or raise."""

    def test_no_target_does_nothing(self) -> None:
        from loghop.cli_commands._handoff_launch import _chdir_to_target

        args = argparse.Namespace(target=None)
        term = _term()
        _chdir_to_target(args, term, command="run")

    def test_valid_target_changes_dir(self, tmp_path: Path) -> None:
        from loghop.cli_commands._handoff_launch import _chdir_to_target

        args = argparse.Namespace(target="my-project")
        term = _term()
        with patch(
            "loghop.cli_commands._handoff_launch.resolve_project_target",
            return_value=tmp_path,
        ):
            _chdir_to_target(args, term, command="run")
        cast(Any, term).info.assert_called_once()

    def test_invalid_target_raises(self) -> None:
        from loghop.cli_commands._handoff_launch import _chdir_to_target

        args = argparse.Namespace(target="nonexistent")
        term = _term()
        with (
            patch(
                "loghop.cli_commands._handoff_launch.resolve_project_target",
                return_value=None,
            ),
            pytest.raises(LoghopError, match="no registered project"),
        ):
            _chdir_to_target(args, term, command="run")


class TestFreshPrompt:
    """_fresh_prompt should include goal and handoff reference."""

    def test_with_handoff_path(self) -> None:
        from loghop.cli_commands._handoff_launch import _fresh_prompt

        result = _fresh_prompt("Fix the bug", Path(".loghop/handoffs/H-1.md"))
        assert "Fix the bug" in result
        assert ".loghop/handoffs/H-1.md" in result
        assert "handoff file" in result.lower()

    def test_without_handoff_path(self) -> None:
        from loghop.cli_commands._handoff_launch import _fresh_prompt

        result = _fresh_prompt("Do stuff", None)
        assert "Do stuff" in result


class TestResumePrompt:
    """_resume_prompt should include goal and continuity instructions."""

    def test_with_handoff_path(self) -> None:
        from loghop.cli_commands._handoff_launch import _resume_prompt

        result = _resume_prompt("Continue feature", Path(".loghop/handoffs/H-5.md"))
        assert "Continue feature" in result
        assert ".loghop/handoffs/H-5.md" in result
        assert "continue" in result.lower()

    def test_without_handoff_path(self) -> None:
        from loghop.cli_commands._handoff_launch import _resume_prompt

        result = _resume_prompt("Keep going", None)
        assert "Keep going" in result


class TestLaunchHandoffSession:
    def test_resume_without_previous_session_starts_fresh(self, tmp_path: Path) -> None:
        from loghop.cli_commands._handoff_launch import launch_handoff_session

        term = _term()
        args = argparse.Namespace(provider="codex", goal="next", interactive=False, timeout=30)
        paths = SimpleNamespace()
        fresh_record = SimpleNamespace(
            id="H-001", md_path=tmp_path / ".loghop" / "handoffs" / "H-001.md"
        )
        session = SimpleNamespace(id="S-001")

        with (
            patch("loghop.cli_commands._handoff_launch.require_project_config") as require_config,
            patch(
                "loghop.cli_commands._handoff_launch.resolve_default_provider", return_value="codex"
            ),
            patch("loghop.cli_commands._handoff_launch.require_provider_arg", return_value="codex"),
            patch(
                "loghop.cli_commands._handoff_launch.resolve_goal_or_default", return_value="next"
            ),
            patch(
                "loghop.cli_commands._handoff_launch.resolve_enabled_provider",
                return_value="/usr/bin/codex",
            ),
            patch(
                "loghop.cli_commands._handoff_launch._reject_unsupported_interactive_api_transport"
            ),
            patch("loghop.cli_commands._handoff_launch._preflight_provider_readiness"),
            patch("loghop.cli_commands._handoff_launch.auto_reconcile_silent"),
            patch("loghop.cli_commands._handoff_launch.latest_useful_session", return_value=None),
            patch(
                "loghop.cli_commands._handoff_launch.create_handoff", return_value=fresh_record
            ) as create_handoff,
            patch(
                "loghop.cli_commands._handoff_launch.create_resume_handoff"
            ) as create_resume_handoff,
            patch("loghop.cli_commands._handoff_launch.create_session", return_value=session),
            patch(
                "loghop.cli_commands._handoff_launch.run_provider_session", return_value=0
            ) as run_provider,
        ):
            require_config.return_value = (tmp_path, paths, {"default_goal": "next"})
            rc = launch_handoff_session(args, term, mode="resume", command="resume")

        assert rc == 0
        create_handoff.assert_called_once_with(tmp_path, "codex", "next")
        create_resume_handoff.assert_not_called()
        run_provider.assert_called_once()
        cast(Any, term).info.assert_any_call("Starting from session none")
