from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from unittest.mock import patch

from loghop.cli_commands._admin_completion import (
    _bash_completion,
    _collect_top_level_commands,
    _fish_completion,
    _zsh_completion,
    handle_completion,
)
from loghop.cli_commands._admin_doctor import handle_doctor
from loghop.cli_commands._admin_init import (
    _collect_rollback_ops,
    _rollback,
    _RollbackOp,
)
from loghop.cli_commands._admin_providers import handle_providers_list
from loghop.install._types import InstallReport
from loghop.terminal import Terminal, TerminalOptions

_DOCTOR = "loghop.cli_commands._admin_doctor"
_PROVIDERS = "loghop.cli_commands._admin_providers"


def _git_init_with_commit(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=root, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)
    (root / "a.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True, capture_output=True)


def _plain_term() -> Terminal:
    return Terminal(options=TerminalOptions(plain=True))


class TestCollectRollbackOps:
    def test_created_file_no_backup(self) -> None:
        reports = [InstallReport(path=Path("/fake/created.md"), action="created")]
        ops = _collect_rollback_ops(reports)
        assert len(ops) == 1
        assert ops[0].remove_created is True
        assert ops[0].restore_from is None

    def test_updated_file_with_backup(self, tmp_path: Path) -> None:
        target = tmp_path / "config.json"
        target.write_text("{}")
        bak = tmp_path / "config.json.loghop.bak"
        bak.write_text("{old}")
        reports = [InstallReport(path=target, action="updated")]
        ops = _collect_rollback_ops(reports)
        assert len(ops) == 1
        assert ops[0].restore_from == bak
        assert ops[0].remove_created is False

    def test_skipped_action_ignored(self) -> None:
        reports = [InstallReport(path=Path("/fake/skip"), action="skipped")]
        ops = _collect_rollback_ops(reports)
        assert ops == []

    def test_unchanged_action_ignored(self) -> None:
        reports = [InstallReport(path=Path("/fake/same"), action="unchanged")]
        ops = _collect_rollback_ops(reports)
        assert ops == []


class TestRollback:
    def test_rollback_restore(self, tmp_path: Path) -> None:
        target = tmp_path / "file.txt"
        target.write_text("new content")
        bak = tmp_path / "file.txt.loghop.bak"
        bak.write_text("old content")
        term = _plain_term()
        ops = [_RollbackOp(path=target, restore_from=bak)]
        _rollback(ops, term)
        assert target.read_text() == "old content"

    def test_rollback_remove_created(self, tmp_path: Path) -> None:
        target = tmp_path / "new_file.txt"
        target.write_text("created")
        term = _plain_term()
        ops = [_RollbackOp(path=target, remove_created=True)]
        _rollback(ops, term)
        assert not target.exists()

    def test_rollback_empty_ops(self) -> None:
        term = _plain_term()
        _rollback([], term)

    def test_rollback_reverse_order(self, tmp_path: Path) -> None:
        f1 = tmp_path / "first.txt"
        f2 = tmp_path / "second.txt"
        f1.write_text("a")
        f2.write_text("b")
        term = _plain_term()
        ops = [
            _RollbackOp(path=f1, remove_created=True),
            _RollbackOp(path=f2, remove_created=True),
        ]
        _rollback(ops, term)
        assert not f1.exists()
        assert not f2.exists()


class TestCompletion:
    def test_bash_completion(self) -> None:
        cmds = ["init", "goal", "status"]
        script = _bash_completion(cmds)
        assert "_loghop_complete" in script
        assert "init" in script
        assert "goal" in script
        assert "complete -F" in script

    def test_zsh_completion(self) -> None:
        cmds = ["init", "goal"]
        script = _zsh_completion(cmds)
        assert "#compdef loghop" in script
        assert "init" in script

    def test_fish_completion(self) -> None:
        cmds = ["init", "goal", "status"]
        script = _fish_completion(cmds)
        assert "complete -c loghop" in script
        assert "init" in script

    def test_collect_top_level_commands(self) -> None:
        cmds = _collect_top_level_commands()
        assert "init" in cmds
        assert "run" in cmds
        assert "goal" in cmds
        assert "handoff" in cmds
        assert "status" not in cmds
        assert "install-prompt" not in cmds
        assert "install-hooks" not in cmds
        assert "install-shims" not in cmds
        assert "hook" not in cmds


class TestHandleCompletion:
    def test_bash_shell(self) -> None:
        term = _plain_term()
        args = argparse.Namespace(shell="bash")
        code = handle_completion(args, term)
        assert code == 0
        assert term._result["shell"] == "bash"
        assert isinstance(term._result["commands"], list)

    def test_zsh_shell(self) -> None:
        term = _plain_term()
        args = argparse.Namespace(shell="zsh")
        code = handle_completion(args, term)
        assert code == 0

    def test_fish_shell(self) -> None:
        term = _plain_term()
        args = argparse.Namespace(shell="fish")
        code = handle_completion(args, term)
        assert code == 0


class TestHandleDoctor:
    def test_all_missing(self) -> None:
        term = _plain_term()
        with (
            patch(f"{_DOCTOR}.claude_hooks_installed", return_value=False),
            patch(f"{_DOCTOR}.codex_shim_installed", return_value=False),
            patch(f"{_DOCTOR}.loghop_prompt_installed", return_value=False),
            patch(f"{_DOCTOR}.load_init_install_choices", return_value=None),
            patch(f"{_DOCTOR}.load_installed_version", return_value=None),
            patch(f"{_DOCTOR}.shutil.which", return_value="/usr/bin/loghop"),
        ):
            args = argparse.Namespace(fix=False)
            code = handle_doctor(args, term)
            assert code == 1
            assert term._result["ok"] is False
            assert len(term._result["problems"]) >= 3

    def test_all_ok(self) -> None:
        term = _plain_term()
        with (
            patch(f"{_DOCTOR}.claude_hooks_installed", return_value=True),
            patch(f"{_DOCTOR}.codex_shim_installed", return_value=True),
            patch(f"{_DOCTOR}.loghop_prompt_installed", return_value=True),
            patch(f"{_DOCTOR}.load_init_install_choices", return_value=None),
            patch("loghop.install._config.load_installed_version", return_value="0.1.0"),
            patch(f"{_DOCTOR}.shutil.which", return_value="/usr/bin/loghop"),
            patch(f"{_DOCTOR}._detect_real_binary", return_value="/usr/bin/codex"),
            patch(f"{_DOCTOR}._prefix_in_path", return_value=True),
            patch(f"{_DOCTOR}._prefix_is_first_in_path", return_value=True),
            patch(f"{_DOCTOR}.load_installed_version", return_value="0.1.0"),
            patch("loghop.__version__", "0.1.0", create=True),
        ):
            args = argparse.Namespace(fix=False)
            code = handle_doctor(args, term)
            assert code == 0
            assert term._result["ok"] is True

    def test_opted_out_not_counted_as_problem(self) -> None:
        from loghop.install._types import InitInstallChoices

        term = _plain_term()
        choices = InitInstallChoices(
            install_claude_hooks=False,
            install_codex_shim=False,
            install_prompt_block=False,
        )
        with (
            patch(f"{_DOCTOR}.claude_hooks_installed", return_value=False),
            patch(f"{_DOCTOR}.codex_shim_installed", return_value=False),
            patch(f"{_DOCTOR}.loghop_prompt_installed", return_value=False),
            patch(f"{_DOCTOR}.load_init_install_choices", return_value=choices),
            patch(f"{_DOCTOR}.load_installed_version", return_value=None),
            patch(f"{_DOCTOR}.shutil.which", return_value="/usr/bin/loghop"),
        ):
            args = argparse.Namespace(fix=False)
            code = handle_doctor(args, term)
            assert code == 0
            assert term._result["ok"] is True
            skipped = [c for c in term._result["components"] if c["state"] == "skipped"]
            assert len(skipped) == 3

    def test_path_warning_does_not_fail_doctor(self) -> None:
        term = _plain_term()
        with (
            patch(f"{_DOCTOR}.claude_hooks_installed", return_value=True),
            patch(f"{_DOCTOR}.codex_shim_installed", return_value=True),
            patch(f"{_DOCTOR}.loghop_prompt_installed", return_value=True),
            patch(f"{_DOCTOR}.load_init_install_choices", return_value=None),
            patch(f"{_DOCTOR}.load_installed_version", return_value="0.1.0"),
            patch(f"{_DOCTOR}.shutil.which", return_value="/usr/bin/loghop"),
            patch(f"{_DOCTOR}._detect_real_binary", return_value="/usr/bin/codex"),
            patch(f"{_DOCTOR}._prefix_in_path", return_value=True),
            patch(f"{_DOCTOR}._prefix_is_first_in_path", return_value=False),
            patch("loghop.__version__", "0.1.0", create=True),
        ):
            args = argparse.Namespace(fix=False)
            code = handle_doctor(args, term)
            assert code == 0
            assert term._result["ok"] is True
            shim = next(c for c in term._result["components"] if c["name"] == "codex-shim")
            assert shim["state"] == "warn"


class TestHandleProvidersList:
    def test_lists_providers(self) -> None:
        term = _plain_term()
        args = argparse.Namespace()
        with patch(f"{_PROVIDERS}.detect_all") as mock_detect:
            mock_detect.return_value = {
                "codex": type("D", (), {"installed": True, "path": "/usr/bin/codex"})(),
                "claude": type("D", (), {"installed": False, "path": None})(),
            }
            code = handle_providers_list(args, term)
            assert code == 0
            assert term._result["providers"]["codex"]["installed"] is True
            assert term._result["providers"]["claude"]["installed"] is False
