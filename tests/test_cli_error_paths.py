"""Tests for error-handling branches in cli.py (coverage: 78% -> 85%+)."""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from loghop.cli import _textual_available, main


def _make_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "dev@test.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=path, check=True)
    (path / "app.py").write_text("print('hi')\n")
    subprocess.run(["git", "add", "app.py"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True, capture_output=True)
    return path


class TestPythonVersionCheck:
    def test_version_too_old(self) -> None:
        with patch("loghop.cli.sys") as mock_sys:
            mock_sys.version_info = (3, 10, 0)
            mock_sys.argv = ["loghop"]
            mock_sys.stderr = sys.stderr
            rc = main([])
            assert rc == 1


class TestTextualAvailable:
    def test_import_error(self) -> None:
        with patch("importlib.util.find_spec", side_effect=ImportError):
            assert not _textual_available()

    def test_value_error(self) -> None:
        with patch("importlib.util.find_spec", side_effect=ValueError):
            assert not _textual_available()


class TestJsonNoCommand:
    def test_json_no_command(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch("loghop.cli._textual_available", return_value=False),
            patch("sys.stdout", stdout),
            patch("sys.stderr", stderr),
        ):
            rc = main(["--json"])
        assert rc == 2


class TestErrorHandlers:
    """Test error branches in _run_command by patching store functions.

    We patch list_sessions in the sessions module's namespace because
    argparse stores a direct reference to the handler function.
    """

    @pytest.fixture
    def initialized_repo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        repo = _make_git_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)
        rc = main(["init"])
        assert rc == 0
        return repo

    def _run(self, *argv: str) -> int:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            return main(list(argv))

    def test_keyboard_interrupt(self, initialized_repo: Path) -> None:
        with patch("loghop.cli_commands.sessions.list_sessions", side_effect=KeyboardInterrupt):
            rc = self._run("--plain", "sessions", "list")
        assert rc == 130

    def test_loghop_error(self, initialized_repo: Path) -> None:
        from loghop.errors import LoghopError

        with patch(
            "loghop.cli_commands.sessions.list_sessions",
            side_effect=LoghopError("test error", code="E_TEST", exit_code=42),
        ):
            rc = self._run("--plain", "sessions", "list")
        assert rc == 42

    def test_timeout_error(self, initialized_repo: Path) -> None:
        with patch(
            "loghop.cli_commands.sessions.list_sessions",
            side_effect=TimeoutError("slow"),
        ):
            rc = self._run("--plain", "sessions", "list")
        assert rc == 3

    def test_value_error(self, initialized_repo: Path) -> None:
        with patch(
            "loghop.cli_commands.sessions.list_sessions",
            side_effect=ValueError("bad"),
        ):
            rc = self._run("--plain", "sessions", "list")
        assert rc == 2

    def test_unexpected_error(self, initialized_repo: Path) -> None:
        with patch(
            "loghop.cli_commands.sessions.list_sessions",
            side_effect=RuntimeError("boom"),
        ):
            rc = self._run("--plain", "sessions", "list")
        assert rc == 1

    def test_json_error_output(self, initialized_repo: Path) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch(
                "loghop.cli_commands.sessions.list_sessions",
                side_effect=RuntimeError("boom"),
            ),
            patch("sys.stdout", stdout),
            patch("sys.stderr", stderr),
        ):
            rc = main(["--json", "--plain", "sessions", "list"])
        assert rc == 1
        output = stdout.getvalue()
        assert "RuntimeError" in output
