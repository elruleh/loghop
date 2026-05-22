"""Unit tests for admin uninstall command.

Covers: handle_uninstall with purge, keep-config, dry-run, confirm-no, and error paths.
"""

import argparse
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from loghop.terminal import Terminal


def _term(confirm_return: bool = True) -> Terminal:
    from loghop.terminal import Terminal

    term = MagicMock(spec=Terminal)
    term.confirm.return_value = confirm_return
    term.json_mode = False
    return term


def _args(**overrides: object) -> argparse.Namespace:
    defaults = {
        "keep_config": False,
        "purge": False,
        "dry_run": False,
        "yes": False,
    }
    defaults.update(cast(Any, overrides))
    return argparse.Namespace(**defaults)


class TestUninstallDryRun:
    def test_dry_run_skips_confirmation(self, tmp_path: Path) -> None:
        from loghop.cli_commands._admin_uninstall import handle_uninstall

        term = _term()
        args = _args(dry_run=True)

        with (
            patch(
                "loghop.cli_commands._admin_uninstall.load_tracked_project_roots", return_value=[]
            ),
            patch("loghop.cli_commands._admin_uninstall.load_registry", return_value=[]),
            patch("loghop.cli_commands._admin_uninstall.load_codex_shim_prefix", return_value=None),
            patch("loghop.cli_commands._admin_uninstall.install_claude_hooks", return_value=[]),
            patch("loghop.cli_commands._admin_uninstall.install_codex_shim") as shim_mock,
            patch("loghop.cli_commands._admin_uninstall.install_loghop_prompt", return_value=[]),
            patch("loghop.cli_commands._admin_uninstall._emit_reports", return_value=0),
        ):
            code = handle_uninstall(args, term)
        assert code == 0
        shim_mock.assert_called_once()
        _, kwargs = shim_mock.call_args
        assert kwargs["dry_run"] is True

    def test_dry_run_does_not_save_config(self, tmp_path: Path) -> None:
        from loghop.cli_commands._admin_uninstall import handle_uninstall

        term = _term()
        args = _args(dry_run=True)

        with (
            patch(
                "loghop.cli_commands._admin_uninstall.load_tracked_project_roots", return_value=[]
            ),
            patch("loghop.cli_commands._admin_uninstall.load_registry", return_value=[]),
            patch("loghop.cli_commands._admin_uninstall.load_codex_shim_prefix", return_value=None),
            patch("loghop.cli_commands._admin_uninstall.install_claude_hooks", return_value=[]),
            patch(
                "loghop.cli_commands._admin_uninstall.install_codex_shim",
                return_value={"action": "would-remove"},
            ),
            patch("loghop.cli_commands._admin_uninstall.install_loghop_prompt", return_value=[]),
            patch("loghop.cli_commands._admin_uninstall._emit_reports", return_value=0),
            patch("loghop.cli_commands._admin_uninstall.save_codex_shim_prefix") as save_mock,
        ):
            handle_uninstall(args, term)
        save_mock.assert_not_called()


class TestUninstallConfirmNo:
    def test_user_declines_returns_0(self) -> None:
        from loghop.cli_commands._admin_uninstall import handle_uninstall

        term = _term(confirm_return=False)
        args = _args()

        code = handle_uninstall(args, term)
        assert code == 0
        cast(Any, term).info.assert_called_with("Aborted")


class TestUninstallWithYes:
    def test_yes_flag_skips_confirm(self) -> None:
        from loghop.cli_commands._admin_uninstall import handle_uninstall

        term = _term(confirm_return=False)
        args = _args(yes=True)

        with (
            patch(
                "loghop.cli_commands._admin_uninstall.load_tracked_project_roots", return_value=[]
            ),
            patch("loghop.cli_commands._admin_uninstall.load_registry", return_value=[]),
            patch("loghop.cli_commands._admin_uninstall.load_codex_shim_prefix", return_value=None),
            patch("loghop.cli_commands._admin_uninstall.install_claude_hooks", return_value=[]),
            patch(
                "loghop.cli_commands._admin_uninstall.install_codex_shim",
                return_value={"action": "removed"},
            ),
            patch("loghop.cli_commands._admin_uninstall.install_loghop_prompt", return_value=[]),
            patch("loghop.cli_commands._admin_uninstall._emit_reports", return_value=0),
            patch("loghop.cli_commands._admin_uninstall.save_codex_shim_prefix"),
            patch("loghop.cli_commands._admin_uninstall.clear_tracked_project_roots"),
        ):
            code = handle_uninstall(args, term)
        assert code == 0
        cast(Any, term).confirm.assert_not_called()


class TestUninstallPurge:
    def test_purge_removes_global_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from loghop.cli_commands._admin_uninstall import handle_uninstall

        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        global_dir = fake_home / ".loghop"
        global_dir.mkdir()
        (global_dir / "config.toml").write_text("test", encoding="utf-8")
        monkeypatch.setenv("HOME", str(fake_home))

        term = _term()
        args = _args(yes=True, purge=True)

        with (
            patch(
                "loghop.cli_commands._admin_uninstall.load_tracked_project_roots", return_value=[]
            ),
            patch("loghop.cli_commands._admin_uninstall.load_registry", return_value=[]),
            patch("loghop.cli_commands._admin_uninstall.load_codex_shim_prefix", return_value=None),
            patch("loghop.cli_commands._admin_uninstall.install_claude_hooks", return_value=[]),
            patch(
                "loghop.cli_commands._admin_uninstall.install_codex_shim",
                return_value={"action": "removed"},
            ),
            patch("loghop.cli_commands._admin_uninstall.install_loghop_prompt", return_value=[]),
            patch("loghop.cli_commands._admin_uninstall._emit_reports", return_value=0),
            patch("loghop.cli_commands._admin_uninstall.save_codex_shim_prefix"),
            patch("loghop.cli_commands._admin_uninstall.clear_tracked_project_roots"),
        ):
            code = handle_uninstall(args, term)
        assert code == 0
        assert not global_dir.exists()
        cast(Any, term).success.assert_called()


class TestUninstallKeepConfig:
    def test_keep_config_preserves_global_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from loghop.cli_commands._admin_uninstall import handle_uninstall

        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))

        with patch(
            "loghop.install._config.global_config_path", return_value=fake_home / "loghop.toml"
        ):
            cfg = fake_home / "loghop.toml"
            cfg.write_text("version = 1\n", encoding="utf-8")

            term = _term()
            args = _args(yes=True, keep_config=True)

            with (
                patch(
                    "loghop.cli_commands._admin_uninstall.load_tracked_project_roots",
                    return_value=[],
                ),
                patch("loghop.cli_commands._admin_uninstall.load_registry", return_value=[]),
                patch(
                    "loghop.cli_commands._admin_uninstall.load_codex_shim_prefix", return_value=None
                ),
                patch("loghop.cli_commands._admin_uninstall.install_claude_hooks", return_value=[]),
                patch(
                    "loghop.cli_commands._admin_uninstall.install_codex_shim",
                    return_value={"action": "removed"},
                ),
                patch(
                    "loghop.cli_commands._admin_uninstall.install_loghop_prompt", return_value=[]
                ),
                patch("loghop.cli_commands._admin_uninstall._emit_reports", return_value=0),
                patch("loghop.cli_commands._admin_uninstall.save_codex_shim_prefix"),
                patch("loghop.cli_commands._admin_uninstall.clear_tracked_project_roots"),
            ):
                handle_uninstall(args, term)
            assert cfg.exists()


class TestUninstallClearsState:
    def test_clears_shim_prefix_and_tracked_roots(self) -> None:
        from loghop.cli_commands._admin_uninstall import handle_uninstall

        term = _term()
        args = _args(yes=True)

        with (
            patch(
                "loghop.cli_commands._admin_uninstall.load_tracked_project_roots", return_value=[]
            ),
            patch("loghop.cli_commands._admin_uninstall.load_registry", return_value=[]),
            patch("loghop.cli_commands._admin_uninstall.load_codex_shim_prefix", return_value=None),
            patch("loghop.cli_commands._admin_uninstall.install_claude_hooks", return_value=[]),
            patch(
                "loghop.cli_commands._admin_uninstall.install_codex_shim",
                return_value={"action": "removed"},
            ),
            patch("loghop.cli_commands._admin_uninstall.install_loghop_prompt", return_value=[]),
            patch("loghop.cli_commands._admin_uninstall._emit_reports", return_value=0),
            patch("loghop.cli_commands._admin_uninstall.save_codex_shim_prefix") as save_mock,
            patch("loghop.cli_commands._admin_uninstall.clear_tracked_project_roots") as clear_mock,
        ):
            handle_uninstall(args, term)
        save_mock.assert_called_once_with(None)
        clear_mock.assert_called_once()
