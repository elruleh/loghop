# mypy: disable-error-code="no-untyped-def"
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from loghop.install._migrations import _MigrationOutcome, detect_drift, run_migrations
from loghop.install._types import InstallReport


class TestMigrationOutcome:
    def test_ran_when_versions_differ(self) -> None:
        outcome = _MigrationOutcome(from_version="0.1.0", to_version="0.2.0", reports=[])
        assert outcome.ran is True

    def test_ran_when_same_version(self) -> None:
        outcome = _MigrationOutcome(from_version="0.2.0", to_version="0.2.0", reports=[])
        assert outcome.ran is False

    def test_ran_when_none(self) -> None:
        outcome = _MigrationOutcome(from_version=None, to_version="0.2.0", reports=[])
        assert outcome.ran is True


class TestDetectDrift:
    def test_no_saved_version(self) -> None:
        with patch("loghop.install._migrations.load_installed_version", return_value=None):
            assert detect_drift() is None

    def test_same_version(self) -> None:
        from loghop import __version__

        with patch("loghop.install._migrations.load_installed_version", return_value=__version__):
            assert detect_drift() is None

    def test_different_version(self) -> None:
        with patch("loghop.install._migrations.load_installed_version", return_value="0.0.1"):
            result = detect_drift()
            assert result == "0.0.1"


class TestRunMigrations:
    def test_nothing_installed_no_reports(self) -> None:
        with (
            patch("loghop.install._migrations.load_installed_version", return_value=None),
            patch("loghop.install._migrations.claude_hooks_installed", return_value=False),
            patch("loghop.install._migrations.codex_shim_installed", return_value=False),
            patch("loghop.install._migrations.loghop_prompt_installed", return_value=False),
            patch("loghop.install._config.load_init_install_choices", return_value=None),
        ):
            outcome = run_migrations()
            assert outcome.reports == []
            assert outcome.from_version is None

    def test_reinstalls_installed_components(self) -> None:
        with (
            patch("loghop.install._migrations.load_installed_version", return_value="0.1.0"),
            patch("loghop.install._migrations.claude_hooks_installed", return_value=True),
            patch("loghop.install._migrations.codex_shim_installed", return_value=True),
            patch("loghop.install._migrations.loghop_prompt_installed", return_value=False),
            patch("loghop.install._migrations.install_claude_hooks", return_value=[]),
            patch("loghop.install._migrations.install_codex_shim") as mock_shim,
            patch("loghop.install._config.load_init_install_choices", return_value=None),
        ):
            from loghop.install._types import InstallReport

            mock_shim.return_value = InstallReport(
                path=__import__("pathlib").Path("/fake/codex"), action="updated"
            )
            steps: list[str] = []
            outcome = run_migrations(on_step=steps.append)
            assert len(outcome.reports) >= 1
            assert "codex-shim" in steps
            assert "claude-hooks" in steps
            assert "prompt-block" not in steps

    def test_on_step_callback(self) -> None:
        with (
            patch("loghop.install._migrations.load_installed_version", return_value=None),
            patch("loghop.install._migrations.claude_hooks_installed", return_value=False),
            patch("loghop.install._migrations.codex_shim_installed", return_value=False),
            patch("loghop.install._migrations.loghop_prompt_installed", return_value=False),
            patch("loghop.install._config.load_init_install_choices", return_value=None),
        ):
            steps: list[str] = []
            run_migrations(on_step=steps.append)
            assert steps == []

    def test_stamps_version_on_success(self) -> None:
        from loghop.install._types import InitInstallChoices

        choices = InitInstallChoices(
            install_claude_hooks=False,
            install_codex_shim=False,
            install_prompt_block=False,
        )
        with (
            patch("loghop.install._migrations.load_installed_version", return_value="0.1.0"),
            patch("loghop.install._migrations.claude_hooks_installed", return_value=False),
            patch("loghop.install._migrations.codex_shim_installed", return_value=False),
            patch("loghop.install._migrations.loghop_prompt_installed", return_value=False),
            patch("loghop.install._config.load_init_install_choices", return_value=choices),
            patch("loghop.install._migrations.save_init_install_choices") as mock_save,
        ):
            run_migrations()
            mock_save.assert_called_once_with(choices)

    def test_does_not_stamp_version_when_any_migration_errors(self) -> None:
        from pathlib import Path

        from loghop.install._types import InitInstallChoices, InstallReport

        choices = InitInstallChoices(
            install_claude_hooks=True,
            install_codex_shim=False,
            install_prompt_block=False,
        )
        with (
            patch("loghop.install._migrations.load_installed_version", return_value="0.1.0"),
            patch("loghop.install._migrations.claude_hooks_installed", return_value=True),
            patch("loghop.install._migrations.codex_shim_installed", return_value=False),
            patch("loghop.install._migrations.loghop_prompt_installed", return_value=False),
            patch(
                "loghop.install._migrations.install_claude_hooks",
                return_value=[InstallReport(Path("/tmp/settings.json"), "error", "boom")],
            ),
            patch("loghop.install._config.load_init_install_choices", return_value=choices),
            patch("loghop.install._migrations.save_init_install_choices") as mock_save,
        ):
            outcome = run_migrations()

        assert any(report.action == "error" for report in outcome.reports)
        mock_save.assert_not_called()

    def test_does_not_stamp_version_when_component_errors(self) -> None:
        with (
            patch("loghop.install._migrations.load_installed_version", return_value="0.1.0"),
            patch("loghop.install._migrations.claude_hooks_installed", return_value=True),
            patch(
                "loghop.install._migrations.install_claude_hooks",
                return_value=[InstallReport(Path("/tmp/settings.json"), "error", "boom")],
            ),
            patch("loghop.install._migrations.codex_shim_installed", return_value=False),
            patch("loghop.install._migrations.loghop_prompt_installed", return_value=False),
            patch("loghop.install._config.load_init_install_choices", return_value=None),
            patch("loghop.install._migrations.save_init_install_choices") as mock_save,
        ):
            outcome = run_migrations()
            assert any(report.action == "error" for report in outcome.reports)
            mock_save.assert_not_called()

    def test_migration_reports_global_config_backup(self, tmp_path, monkeypatch) -> None:
        from loghop.install._config import global_config_path

        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        config = global_config_path()
        config.parent.mkdir(parents=True)
        config.write_text(
            "[install]\n"
            "install_claude_hooks = false\n"
            "install_codex_shim = false\n"
            "install_prompt_block = false\n"
            'installed_version = "0.0.1"\n',
            encoding="utf-8",
        )

        outcome = run_migrations()

        backup_reports = [r for r in outcome.reports if r.action == "backup"]
        assert any(r.path.name == "config.toml.loghop.bak" for r in backup_reports)
        assert (config.parent / "config.toml.loghop.bak").exists()
