"""Tests for run_provider_session error paths in _runner.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest
from conftest import init_repo

from loghop.cli_commands._runner import run_provider_session
from loghop.errors import LoghopError
from loghop.store import project_paths
from loghop.store._handoff import create_handoff
from loghop.store._session import create_session, find_session
from loghop.terminal import Terminal, TerminalOptions


def _plain_term() -> Terminal:
    import io

    return Terminal(TerminalOptions(plain=True, stream=io.StringIO(), error_stream=io.StringIO()))


class TestRunProviderSessionOsError:
    def test_oserror_sets_session_launch_failed(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="codex", goal="g")
        handoff = create_handoff(root, "codex", "g")
        term = _plain_term()

        with (
            patch(
                "loghop.cli_commands._runner.build_launch_command",
                return_value=["nonexistent-binary"],
            ),
            patch(
                "loghop.cli_commands._runner.subprocess.run",
                side_effect=OSError("no such file"),
            ),
            pytest.raises(LoghopError, match="failed to launch"),
        ):
            run_provider_session(
                root, "codex", "nonexistent-binary", session.id, handoff.id, "prompt", term
            )

        meta = find_session(project_paths(root), session.id)
        assert meta.status == "launch_failed"

    def test_oserror_without_handoff_id(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="codex", goal="g")
        term = _plain_term()

        with (
            patch(
                "loghop.cli_commands._runner.build_launch_command",
                return_value=["nonexistent-binary"],
            ),
            patch(
                "loghop.cli_commands._runner.subprocess.run",
                side_effect=OSError("no such file"),
            ),
            pytest.raises(LoghopError),
        ):
            run_provider_session(
                root, "codex", "nonexistent-binary", session.id, "", "prompt", term
            )

        meta = find_session(project_paths(root), session.id)
        assert meta.status == "launch_failed"


class TestRunProviderSessionTimeout:
    def test_timeout_sets_session_timed_out(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="codex", goal="g")
        handoff = create_handoff(root, "codex", "g")
        term = _plain_term()

        with (
            patch("loghop.cli_commands._runner.build_launch_command", return_value=["sleep", "60"]),
            patch(
                "loghop.cli_commands._runner.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=["sleep", "60"], timeout=1),
            ),
            pytest.raises(LoghopError, match="timed out"),
        ):
            run_provider_session(
                root,
                "codex",
                "sleep",
                session.id,
                handoff.id,
                "prompt",
                term,
                timeout=1,
            )

        meta = find_session(project_paths(root), session.id)
        assert meta.status == "timed_out"


class TestRunProviderSessionNonZeroExit:
    def test_nonzero_exit_sets_session_failed_and_returns_10(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="codex", goal="g")
        handoff = create_handoff(root, "codex", "g")
        term = _plain_term()

        fake_result = subprocess.CompletedProcess(
            args=["codex"], returncode=1, stdout="error output", stderr="err"
        )
        with (
            patch("loghop.cli_commands._runner.build_launch_command", return_value=["codex"]),
            patch("loghop.cli_commands._runner.subprocess.run", return_value=fake_result),
        ):
            code = run_provider_session(
                root, "codex", "codex", session.id, handoff.id, "prompt", term
            )

        assert code == 10
        meta = find_session(project_paths(root), session.id)
        assert meta.status == "failed"

    def test_nonzero_exit_without_handoff_id(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="codex", goal="g")
        term = _plain_term()

        fake_result = subprocess.CompletedProcess(
            args=["codex"], returncode=2, stdout="", stderr=""
        )
        with (
            patch("loghop.cli_commands._runner.build_launch_command", return_value=["codex"]),
            patch("loghop.cli_commands._runner.subprocess.run", return_value=fake_result),
        ):
            code = run_provider_session(root, "codex", "codex", session.id, "", "prompt", term)

        assert code == 10
        meta = find_session(project_paths(root), session.id)
        assert meta.status == "failed"


class TestRunProviderSessionKeyboardInterrupt:
    def test_keyboard_interrupt_sets_session_interrupted(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="codex", goal="g")
        handoff = create_handoff(root, "codex", "g")
        term = _plain_term()

        with (
            patch("loghop.cli_commands._runner.build_launch_command", return_value=["codex"]),
            patch(
                "loghop.cli_commands._runner.subprocess.run",
                side_effect=KeyboardInterrupt,
            ),
            pytest.raises(KeyboardInterrupt),
        ):
            run_provider_session(root, "codex", "codex", session.id, handoff.id, "prompt", term)

        meta = find_session(project_paths(root), session.id)
        assert meta.status == "interrupted"


class TestRunProviderSessionSuccess:
    def test_zero_exit_sets_session_succeeded(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="codex", goal="g")
        handoff = create_handoff(root, "codex", "g")
        term = _plain_term()

        fake_result = subprocess.CompletedProcess(
            args=["codex"], returncode=0, stdout="all done", stderr=""
        )
        with (
            patch("loghop.cli_commands._runner.build_launch_command", return_value=["codex"]),
            patch("loghop.cli_commands._runner.subprocess.run", return_value=fake_result),
        ):
            code = run_provider_session(
                root, "codex", "codex", session.id, handoff.id, "prompt", term
            )

        assert code == 0
        meta = find_session(project_paths(root), session.id)
        assert meta.status == "succeeded"

    def test_claude_auth_token_is_aliased_to_api_key_for_launch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="claude", goal="g")
        handoff = create_handoff(root, "claude", "g")
        term = _plain_term()
        captured_env: dict[str, str] = {}
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-provider-test")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.example.com/anthropic")

        def fake_run(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured_env.update(cast(Any, kwargs.get("env") or {}))
            return subprocess.CompletedProcess(args=["claude"], returncode=0, stdout="", stderr="")

        with (
            patch(
                "loghop.cli_commands._runner.build_launch_command",
                return_value=["claude", "--bare", "--", "prompt"],
            ),
            patch("loghop.cli_commands._runner.subprocess.run", side_effect=fake_run),
        ):
            code = run_provider_session(
                root, "claude", "claude", session.id, handoff.id, "prompt", term
            )

        assert code == 0
        assert captured_env["ANTHROPIC_API_KEY"] == "sk-provider-test"
        assert captured_env["ANTHROPIC_BASE_URL"] == "https://api.example.com/anthropic"

    def test_claude_shell_auth_token_is_passed_to_launch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="claude", goal="g")
        handoff = create_handoff(root, "claude", "g")
        term = _plain_term()
        captured_env: dict[str, str] = {}
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

        def fake_run(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured_env.update(cast(Any, kwargs.get("env") or {}))
            return subprocess.CompletedProcess(args=["claude"], returncode=0, stdout="", stderr="")

        with (
            patch(
                "loghop.cli_commands._runner.claude_api_environment",
                return_value={
                    "ANTHROPIC_AUTH_TOKEN": "sk-provider-test",
                    "ANTHROPIC_BASE_URL": "https://api.example.com/anthropic",
                },
            ),
            patch(
                "loghop.cli_commands._runner.build_launch_command",
                return_value=["claude", "--bare", "--", "prompt"],
            ),
            patch("loghop.cli_commands._runner.subprocess.run", side_effect=fake_run),
        ):
            code = run_provider_session(
                root, "claude", "claude", session.id, handoff.id, "prompt", term
            )

        assert code == 0
        assert captured_env["ANTHROPIC_API_KEY"] == "sk-provider-test"
        assert captured_env["ANTHROPIC_BASE_URL"] == "https://api.example.com/anthropic"

    def test_claude_interactive_does_not_alias_auth_token_to_api_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="claude", goal="g")
        handoff = create_handoff(root, "claude", "g")
        term = _plain_term()
        captured_env: dict[str, str] = {}
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-provider-test")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.example.com/anthropic")

        def fake_run(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured_env.update(cast(Any, kwargs.get("env") or {}))
            return subprocess.CompletedProcess(args=["claude"], returncode=0, stdout="", stderr="")

        with (
            patch(
                "loghop.cli_commands._runner.build_launch_command",
                return_value=["claude", "--bare", "prompt"],
            ),
            patch("loghop.cli_commands._runner.subprocess.run", side_effect=fake_run),
        ):
            code = run_provider_session(
                root,
                "claude",
                "claude",
                session.id,
                handoff.id,
                "prompt",
                term,
                interactive=True,
            )

        assert code == 0
        assert "ANTHROPIC_API_KEY" not in captured_env
        assert captured_env["ANTHROPIC_AUTH_TOKEN"] == "sk-provider-test"
        assert captured_env["ANTHROPIC_BASE_URL"] == "https://api.example.com/anthropic"

    def test_zero_exit_auth_failure_is_failed(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="claude", goal="g")
        handoff = create_handoff(root, "claude", "g")
        term = _plain_term()

        fake_result = subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout="", stderr=""
        )
        with (
            patch("loghop.cli_commands._runner.build_launch_command", return_value=["claude"]),
            patch("loghop.cli_commands._runner.subprocess.run", return_value=fake_result),
            patch(
                "loghop.session_lifecycle.capture_from_transcript",
                return_value={
                    "summary": "Not logged in · Please run /login",
                    "turns_captured": 1,
                },
            ),
        ):
            code = run_provider_session(
                root, "claude", "claude", session.id, handoff.id, "prompt", term
            )

        assert code == 10
        meta = find_session(project_paths(root), session.id)
        assert meta.status == "failed"
        assert meta.returncode == "1"
