"""Tests for install-prompt, install-hooks, install-shims CLI commands."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

CliRunner = Callable[..., tuple[int, str, str]]


class TestInstallPrompt:
    def test_installs_codex_prompt(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, stdout, _ = cli(["install-prompt", "--codex"], cwd=initialized_repo)
        assert code == 0
        assert stdout

    def test_installs_claude_prompt(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, _stdout, _ = cli(["install-prompt", "--claude"], cwd=initialized_repo)
        assert code == 0

    def test_installs_both_by_default(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, _stdout, _ = cli(["install-prompt"], cwd=initialized_repo)
        assert code == 0

    def test_uninstall_prompt(self, cli: CliRunner, initialized_repo: Path) -> None:
        cli(["install-prompt", "--codex"], cwd=initialized_repo)
        code, _stdout, _ = cli(["install-prompt", "--codex", "--uninstall"], cwd=initialized_repo)
        assert code == 0

    def test_scope_project_fails_outside_repo(
        self, cli: CliRunner, loghop_env: object, tmp_path: Path
    ) -> None:
        code, _, stderr = cli(["install-prompt", "--scope", "project"], cwd=tmp_path)
        assert code == 2
        assert "scope project" in stderr

    def test_scope_project_installs_local_prompt(
        self, cli: CliRunner, initialized_repo: Path
    ) -> None:
        code, _, _ = cli(["install-prompt", "--scope", "project", "--codex"], cwd=initialized_repo)
        assert code == 0
        assert (initialized_repo / ".loghop" / "loghop-prompt.md").exists()
        assert "@.loghop/loghop-prompt.md" in (initialized_repo / "AGENTS.md").read_text(
            encoding="utf-8"
        )


class TestInstallHooks:
    def test_installs_claude_hooks(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, _stdout, _ = cli(["install-hooks"], cwd=initialized_repo)
        assert code == 0

    def test_uninstall_hooks(self, cli: CliRunner, initialized_repo: Path) -> None:
        cli(["install-hooks"], cwd=initialized_repo)
        code, _, _ = cli(["install-hooks", "--uninstall"], cwd=initialized_repo)
        assert code == 0

    def test_scope_project_fails_outside_repo(
        self, cli: CliRunner, loghop_env: object, tmp_path: Path
    ) -> None:
        code, _, stderr = cli(["install-hooks", "--scope", "project"], cwd=tmp_path)
        assert code == 2
        assert "scope project" in stderr


class TestInstallShims:
    def test_installs_codex_shim(
        self, cli: CliRunner, initialized_repo: Path, tmp_path: Path
    ) -> None:
        prefix = tmp_path / "shims"
        prefix.mkdir()
        code, _stdout, _ = cli(
            ["install-shims", "--codex", "--prefix", str(prefix)],
            cwd=initialized_repo,
        )
        assert code == 0

    def test_installs_default_codex_when_no_flags(
        self, cli: CliRunner, initialized_repo: Path, tmp_path: Path
    ) -> None:
        prefix = tmp_path / "shims"
        prefix.mkdir()
        code, _, _ = cli(["install-shims", "--prefix", str(prefix)], cwd=initialized_repo)
        assert code == 0

    def test_rejects_claude_shim_flag(
        self, cli: CliRunner, initialized_repo: Path, tmp_path: Path
    ) -> None:
        prefix = tmp_path / "shims"
        prefix.mkdir()
        code, _, stderr = cli(
            ["install-shims", "--claude", "--prefix", str(prefix)],
            cwd=initialized_repo,
        )
        assert code == 2
        assert "--claude" in stderr
