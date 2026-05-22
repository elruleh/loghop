"""Regression tests for shell-injection fixes in tui.launcher.

The launcher composes shell commands that get passed to bash -ic by
external terminal emulators. Any unquoted interpolation of paths or
provider names is a remote-code-execution vector if an attacker can
control the project directory or config.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from loghop.tui.launcher import build_resume_command, build_wrap_command


class TestBuildResumeCommandQuoting:
    def test_path_with_single_quote_is_preserved(self) -> None:
        argv = build_resume_command(Path("/tmp/foo'bar"), "claude")
        idx = argv.index("run")
        assert argv[idx + 1] == "/tmp/foo'bar"

    def test_path_with_metacharacters_is_preserved_verbatim(self) -> None:
        evil = "/tmp/foo; rm -rf /; echo "
        argv = build_resume_command(Path(evil), "claude")
        idx = argv.index("run")
        assert argv[idx + 1] == evil
        assert "rm" not in [a for a in argv if a != evil]

    def test_provider_must_be_in_allowlist(self) -> None:
        with pytest.raises(ValueError, match="unsupported provider"):
            build_resume_command(Path("/tmp/x"), "evil; rm -rf /")

    def test_interactive_flag_appended(self) -> None:
        argv = build_resume_command(Path("/tmp/x"), "claude", interactive=True)
        assert argv[-1] == "--interactive"


class TestBuildWrapCommandQuoting:
    def test_path_with_single_quote_is_safely_quoted(self) -> None:
        cmd = build_wrap_command("/tmp/foo'bar", "codex")
        import shlex

        argv = shlex.split(cmd)
        assert argv[0] == "cd"
        assert argv[1] == "/tmp/foo'bar"
        assert argv[2] == "&&"

    def test_path_with_metacharacters_is_safely_quoted(self) -> None:
        evil = "/tmp/x; touch /tmp/pwned"
        cmd = build_wrap_command(evil, "claude")
        import shlex

        argv = shlex.split(cmd)
        assert argv[1] == evil
        tokens_after_path = argv[2:]
        assert "touch" not in tokens_after_path

    def test_provider_must_be_in_allowlist(self) -> None:
        with pytest.raises(ValueError, match="unsupported provider"):
            build_wrap_command("/tmp/x", "../../bin/sh")
