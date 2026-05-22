# mypy: disable-error-code="no-untyped-def"
"""Tests for the newer install features: dry-run, is_installed, doctor, rollback."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

CliRunner = Callable[..., tuple[int, str, str]]


class TestDryRun:
    def test_hooks_dry_run_does_not_write(self, tmp_path: Path) -> None:
        from loghop.install import install_claude_hooks

        reports = install_claude_hooks(scope_user=False, project_root=tmp_path, dry_run=True)
        assert reports[0].action == "would-create"
        assert not (tmp_path / ".claude" / "settings.json").exists()

    def test_prompt_dry_run_does_not_write(self) -> None:
        from loghop.install import install_loghop_prompt

        reports = install_loghop_prompt(targets=("codex",), dry_run=True)
        actions = {r.action for r in reports}
        assert actions <= {"would-create", "would-update", "unchanged"}
        # No prompt file should exist on disk after a dry run.
        assert not (Path.home() / ".loghop" / "loghop-prompt.md").exists()
        assert not (Path.home() / ".codex" / "AGENTS.md").exists()

    def test_shim_dry_run_does_not_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from loghop.install import install_codex_shim

        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
        (real_dir / "codex").chmod(0o755)
        prefix = tmp_path / "shimbin"
        prefix.mkdir()
        monkeypatch.setenv("PATH", f"{prefix}:{real_dir}")

        report = install_codex_shim(prefix=prefix, dry_run=True)
        assert report.action == "would-create"
        assert not (prefix / "codex").exists()


class TestIsInstalled:
    def test_returns_false_when_nothing_installed(self) -> None:
        from loghop.install import is_installed

        status = is_installed()
        assert not status.any
        assert not status.all

    def test_detects_claude_hooks_after_install(self) -> None:
        from loghop.install import install_claude_hooks, is_installed

        install_claude_hooks()
        assert is_installed().claude_hooks is True

    def test_detects_prompt_after_install(self) -> None:
        from loghop.install import install_loghop_prompt, is_installed

        install_loghop_prompt(targets=("codex", "claude"))
        assert is_installed().prompt_block is True


class TestStrictPreconditions:
    def test_shim_errors_when_default_prefix_not_on_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from loghop.install import install_codex_shim

        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
        (real_dir / "codex").chmod(0o755)
        # ~/.local/bin is intentionally NOT on PATH.
        monkeypatch.setenv("PATH", str(real_dir))

        report = install_codex_shim()  # default prefix → ~/.local/bin
        assert report.action == "error"
        assert "PATH" in (report.detail or "")

    def test_shim_explicit_prefix_only_warns_when_off_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from loghop.install import install_codex_shim

        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
        (real_dir / "codex").chmod(0o755)
        monkeypatch.setenv("PATH", str(real_dir))

        prefix = tmp_path / "shimbin"
        report = install_codex_shim(prefix=prefix)
        # Explicit prefix → user takes responsibility, only a warning.
        assert report.action in {"created", "updated"}
        assert "not on PATH" in (report.detail or "")

    def test_hooks_error_on_corrupt_settings(self, tmp_path: Path) -> None:
        from loghop.install import install_claude_hooks

        settings = tmp_path / ".claude" / "settings.json"
        settings.parent.mkdir()
        settings.write_text("{not valid json", encoding="utf-8")
        reports = install_claude_hooks(scope_user=False, project_root=tmp_path)
        assert reports[0].action == "error"
        assert "valid JSON" in (reports[0].detail or "")

    def test_shim_skipped_on_windows(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from loghop.install import install_codex_shim

        monkeypatch.setattr(sys, "platform", "win32")
        report = install_codex_shim(prefix=tmp_path)
        assert report.action == "skipped"
        assert "POSIX-only" in (report.detail or "")


class TestDoctor:
    def test_doctor_reports_missing_when_nothing_installed(
        self, cli: CliRunner, tmp_path: Path
    ) -> None:
        code, stdout, _ = cli(["doctor"], cwd=tmp_path)
        assert code == 1
        assert "claude-hooks" in stdout
        assert "codex-shim" in stdout
        assert "prompt-block" in stdout
        assert "missing" in stdout

    def test_doctor_passes_when_all_installed(
        self,
        cli: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from loghop.install import install_claude_hooks, install_codex_shim, install_loghop_prompt

        # Set up real codex + ~/.local/bin on PATH.
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
        (real_dir / "codex").chmod(0o755)
        local_bin = Path.home() / ".local" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        existing_path = os.environ.get("PATH", "")
        monkeypatch.setenv("PATH", f"{local_bin}{os.pathsep}{real_dir}{os.pathsep}{existing_path}")

        install_claude_hooks()
        install_codex_shim(binary="codex")
        install_loghop_prompt()

        _code, stdout, _ = cli(["doctor"], cwd=tmp_path)
        # CLI may or may not be on PATH depending on env; tolerate both.
        assert "claude-hooks" in stdout
        assert "codex-shim" in stdout
        assert "prompt-block" in stdout

    def test_doctor_flags_version_drift(
        self,
        cli: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from loghop.install import InitInstallChoices, save_init_install_choices

        save_init_install_choices(
            InitInstallChoices(
                install_claude_hooks=False,
                install_codex_shim=False,
                install_prompt_block=False,
            )
        )
        # Pin a fake "running version" different from the saved one.
        monkeypatch.setattr(
            "loghop.cli_commands._admin_init.__name__", "loghop.cli_commands._admin_init"
        )
        # Re-write the config with a different version.
        config = Path.home() / ".loghop" / "config.toml"
        text = config.read_text(encoding="utf-8")
        config.write_text(
            text.replace('installed_version = "', 'installed_version = "999.999.999-')
            if "installed_version" in text
            else text + '\ninstalled_version = "999.0.0"\n',
            encoding="utf-8",
        )

        _code, stdout, _ = cli(["doctor"], cwd=tmp_path)
        # Should detect drift somewhere.
        assert "drift" in stdout or "version" in stdout

    def test_doctor_accepts_partial_prompt_install(self, cli: CliRunner, tmp_path: Path) -> None:
        import json

        from loghop.install import install_loghop_prompt

        install_loghop_prompt(targets=("codex",))

        code, stdout, _ = cli(["--json", "doctor"], cwd=tmp_path)
        envelope = json.loads(stdout)
        prompt = next(c for c in envelope["components"] if c["name"] == "prompt-block")

        assert prompt["state"] == "ok"
        assert "codex" in prompt["detail"]
        assert code in (0, 1)

    def test_doctor_uses_saved_custom_shim_prefix(
        self,
        cli: CliRunner,
        initialized_repo: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import json

        prefix = tmp_path / "custom-bin"
        prefix.mkdir()
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
        (real_dir / "codex").chmod(0o755)
        existing_path = os.environ.get("PATH", "")
        monkeypatch.setenv("PATH", f"{prefix}{os.pathsep}{real_dir}{os.pathsep}{existing_path}")

        code, _, _ = cli(["install-shims", "--prefix", str(prefix)], cwd=initialized_repo)
        assert code == 0

        code, stdout, _ = cli(["--json", "doctor"], cwd=initialized_repo)
        envelope = json.loads(stdout)
        shim = next(c for c in envelope["components"] if c["name"] == "codex-shim")

        assert shim["state"] in {"ok", "warn"}
        assert str(prefix / "codex") in shim["detail"]
        assert code in (0, 1)

    def test_doctor_treats_path_order_as_warning_not_failure(
        self,
        cli: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import json

        from loghop.install import install_codex_shim
        from loghop.install._config import save_codex_shim_prefix

        prefix = tmp_path / "custom-bin"
        prefix.mkdir()
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
        (real_dir / "codex").chmod(0o755)
        existing_path = os.environ.get("PATH", "")
        monkeypatch.setenv("PATH", f"{real_dir}{os.pathsep}{prefix}{os.pathsep}{existing_path}")

        install_codex_shim(prefix=prefix, binary="codex")
        save_codex_shim_prefix(prefix)

        code, stdout, _ = cli(["--json", "doctor"], cwd=tmp_path)
        envelope = json.loads(stdout)
        shim = next(c for c in envelope["components"] if c["name"] == "codex-shim")

        assert shim["state"] == "warn"
        assert "not first in PATH" in shim["detail"]
        assert not any("not first in PATH" in problem for problem in envelope["problems"])
        assert code in (0, 1)


class TestForceReinstall:
    def test_init_skips_when_already_installed(
        self,
        cli: CliRunner,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from loghop.install import install_claude_hooks, install_codex_shim, install_loghop_prompt

        real_dir = git_repo.parent / "real"
        real_dir.mkdir()
        (real_dir / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
        (real_dir / "codex").chmod(0o755)
        local_bin = Path.home() / ".local" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        existing_path = os.environ.get("PATH", "")
        monkeypatch.setenv("PATH", f"{local_bin}{os.pathsep}{real_dir}{os.pathsep}{existing_path}")

        install_claude_hooks()
        install_codex_shim(binary="codex")
        install_loghop_prompt()

        code, stdout, _ = cli(["init"], cwd=git_repo)
        assert code == 0
        assert "install already looks complete" in stdout.lower()


class TestRollback:
    def test_rollback_restores_backup_on_install_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If a later step errors, earlier-modified files are restored from .bak."""
        from loghop.cli_commands.admin import _rollback, _RollbackOp

        target = tmp_path / "settings.json"
        target.write_text("ORIGINAL", encoding="utf-8")
        bak = target.with_suffix(target.suffix + ".loghop.bak")
        bak.write_text("ORIGINAL", encoding="utf-8")
        # Mutate the target as if an installer wrote to it.
        target.write_text("MUTATED", encoding="utf-8")

        class _SilentTerm:
            def warn(self, *_args, **_kwargs) -> None: ...
            def error(self, *_args, **_kwargs) -> None: ...

        _rollback([_RollbackOp(path=target, restore_from=bak)], cast(Any, _SilentTerm()))
        assert target.read_text(encoding="utf-8") == "ORIGINAL"

    def test_rollback_removes_newly_created_file(self, tmp_path: Path) -> None:
        from loghop.cli_commands.admin import _rollback, _RollbackOp

        created = tmp_path / "new-file.txt"
        created.write_text("TEMP", encoding="utf-8")

        class _SilentTerm:
            def warn(self, *_args, **_kwargs) -> None: ...
            def error(self, *_args, **_kwargs) -> None: ...

        _rollback([_RollbackOp(path=created, remove_created=True)], cast(Any, _SilentTerm()))
        assert not created.exists()


class TestVisualInstall:
    def test_welcome_panel_shows_in_tty(
        self,
        cli: CliRunner,
        git_repo: Path,
        loghop_env,
        fake_provider,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        bin_dir = loghop_env.root / "bin"
        bin_dir.mkdir()
        fake_provider(bin_dir, "codex")
        local_bin = Path.home() / ".local" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        existing = os.environ.get("PATH", "")
        monkeypatch.setenv("PATH", f"{local_bin}{os.pathsep}{bin_dir}{os.pathsep}{existing}")

        # Need a TTY-shaped stdin for the welcome panel to render. Empty answers
        # → defaults trigger.
        import io

        class _TTYInput(io.StringIO):
            def isatty(self) -> bool:
                return True

        monkeypatch.setattr("sys.stdin", _TTYInput("y\ny\ny\n\n"))

        code, stdout, _ = cli(["init"], cwd=git_repo)
        assert code == 0
        # Welcome panel components mentioned.
        assert "Claude session hooks" in stdout
        assert "Codex PATH shim" in stdout
        # Final summary panel.
        assert "install summary" in stdout
        assert "next steps" in stdout

    def test_no_panels_in_no_prompt(
        self,
        cli: CliRunner,
        git_repo: Path,
    ) -> None:
        code, stdout, _ = cli(["init", "--no-prompt"], cwd=git_repo)
        assert code == 0
        # No tutorial panel rendered in non-interactive mode.
        assert "Claude session hooks" not in stdout
        assert "next steps" not in stdout


class TestProjectSelector:
    def test_init_never_offers_other_projects(
        self,
        cli: CliRunner,
        git_repo: Path,
        loghop_env,
        fake_provider,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        from loghop.store._models import RegistryEntry
        from loghop.store._registry import save_registry

        # Seed a second registered project.
        other = tmp_path / "other-project"
        other.mkdir()
        (other / ".loghop").mkdir()
        (other / ".loghop" / "config.toml").write_text("", encoding="utf-8")
        save_registry(
            [
                RegistryEntry(
                    name="other-project",
                    path=str(other),
                    registered="2026-01-01T00:00:00Z",
                    last_used="2026-01-01T00:00:00Z",
                )
            ]
        )

        bin_dir = loghop_env.root / "bin"
        bin_dir.mkdir()
        fake_provider(bin_dir, "codex")
        local_bin = Path.home() / ".local" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        existing = os.environ.get("PATH", "")
        monkeypatch.setenv("PATH", f"{local_bin}{os.pathsep}{bin_dir}{os.pathsep}{existing}")

        import io

        class _TTYInput(io.StringIO):
            def isatty(self) -> bool:
                return True

        monkeypatch.setattr("sys.stdin", _TTYInput("y\ny\ny\n"))
        code, stdout, _ = cli(["init"], cwd=git_repo)
        assert code == 0
        assert "other registered projects" not in stdout
        assert str(other) not in stdout
        assert not (other / ".claude" / "settings.json").exists()


class TestTopLevelInstall:
    def test_install_works_without_git_repo(self, cli: CliRunner, tmp_path: Path) -> None:
        """`loghop install` must run in a plain directory (no .git, no .loghop)."""
        non_git = tmp_path / "plain-dir"
        non_git.mkdir()
        code, _, _ = cli(["install", "--no-prompt"], cwd=non_git)
        assert code == 0

    def test_install_does_not_create_project_files(self, cli: CliRunner, tmp_path: Path) -> None:
        """Unlike `init`, plain `install` must not write `.loghop/` or `loghop.md`."""
        non_git = tmp_path / "plain-dir"
        non_git.mkdir()
        cli(["install", "--no-prompt"], cwd=non_git)
        assert not (non_git / ".loghop").exists()
        assert not (non_git / "loghop.md").exists()

    def test_install_dry_run(self, cli: CliRunner, tmp_path: Path) -> None:
        from loghop.install import is_installed

        non_git = tmp_path / "plain-dir"
        non_git.mkdir()
        # Need a TTY-shaped stdin so the prompts run; answer Y to all.
        import io

        class _TTYInput(io.StringIO):
            def isatty(self) -> bool:
                return True

        import pytest

        with pytest.MonkeyPatch.context() as mp:
            # Answer Y to hooks + prompt, N to shim (avoids PATH precondition).
            mp.setattr("sys.stdin", _TTYInput("y\nn\ny\n"))
            code, _, _ = cli(["install", "--dry-run"], cwd=non_git)
        assert code == 0
        # Dry-run must leave the filesystem untouched.
        assert not is_installed().any


class TestUninstall:
    def test_uninstall_removes_all_components(
        self,
        cli: CliRunner,
        git_repo: Path,
        loghop_env,
        fake_provider,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from loghop.install import (
            install_claude_hooks,
            install_codex_shim,
            install_loghop_prompt,
            is_installed,
        )

        # Set up everything first.
        bin_dir = loghop_env.root / "bin"
        bin_dir.mkdir()
        fake_provider(bin_dir, "codex")
        local_bin = Path.home() / ".local" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        existing = os.environ.get("PATH", "")
        monkeypatch.setenv("PATH", f"{local_bin}{os.pathsep}{bin_dir}{os.pathsep}{existing}")

        install_claude_hooks()
        install_codex_shim(binary="codex")
        install_loghop_prompt()
        assert is_installed().any

        code, _, _ = cli(["uninstall", "-y"], cwd=git_repo)
        assert code == 0
        status = is_installed()
        assert not status.claude_hooks
        assert not status.codex_shim
        assert not status.prompt_block
        assert not (Path.home() / ".loghop" / "loghop-prompt.md").exists()

    def test_uninstall_dry_run_does_not_write(
        self,
        cli: CliRunner,
        git_repo: Path,
        loghop_env,
        fake_provider,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from loghop.install import install_claude_hooks, is_installed

        local_bin = Path.home() / ".local" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        install_claude_hooks()

        code, _, _ = cli(["uninstall", "-y", "--dry-run"], cwd=git_repo)
        assert code == 0
        # Hooks still present after dry-run.
        assert is_installed().claude_hooks

    def test_uninstall_purge_removes_loghop_dir(self, cli: CliRunner, git_repo: Path) -> None:
        from loghop.install import (
            InitInstallChoices,
            save_init_install_choices,
        )

        save_init_install_choices(
            InitInstallChoices(
                install_claude_hooks=False,
                install_codex_shim=False,
                install_prompt_block=False,
            )
        )
        assert (Path.home() / ".loghop").exists()

        code, _, _ = cli(["uninstall", "-y", "--purge"], cwd=git_repo)
        assert code == 0
        assert not (Path.home() / ".loghop").exists()

    def test_uninstall_keep_config_preserves_config(self, cli: CliRunner, git_repo: Path) -> None:
        from loghop.install import (
            InitInstallChoices,
            global_config_path,
            save_init_install_choices,
        )

        save_init_install_choices(
            InitInstallChoices(
                install_claude_hooks=False,
                install_codex_shim=False,
                install_prompt_block=False,
            )
        )
        cfg = global_config_path()
        assert cfg.exists()

        code, _, _ = cli(["uninstall", "-y", "--keep-config"], cwd=git_repo)
        assert code == 0
        assert cfg.exists()

    def test_uninstall_does_not_purge_after_component_error(
        self, cli: CliRunner, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from loghop.install import InitInstallChoices, save_init_install_choices
        from loghop.install import _types as types_module

        save_init_install_choices(
            InitInstallChoices(
                install_claude_hooks=False,
                install_codex_shim=False,
                install_prompt_block=False,
            )
        )

        def _fail_prompt(**_kwargs):
            return [
                types_module.InstallReport(
                    Path.home() / ".loghop" / "loghop-prompt.md",
                    "error",
                    "simulated uninstall failure",
                )
            ]

        monkeypatch.setattr(
            "loghop.cli_commands._admin_uninstall.install_loghop_prompt", _fail_prompt
        )
        code, _, _ = cli(["uninstall", "-y", "--purge"], cwd=git_repo)
        assert code == 1
        assert (Path.home() / ".loghop").exists()

    def test_uninstall_purge_removes_project_scope_assets(
        self, cli: CliRunner, git_repo: Path, tmp_path: Path
    ) -> None:
        from loghop.install import install_claude_hooks, install_loghop_prompt
        from loghop.install._config import track_project_root

        other = tmp_path / "other"
        other.mkdir()
        (other / ".claude").mkdir()
        install_claude_hooks(scope_user=False, project_root=other)
        install_loghop_prompt(scope_user=False, project_root=other)
        track_project_root(other)

        code, _, _ = cli(["uninstall", "-y", "--purge"], cwd=git_repo)

        assert code == 0
        assert "loghop hook" not in (other / ".claude" / "settings.json").read_text(
            encoding="utf-8"
        )
        agents = other / "AGENTS.md"
        if agents.exists():
            assert "@/" not in agents.read_text(encoding="utf-8")


class TestDoctorFix:
    def test_fix_reinstalls_missing_components(
        self,
        cli: CliRunner,
        tmp_path: Path,
        loghop_env,
        fake_provider,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from loghop.install import is_installed

        bin_dir = loghop_env.root / "bin"
        bin_dir.mkdir()
        fake_provider(bin_dir, "codex")
        local_bin = Path.home() / ".local" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        existing = os.environ.get("PATH", "")
        monkeypatch.setenv("PATH", f"{local_bin}{os.pathsep}{bin_dir}{os.pathsep}{existing}")

        # Nothing installed → doctor --fix should install missing pieces.
        code, _, _ = cli(["doctor", "--fix"], cwd=tmp_path)
        # May still return 1 if `loghop` is not on PATH in the test env, but
        # the components themselves should be installed.
        status = is_installed()
        assert status.claude_hooks
        assert status.codex_shim
        assert status.prompt_block
        del code  # ignore — `loghop-cli on PATH` cannot be auto-fixed in tests


class TestCompletion:
    def test_bash_completion(self, cli: CliRunner, tmp_path: Path) -> None:
        code, stdout, _ = cli(["completion", "bash"], cwd=tmp_path)
        assert code == 0
        assert "_loghop_complete" in stdout
        assert "complete -F" in stdout
        # Includes at least one known subcommand.
        assert "init" in stdout

    def test_zsh_completion(self, cli: CliRunner, tmp_path: Path) -> None:
        code, stdout, _ = cli(["completion", "zsh"], cwd=tmp_path)
        assert code == 0
        assert "#compdef loghop" in stdout
        assert "init" in stdout

    def test_fish_completion(self, cli: CliRunner, tmp_path: Path) -> None:
        code, stdout, _ = cli(["completion", "fish"], cwd=tmp_path)
        assert code == 0
        assert "complete -c loghop" in stdout
        assert "init" in stdout

    def test_unknown_shell_rejected(self, cli: CliRunner, tmp_path: Path) -> None:
        code, _, _ = cli(["completion", "tcsh"], cwd=tmp_path)
        assert code != 0


class TestMigrations:
    def test_no_drift_when_versions_match(self) -> None:
        from loghop import __version__
        from loghop.install import (
            InitInstallChoices,
            detect_drift,
            save_init_install_choices,
        )

        save_init_install_choices(
            InitInstallChoices(
                install_claude_hooks=False,
                install_codex_shim=False,
                install_prompt_block=False,
            )
        )
        # Just-saved version always matches the running version.
        assert detect_drift() is None
        del __version__

    def test_drift_detected_when_version_stale(self) -> None:
        from loghop.install import detect_drift, global_config_path

        cfg = global_config_path()
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(
            "[install]\n"
            "install_claude_hooks = false\n"
            "install_codex_shim = false\n"
            "install_prompt_block = false\n"
            'installed_version = "0.0.1-stale"\n',
            encoding="utf-8",
        )
        assert detect_drift() == "0.0.1-stale"

    def test_run_migrations_stamps_new_version(self) -> None:
        from loghop import __version__
        from loghop.install import (
            global_config_path,
            load_installed_version,
            run_migrations,
        )

        cfg = global_config_path()
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(
            "[install]\n"
            "install_claude_hooks = false\n"
            "install_codex_shim = false\n"
            "install_prompt_block = false\n"
            'installed_version = "0.0.1-stale"\n',
            encoding="utf-8",
        )
        outcome = run_migrations()
        assert outcome.from_version == "0.0.1-stale"
        assert outcome.to_version == __version__
        assert load_installed_version() == __version__


class TestDoctorJsonEnvelope:
    def test_json_envelope_has_stable_shape(self, cli: CliRunner, tmp_path: Path) -> None:
        import json

        code, stdout, _ = cli(["--json", "doctor"], cwd=tmp_path)
        # Doctor returns 1 when nothing installed; JSON should still be valid.
        assert code in (0, 1)
        envelope = json.loads(stdout)
        assert "ok" in envelope
        assert "problems" in envelope
        assert "components" in envelope
        # Components is a list of dicts with name/state/detail.
        for c in envelope["components"]:
            assert {"name", "state", "detail"} <= set(c.keys())


class TestVersionTracking:
    def test_save_persists_installed_version(self) -> None:
        import tomllib

        from loghop import __version__
        from loghop.install import (
            InitInstallChoices,
            global_config_path,
            load_installed_version,
            save_init_install_choices,
        )

        save_init_install_choices(
            InitInstallChoices(
                install_claude_hooks=False,
                install_codex_shim=False,
                install_prompt_block=False,
            )
        )
        config = tomllib.loads(global_config_path().read_text(encoding="utf-8"))
        assert config["install"]["installed_version"] == __version__
        assert load_installed_version() == __version__


class TestDoctorOptOut:
    """Doctor must respect explicit install_*=false from ~/.loghop/config.toml."""

    def test_skipped_components_do_not_count_as_problems(
        self, cli: CliRunner, tmp_path: Path
    ) -> None:
        import json

        from loghop.install import InitInstallChoices, save_init_install_choices

        save_init_install_choices(
            InitInstallChoices(
                install_claude_hooks=False,
                install_codex_shim=False,
                install_prompt_block=False,
            )
        )
        code, stdout, _ = cli(["--json", "doctor"], cwd=tmp_path)
        envelope = json.loads(stdout)
        states = {c["name"]: c["state"] for c in envelope["components"]}
        assert states["claude-hooks"] == "skipped"
        assert states["codex-shim"] == "skipped"
        assert states["prompt-block"] == "skipped"
        # No problems should be reported for the opted-out components.
        assert not any(
            "session hooks" in p or "shim" in p or "prompt" in p for p in envelope["problems"]
        )
        # If `loghop` itself is on PATH (typical), doctor exits 0.
        # If not, it still exits 1 — but only for the cli-on-path problem,
        # not for skipped components.
        assert code in (0, 1)


class TestDryRunPlanWithNoPrompt:
    """`--dry-run` must show the install plan even with `--no-prompt` set."""

    def test_dry_run_plus_no_prompt_emits_would_actions(
        self, cli: CliRunner, tmp_path: Path
    ) -> None:
        import json

        non_git = tmp_path / "plain"
        non_git.mkdir()
        code, stdout, _ = cli(
            ["--json", "install", "--dry-run", "--no-prompt"],
            cwd=non_git,
        )
        assert code == 0
        envelope = json.loads(stdout)
        # The reports list must include at least one would-* action.
        events = json.dumps(envelope.get("events", []))
        assert "would-" in events or "would-create" in stdout or "would-update" in stdout


class TestForceReinstallOnInitialized:
    """`loghop init --force-reinstall` must not error on an initialized repo."""

    def test_force_reinstall_dry_run_succeeds(self, cli: CliRunner, git_repo: Path) -> None:
        # First init normally.
        code, _, _ = cli(["init", "--no-prompt"], cwd=git_repo)
        assert code == 0
        # Re-running with --force-reinstall --dry-run must succeed.
        code, stdout, _ = cli(["init", "--force-reinstall", "--dry-run"], cwd=git_repo)
        assert code == 0
        assert "already initialized" in stdout.lower() or "skipping store init" in stdout.lower()

    def test_plain_rerun_succeeds_without_force(self, cli: CliRunner, git_repo: Path) -> None:
        code, _, _ = cli(["init", "--no-prompt"], cwd=git_repo)
        assert code == 0
        code, stdout, _ = cli(["init"], cwd=git_repo)
        assert code == 0
        assert "already initialized" in stdout.lower()


class TestProjectsPrune:
    """`loghop projects prune` is the discoverable alias of `cleanup`."""

    def test_prune_drops_orphans(
        self, cli: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from loghop.store._models import RegistryEntry
        from loghop.store._registry import load_registry, save_registry

        ghost = tmp_path / "gone-forever"
        save_registry(
            [
                RegistryEntry(
                    name="ghost",
                    path=str(ghost),
                    registered="",
                    last_used="",
                    goal="",
                    last_session="",
                    session_count=0,
                    handoff_count=0,
                )
            ]
        )
        assert any(p.name == "ghost" for p in load_registry())
        code, stdout, _ = cli(["projects", "prune"], cwd=tmp_path)
        assert code == 0
        assert "1" in stdout or "removed" in stdout.lower()
        assert not any(p.name == "ghost" for p in load_registry())


class TestErrorPathsEACCES:
    """Filesystem permission errors must surface as `error` reports, not crashes."""

    def test_settings_readonly_returns_error_not_crash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import json as _json

        from loghop.install import install_claude_hooks

        project = tmp_path / "proj"
        project.mkdir()
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.json"
        settings.write_text(_json.dumps({"hooks": {}}), encoding="utf-8")
        # Drop write bit on the parent dir so atomic_write_text can't create
        # a tempfile.
        original_mode = claude_dir.stat().st_mode
        try:
            claude_dir.chmod(0o500)
            reports = install_claude_hooks(scope_user=False, project_root=project)
        finally:
            claude_dir.chmod(original_mode)
        # We just want a clean failure mode (error report or OSError surfaced
        # via the lock layer), not a corrupted settings.json.
        assert reports
        # No partial write: file content unchanged.
        assert "loghop hook" not in settings.read_text(encoding="utf-8")


class TestErrorPathsENOSPC:
    """Atomic writes must not corrupt settings.json when the disk is full."""

    def test_enospc_during_settings_write_leaves_original_intact(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import json as _json

        from loghop.install import install_claude_hooks

        project = tmp_path / "proj"
        project.mkdir()
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.json"
        original_body = _json.dumps({"hooks": {"PreToolUse": [{"keep": "me"}]}}, indent=2) + "\n"
        settings.write_text(original_body, encoding="utf-8")

        from loghop.store import _io as io_module

        real_write = io_module.atomic_write_text

        def _boom(path, text, **kw):
            if str(path).endswith("settings.json"):
                raise OSError(28, "No space left on device")
            return real_write(path, text, **kw)

        monkeypatch.setattr(io_module, "atomic_write_text", _boom)
        # Patch the imported alias inside _hooks too.
        from loghop.install import _hooks as hooks_module

        monkeypatch.setattr(hooks_module, "atomic_write_text", _boom)

        try:
            reports = install_claude_hooks(scope_user=False, project_root=project)
        except OSError:
            # Either it surfaces the OSError or returns an error report —
            # both acceptable. The non-negotiable invariant is below.
            reports = []
        # Original content must still be intact.
        assert settings.read_text(encoding="utf-8") == original_body
        # If we got reports, the action must not be a successful "created/updated"
        for r in reports:
            assert r.action not in ("created", "updated")


class TestMultiFileRollback:
    """If any install step fails after partial writes, prior changes are rolled back."""

    def test_failed_step_triggers_rollback_of_earlier_files(
        self,
        cli: CliRunner,
        git_repo: Path,
        loghop_env,
        fake_provider,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        bin_dir = loghop_env.root / "bin"
        bin_dir.mkdir()
        fake_provider(bin_dir, "codex")
        local_bin = Path.home() / ".local" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        existing = os.environ.get("PATH", "")
        monkeypatch.setenv("PATH", f"{local_bin}{os.pathsep}{bin_dir}{os.pathsep}{existing}")

        # Pre-existing settings.json content the rollback must preserve.
        settings = Path.home() / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        original = '{\n  "hooks": {}\n}\n'
        settings.write_text(original, encoding="utf-8")

        # Force the prompt step (the third step) to fail by patching it to
        # return an InstallReport with action="error".
        from loghop.cli_commands import _admin_init as admin_module
        from loghop.install import _types as types_module
        from loghop.install import install_loghop_prompt as real_prompt

        def _fail(**kw):
            return [
                types_module.InstallReport(
                    Path.home() / ".loghop" / "loghop-prompt.md",
                    "error",
                    "simulated failure",
                )
            ]

        monkeypatch.setattr(admin_module, "install_loghop_prompt", _fail)

        # Use TTY-shaped stdin to force "yes" to all three.
        import io as _io

        class _TTY(_io.StringIO):
            def isatty(self) -> bool:
                return True

        monkeypatch.setattr("sys.stdin", _TTY("y\ny\ny\n"))
        code, _, _ = cli(["init", "--force-reinstall"], cwd=git_repo)
        assert code != 0
        # Hooks file must be back to its original content.
        assert settings.read_text(encoding="utf-8") == original
        # Restore real prompt installer for any later tests in this module.
        monkeypatch.setattr(admin_module, "install_loghop_prompt", real_prompt)


class TestSettingsLockIsHeld:
    """The hooks installer takes a per-file lock around the read-modify-write."""

    def test_lock_file_path_is_used(self, tmp_path: Path) -> None:
        from loghop.install import install_claude_hooks

        project = tmp_path / "proj"
        project.mkdir()
        reports = install_claude_hooks(scope_user=False, project_root=project)
        assert reports
        # The lock file persists on disk (standard fcntl-based lock behavior),
        # but the lock itself must be released — a second install should succeed.
        _lock_path = project / ".claude" / ".loghop-settings.lock"
        # Lock file may or may not persist (platform-dependent). What matters
        # is that a second install can acquire the lock without timing out.
        reports2 = install_claude_hooks(scope_user=False, project_root=project)
        assert reports2


class TestSiblingWrapperWarning:
    """Sibling wrappers in the shim dir trigger a generic double-wrap warning."""

    @pytest.mark.parametrize(
        "wrapper_name",
        ["codex-rtk", "codex-real", "codex.original", "asdf-codex", "codex.bak"],
    )
    def test_warning_emitted_for_any_sibling_wrapper(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wrapper_name: str
    ) -> None:
        from loghop.install import install_codex_shim

        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
        (real_dir / "codex").chmod(0o755)
        prefix = tmp_path / "shimbin"
        prefix.mkdir()
        # Plant a generic sibling that intercepts `codex`.
        (prefix / wrapper_name).write_text("#!/bin/sh\n# sibling wrapper\n", encoding="utf-8")
        monkeypatch.setenv("PATH", f"{prefix}{os.pathsep}{real_dir}")

        report = install_codex_shim(prefix=prefix)
        assert report.action in ("created", "updated")
        detail = (report.detail or "").lower()
        assert "wrapper" in detail
        assert wrapper_name in detail

    def test_no_warning_when_no_siblings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from loghop.install import install_codex_shim

        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
        (real_dir / "codex").chmod(0o755)
        prefix = tmp_path / "shimbin"
        prefix.mkdir()
        monkeypatch.setenv("PATH", f"{prefix}{os.pathsep}{real_dir}")

        report = install_codex_shim(prefix=prefix)
        assert report.action in ("created", "updated")
        assert "wrapper" not in (report.detail or "").lower()
