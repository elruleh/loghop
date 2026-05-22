"""Unit tests for install submodules — edge cases not covered by CLI tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

import pytest

# ---------------------------------------------------------------------------
# install/_hooks.py
# ---------------------------------------------------------------------------


class TestInstallClaudeHooksUnit:
    def test_returns_empty_when_settings_path_is_none(self, tmp_path: Path) -> None:
        from loghop.install._hooks import install_claude_hooks

        # scope_user=False with no project_root → settings_path is None
        result = install_claude_hooks(scope_user=False, project_root=None)
        assert result == []

    def test_project_scope_uses_project_root(self, tmp_path: Path) -> None:
        from loghop.install._hooks import install_claude_hooks

        result = install_claude_hooks(scope_user=False, project_root=tmp_path)
        assert len(result) == 1
        assert result[0].action in ("updated", "created", "unchanged")

    def test_errors_when_hooks_block_not_dict(self, tmp_path: Path) -> None:
        from loghop.install._hooks import _ensure_claude_hooks

        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"hooks": "not a dict"}), encoding="utf-8")
        report = _ensure_claude_hooks(path, dry_run=False)
        assert report.action == "error"
        assert "not an object" in (report.detail or "")

    def test_errors_when_event_list_not_a_list(self, tmp_path: Path) -> None:
        from loghop.install._hooks import _ensure_claude_hooks

        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"hooks": {"SessionStart": "bad"}}), encoding="utf-8")
        report = _ensure_claude_hooks(path, dry_run=False)
        assert report.action == "error"
        assert "not a list" in (report.detail or "")

    def test_errors_when_settings_json_corrupt(self, tmp_path: Path) -> None:
        from loghop.install._hooks import _ensure_claude_hooks

        path = tmp_path / "settings.json"
        path.write_text("{not json", encoding="utf-8")
        report = _ensure_claude_hooks(path, dry_run=False)
        assert report.action == "error"
        assert "valid JSON" in (report.detail or "")

    @pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
    def test_errors_when_settings_path_is_symlink(self, tmp_path: Path) -> None:
        from loghop.install._hooks import _ensure_claude_hooks

        target = tmp_path / "real-settings.json"
        target.write_text(json.dumps({"hooks": {}}), encoding="utf-8")
        path = tmp_path / "settings.json"
        path.symlink_to(target)

        report = _ensure_claude_hooks(path, dry_run=False)
        assert report.action == "error"
        assert "symlink" in (report.detail or "")

    def test_claude_hook_entries_use_absolute_launcher_and_timeouts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from loghop.install._hooks import _claude_hook_entries

        monkeypatch.setattr(
            "loghop.install._hooks.shutil.which", lambda _name: "/opt/loghop/bin/loghop"
        )

        entries = _claude_hook_entries()
        start_hook = cast(Any, entries)["SessionStart"][0]["hooks"][0]
        end_hook = cast(Any, entries)["SessionEnd"][0]["hooks"][0]

        assert start_hook["command"] == "/opt/loghop/bin/loghop hook claude-session-start"
        assert start_hook["timeout"] == 10
        assert end_hook["command"] == "/opt/loghop/bin/loghop hook claude-session-end"
        assert end_hook["timeout"] == 30

    def test_remove_returns_unchanged_when_file_absent(self, tmp_path: Path) -> None:
        from loghop.install._hooks import _remove_claude_hooks

        report = _remove_claude_hooks(tmp_path / "nonexistent.json", dry_run=False)
        assert report.action == "unchanged"

    def test_remove_returns_unchanged_when_no_hooks_block(self, tmp_path: Path) -> None:
        from loghop.install._hooks import _remove_claude_hooks

        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"other": 1}), encoding="utf-8")
        report = _remove_claude_hooks(path, dry_run=False)
        assert report.action == "unchanged"

    def test_remove_returns_unchanged_when_no_loghop_hooks(self, tmp_path: Path) -> None:
        from loghop.install._hooks import _remove_claude_hooks

        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps({"hooks": {"SessionStart": [{"type": "command", "command": "other"}]}}),
            encoding="utf-8",
        )
        report = _remove_claude_hooks(path, dry_run=False)
        assert report.action == "unchanged"

    def test_remove_skips_non_list_event(self, tmp_path: Path) -> None:
        from loghop.install._hooks import _remove_claude_hooks

        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps({"hooks": {"SessionStart": "not a list", "SessionEnd": []}}),
            encoding="utf-8",
        )
        report = _remove_claude_hooks(path, dry_run=False)
        assert report.action == "unchanged"

    def test_is_loghop_hook_entry_non_dict(self) -> None:
        from loghop.install._hooks import _is_loghop_hook_entry

        assert _is_loghop_hook_entry("string") is False
        assert _is_loghop_hook_entry(42) is False

    def test_is_loghop_hook_entry_hooks_not_list(self) -> None:
        from loghop.install._hooks import _is_loghop_hook_entry

        assert _is_loghop_hook_entry({"hooks": "not a list"}) is False

    def test_uninstall_removes_loghop_hooks(self, tmp_path: Path) -> None:
        from loghop.install._hooks import install_claude_hooks

        # First install, then uninstall
        install_claude_hooks(scope_user=False, project_root=tmp_path)
        result = install_claude_hooks(scope_user=False, project_root=tmp_path, uninstall=True)
        assert result[0].action == "updated"

    def test_install_reports_error_when_lock_path_validation_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from loghop.install._hooks import install_claude_hooks

        def _boom(_path: Path) -> None:
            raise ValueError("refusing to use symlinked path component")

        monkeypatch.setattr("loghop.install._hooks.project_lock", _boom)

        reports = install_claude_hooks(scope_user=False, project_root=tmp_path)
        assert reports
        assert reports[0].action == "error"
        assert "symlinked path component" in (reports[0].detail or "")


class TestInstallConfigBackupUnit:
    @pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
    def test_backup_rejects_symlink(self, tmp_path: Path) -> None:
        from loghop.install._config import _backup

        target = tmp_path / "real.txt"
        target.write_text("secret\n", encoding="utf-8")
        link = tmp_path / "AGENTS.md"
        link.symlink_to(target)

        assert _backup(link) is None
        assert not (tmp_path / "AGENTS.md.loghop.bak").exists()


# ---------------------------------------------------------------------------
# install/_prompt.py
# ---------------------------------------------------------------------------


class TestInstallPromptUnit:
    def test_entry_file_none_for_unknown_target(self) -> None:
        from loghop.install._prompt import _entry_file_for

        assert _entry_file_for("unknown", True, None) is None

    def test_entry_file_project_scope_codex(self, tmp_path: Path) -> None:
        from loghop.install._prompt import _entry_file_for

        result = _entry_file_for("codex", False, tmp_path)
        assert result == tmp_path / "AGENTS.md"

    def test_entry_file_project_scope_claude(self, tmp_path: Path) -> None:
        from loghop.install._prompt import _entry_file_for

        result = _entry_file_for("claude", False, tmp_path)
        assert result == tmp_path / "CLAUDE.md"

    def test_entry_file_project_scope_returns_none_without_root(self) -> None:
        from loghop.install._prompt import _entry_file_for

        assert _entry_file_for("codex", False, None) is None
        assert _entry_file_for("claude", False, None) is None

    def test_uninstall_skips_none_entry(self, tmp_path: Path) -> None:
        from loghop.install._prompt import install_loghop_prompt

        # scope_user=False with no root → entries are None → skipped silently
        result = install_loghop_prompt(scope_user=False, project_root=None, uninstall=True)
        assert result == []

    def test_project_scope_uses_local_prompt_and_relative_include(self, tmp_path: Path) -> None:
        from loghop.install._prompt import install_loghop_prompt

        install_loghop_prompt(scope_user=False, project_root=tmp_path, targets=("codex",))

        prompt = tmp_path / ".loghop" / "loghop-prompt.md"
        entry = tmp_path / "AGENTS.md"
        assert prompt.exists()
        assert "@.loghop/loghop-prompt.md" in entry.read_text(encoding="utf-8")
        assert str(Path.home() / ".loghop" / "loghop-prompt.md") not in entry.read_text(
            encoding="utf-8"
        )

    def test_project_scope_uninstall_removes_unused_local_prompt_file(self, tmp_path: Path) -> None:
        from loghop.install._prompt import install_loghop_prompt

        install_loghop_prompt(scope_user=False, project_root=tmp_path, targets=("codex",))

        result = install_loghop_prompt(scope_user=False, project_root=tmp_path, uninstall=True)
        prompt = tmp_path / ".loghop" / "loghop-prompt.md"
        assert not prompt.exists()
        assert any(report.path.name == "loghop-prompt.md" for report in result)

    def test_project_scope_install_replaces_legacy_global_include(self, tmp_path: Path) -> None:
        from loghop.install._prompt import install_loghop_prompt

        legacy = Path.home() / ".loghop" / "loghop-prompt.md"
        entry = tmp_path / "AGENTS.md"
        entry.write_text(f"@{legacy}\n", encoding="utf-8")

        install_loghop_prompt(scope_user=False, project_root=tmp_path, targets=("codex",))

        body = entry.read_text(encoding="utf-8")
        assert "@.loghop/loghop-prompt.md" in body
        assert f"@{legacy}" not in body

    def test_partial_user_uninstall_keeps_shared_prompt_file_when_other_target_uses_it(
        self,
    ) -> None:
        from loghop.install._prompt import install_loghop_prompt

        install_loghop_prompt(targets=("codex", "claude"))

        reports = install_loghop_prompt(targets=("codex",), uninstall=True)

        prompt = Path.home() / ".loghop" / "loghop-prompt.md"
        claude_entry = Path.home() / ".claude" / "CLAUDE.md"
        assert prompt.exists()
        assert str(prompt) in claude_entry.read_text(encoding="utf-8")
        assert all(report.path.name != "loghop-prompt.md" for report in reports)

    def test_installed_targets_reports_partial_prompt_install(self) -> None:
        from loghop.install._prompt import install_loghop_prompt, loghop_prompt_installed_targets

        install_loghop_prompt(targets=("codex",))

        assert loghop_prompt_installed_targets() == ("codex",)

    def test_install_skips_none_entry(self, tmp_path: Path) -> None:
        from loghop.install._prompt import install_loghop_prompt

        # unknown target → _entry_file_for returns None → skipped
        result = install_loghop_prompt(scope_user=True, targets=("unknown_target",))
        # Only the prompt-file write report — no entry-file report
        assert len(result) == 1

    def test_remove_include_line_absent_file(self, tmp_path: Path) -> None:
        from loghop.install._prompt import _remove_include_line

        report = _remove_include_line(tmp_path / "AGENTS.md", "@/some/path", dry_run=False)
        assert report.action == "unchanged"
        assert "absent" in (report.detail or "")

    def test_remove_include_line_not_present(self, tmp_path: Path) -> None:
        from loghop.install._prompt import _remove_include_line

        f = tmp_path / "AGENTS.md"
        f.write_text("# existing content\n", encoding="utf-8")
        report = _remove_include_line(f, "@/not/here", dry_run=False)
        assert report.action == "unchanged"
        assert "not present" in (report.detail or "")

    def test_ensure_include_line_idempotent(self, tmp_path: Path) -> None:
        from loghop.install._prompt import _ensure_include_line

        f = tmp_path / "CLAUDE.md"
        include = "@/some/prompt.md"
        f.write_text(include + "\n", encoding="utf-8")
        report = _ensure_include_line(f, include, dry_run=False)
        assert report.action == "unchanged"

    def test_write_prompt_file_unchanged_when_identical(self, tmp_path: Path) -> None:
        from loghop.install._prompt import _write_prompt_file
        from loghop.install._types import _LOGHOP_PROMPT_BODY

        path = tmp_path / "loghop-prompt.md"
        path.write_text(_LOGHOP_PROMPT_BODY, encoding="utf-8")
        report = _write_prompt_file(path, dry_run=False)
        assert report.action == "unchanged"


# ---------------------------------------------------------------------------
# install/_shim.py
# ---------------------------------------------------------------------------


class TestInstallShimUnit:
    def test_uninstall_returns_unchanged_when_no_shim(self, tmp_path: Path) -> None:
        from loghop.install._shim import install_codex_shim

        report = install_codex_shim(prefix=tmp_path, uninstall=True)
        assert report.action == "unchanged"
        assert "no shim" in (report.detail or "")

    def test_uninstall_skips_non_loghop_file(self, tmp_path: Path) -> None:
        from loghop.install._shim import install_codex_shim

        shim = tmp_path / "codex"
        shim.write_text("#!/bin/sh\necho hello\n", encoding="utf-8")
        report = install_codex_shim(prefix=tmp_path, uninstall=True)
        assert report.action == "skipped"
        assert "not a loghop shim" in (report.detail or "")

    def test_is_loghop_shim_returns_false_for_non_loghop(self, tmp_path: Path) -> None:
        from loghop.install._shim import _is_loghop_shim

        f = tmp_path / "script.sh"
        f.write_text("#!/bin/sh\necho nope\n", encoding="utf-8")
        assert _is_loghop_shim(f) is False

    def test_is_loghop_shim_returns_false_on_oserror(self, tmp_path: Path) -> None:
        from loghop.install._shim import _is_loghop_shim

        assert _is_loghop_shim(tmp_path / "missing.sh") is False

    def test_prefix_is_first_in_path_empty_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from loghop.install._shim import _prefix_is_first_in_path

        monkeypatch.setenv("PATH", "")
        assert _prefix_is_first_in_path(tmp_path) is False

    def test_shim_body_contains_expected_content(self) -> None:
        from loghop.install._shim import _shim_body

        body = _shim_body("codex", "/usr/bin/codex")
        assert "loghop wrap codex" in body
        assert "LOGHOP_REAL_CODEX" in body


# ---------------------------------------------------------------------------
# install/_config.py
# ---------------------------------------------------------------------------


class TestInstallConfigUnit:
    def test_read_json_or_empty_returns_empty_on_bad_json(self, tmp_path: Path) -> None:
        from loghop.install._config import _read_json_or_empty

        f = tmp_path / "bad.json"
        f.write_text("{invalid", encoding="utf-8")
        assert _read_json_or_empty(f) == {}

    def test_read_json_or_empty_returns_empty_for_non_dict(self, tmp_path: Path) -> None:
        from loghop.install._config import _read_json_or_empty

        f = tmp_path / "arr.json"
        f.write_text("[1, 2, 3]", encoding="utf-8")
        assert _read_json_or_empty(f) == {}

    def test_load_init_install_choices_returns_none_for_non_bool_value(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import tomllib

        from loghop.install._config import load_init_install_choices
        from loghop.install._types import INIT_INSTALL_KEYS

        # Build a TOML config with a non-bool value for the first key
        key = next(iter(INIT_INSTALL_KEYS))
        toml_lines = ["[install]"] + [
            f"{k} = {'true' if k != key else '42'}" for k in INIT_INSTALL_KEYS
        ]
        toml_content = "\n".join(toml_lines) + "\n"

        def fake_load_config() -> dict[str, Any]:
            return tomllib.loads(toml_content)

        monkeypatch.setattr("loghop.install._config._load_global_config", fake_load_config)
        result = load_init_install_choices()
        assert result is None

    def test_save_init_install_choices_with_non_dict_install(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from loghop.install._config import save_init_install_choices
        from loghop.install._types import INIT_INSTALL_KEYS, InitInstallChoices

        # Patch global_config_path to tmp_path file and seed with non-dict install
        config_path = tmp_path / "config.toml"
        config_path.write_text("", encoding="utf-8")

        captured: dict[str, Any] = {}

        def fake_load() -> dict[str, Any]:
            return {"install": "not-a-dict"}

        def fake_save(config: dict[str, Any]) -> None:
            captured["config"] = config

        monkeypatch.setattr("loghop.install._config._load_global_config", fake_load)
        monkeypatch.setattr("loghop.install._config._save_global_config", fake_save)

        choices = InitInstallChoices(**dict.fromkeys(INIT_INSTALL_KEYS, True))
        save_init_install_choices(choices)

        assert isinstance(captured["config"]["install"], dict)
