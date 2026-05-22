# mypy: disable-error-code="no-untyped-def"
from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import stat
from collections.abc import Callable
from pathlib import Path

import pytest

CliRunner = Callable[..., tuple[int, str, str]]


class _TTYInput(io.StringIO):
    def isatty(self) -> bool:
        return True


class _TTYOutput(io.StringIO):
    def isatty(self) -> bool:
        return True


class TestBareLanding:
    def test_inside_project_shows_landing(self, cli: CliRunner, initialized_repo: Path) -> None:
        cli(["goal", "Ship the auth module"], cwd=initialized_repo)
        code, stdout, _ = cli([], cwd=initialized_repo)
        assert code == 0
        assert "loghop" in stdout
        assert "Ship the auth module" in stdout
        assert "default provider" in stdout
        assert "loghop run" in stdout

    def test_interactive_without_textual_falls_back_to_dashboard(
        self,
        initialized_repo: Path,
        monkeypatch,
    ) -> None:
        from loghop import cli as cli_module

        monkeypatch.chdir(initialized_repo)
        assert cli_module.main(["goal", "Ship the auth module"]) == 0
        monkeypatch.setattr(
            importlib.util,
            "find_spec",
            lambda name, *args, **kwargs: (
                None
                if name == "textual"
                else importlib.machinery.PathFinder.find_spec(name, *args, **kwargs)
            ),
        )

        monkeypatch.setattr("sys.stdin", _TTYInput(""))
        stdout = _TTYOutput()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli_module.main([])

        assert code == 0
        assert "Ship the auth module" in stdout.getvalue()
        assert "textual is not installed" not in stderr.getvalue().lower()

    def test_outside_project_hints_init(self, cli: CliRunner, tmp_path: Path, monkeypatch) -> None:
        Path.home()
        # Force registry module to recompute its HOME-derived path.
        import importlib

        import loghop.store._registry as registry_mod

        importlib.reload(registry_mod)
        outside = tmp_path / "empty"
        outside.mkdir()
        code, stdout, _ = cli([], cwd=outside)
        assert code == 0
        assert "loghop init" in stdout
        importlib.reload(registry_mod)


class TestProviderDefaulting:
    def test_handoff_build_accepts_no_provider_when_installed(
        self, cli: CliRunner, initialized_repo: Path
    ) -> None:
        cli(["goal", "x"], cwd=initialized_repo)
        code, stdout, _ = cli(["handoff", "build"], cwd=initialized_repo)
        assert code == 0
        assert "handoff built" in stdout.lower() or "H-" in stdout

    def test_resolve_default_provider_picks_last_healthy_session_provider(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import subprocess

        from loghop.cli_commands._helpers import resolve_default_provider
        from loghop.store import init_project
        from loghop.store._session import create_session, finish_session

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        for name in ("codex", "claude"):
            script = bin_dir / name
            script.write_text("#!/bin/sh\nexit 0\n")
            script.chmod(0o755)
        original_path = monkeypatch.delenv("PATH", raising=False) or "/usr/bin:/bin"
        monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")

        root = tmp_path / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "d@e.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "d"], cwd=root, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)
        (root / "x").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "i"], cwd=root, check=True)
        init_project(root)

        session = create_session(root, provider="claude", goal="x")
        finish_session(root, session.id, status="succeeded", returncode=0)
        assert resolve_default_provider(root) == "claude"
        _ = original_path  # silence unused

    def test_resolve_default_provider_skips_failed_and_running_sessions(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import subprocess

        from loghop.cli_commands._helpers import resolve_default_provider
        from loghop.store import init_project
        from loghop.store._session import create_session, finish_session

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        for name in ("codex", "claude"):
            script = bin_dir / name
            script.write_text("#!/bin/sh\nexit 0\n")
            script.chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")

        root = tmp_path / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "d@e.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "d"], cwd=root, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)
        (root / "x").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "i"], cwd=root, check=True)
        init_project(root)

        codex = create_session(root, provider="codex", goal="good")
        finish_session(root, codex.id, status="succeeded", returncode=0)
        failed_claude = create_session(root, provider="claude", goal="bad auth")
        finish_session(root, failed_claude.id, status="failed", returncode=1)
        create_session(root, provider="claude", goal="still running")

        assert resolve_default_provider(root) == "codex"

    def test_resolve_default_provider_skips_auth_failure_summary(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import subprocess

        from loghop.cli_commands._helpers import resolve_default_provider
        from loghop.store import init_project
        from loghop.store._session import create_session, finish_session

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        for name in ("codex", "claude"):
            script = bin_dir / name
            script.write_text("#!/bin/sh\nexit 0\n")
            script.chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")

        root = tmp_path / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "d@e.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "d"], cwd=root, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)
        (root / "x").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "i"], cwd=root, check=True)
        init_project(root)

        codex = create_session(root, provider="codex", goal="good")
        finish_session(root, codex.id, status="succeeded", returncode=0)
        claude = create_session(root, provider="claude", goal="bad auth")
        finish_session(
            root,
            claude.id,
            status="succeeded",
            summary="Not logged in · Please run /login",
            returncode=0,
        )

        assert resolve_default_provider(root) == "codex"

    def test_resolve_default_provider_skips_stale_loghop_codex_shim(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import subprocess

        from loghop.cli_commands._helpers import resolve_default_provider, resolve_enabled_provider
        from loghop.errors import LoghopError
        from loghop.install._config import save_codex_shim_prefix
        from loghop.install._shim import _shim_body
        from loghop.store import init_project, load_config, project_paths

        shim_dir = tmp_path / "shim"
        shim_dir.mkdir()
        shim = shim_dir / "codex"
        shim.write_text(_shim_body("codex", "/missing/real/codex"), encoding="utf-8")
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
        save_codex_shim_prefix(shim_dir)
        monkeypatch.setenv("PATH", f"{shim_dir}:/usr/bin:/bin")

        root = tmp_path / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "d@e.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "d"], cwd=root, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)
        (root / "x").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "i"], cwd=root, check=True)
        init_project(root)

        assert resolve_default_provider(root) is None
        with pytest.raises(LoghopError):
            resolve_enabled_provider("codex", load_config(project_paths(root)))
