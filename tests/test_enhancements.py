from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

import pytest

from loghop.cli_commands.metrics import handle_metrics
from loghop.install import codex_shim_installed, install_aliases, install_codex_shim
from loghop.install._shim import _shim_body
from loghop.redact import _clear_redact_cache, redact_text
from loghop.terminal import Terminal

# --- 1. Windows Shim Support Tests ---


def test_windows_shim_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    # Test batch file body formatting when sys.platform starts with win
    body = _shim_body("codex", "C:\\path\\to\\codex.exe")
    assert "@echo off" in body
    assert "set LOGHOP_REAL_CODEX=C:\\path\\to\\codex.exe" in body
    assert "loghop wrap codex %*" in body


def test_windows_install_and_uninstall(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Force sys.platform to windows (but keep os.name as posix so pathlib works)
    monkeypatch.setattr(sys, "platform", "win32")

    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    real_codex = real_dir / "codex"
    real_codex.write_text("dummy", encoding="utf-8")

    # Mock shutil.which to avoid C-level _winapi dependencies on Linux
    monkeypatch.setattr(shutil, "which", lambda cmd, path=None: str(real_codex))
    monkeypatch.setenv("PATH", f"{install_dir}{os.pathsep}{real_dir}")

    # Install
    report = install_codex_shim(prefix=install_dir, binary="codex")
    assert report.action == "created"
    shim_file = install_dir / "codex.cmd"
    assert shim_file.exists()

    body = shim_file.read_text(encoding="utf-8")
    assert "@echo off" in body

    assert codex_shim_installed(prefix=install_dir, binary="codex") is True

    # Uninstall
    report_un = install_codex_shim(prefix=install_dir, binary="codex", uninstall=True)
    assert report_un.action == "removed"
    assert not shim_file.exists()


# --- 2. Custom Secrets Redaction Patterns Tests ---


def test_custom_redaction_patterns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Setup mock paths
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    global_config = global_dir / "config.toml"
    global_config.write_text(
        '[[redaction]]\npattern = "MY_SUPER_SECRET_\\\\d+"\nreplacement = "[custom global redacted]"\n',
        encoding="utf-8",
    )

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    project_dot = project_dir / ".loghop"
    project_dot.mkdir()
    project_config = project_dot / "config.toml"
    project_config.write_text(
        '[[redaction]]\npattern = "MY_PROJECT_SECRET=[^&\\\\s]+"\nreplacement = "MY_PROJECT_SECRET=[redacted custom]"\n',
        encoding="utf-8",
    )

    # Mock global_config_path
    monkeypatch.setattr("loghop.install._config.global_config_path", lambda: global_config)
    # Mock find_project_root
    monkeypatch.setattr("loghop.store.find_project_root", lambda _p: project_dir)
    # Mock Cwd with a classmethod-compatible lambda
    monkeypatch.setattr(Path, "cwd", lambda *args, **kwargs: project_dir)

    _clear_redact_cache()

    # Verify custom rules are applied
    txt1 = "Here is my key: MY_SUPER_SECRET_12345"
    redacted1 = redact_text(txt1)
    assert "[custom global redacted]" in redacted1
    assert "12345" not in redacted1

    txt2 = "Key value: MY_PROJECT_SECRET=secret_val"
    redacted2 = redact_text(txt2)
    assert "MY_PROJECT_SECRET=[redacted custom]" in redacted2
    assert "secret_val" not in redacted2

    _clear_redact_cache()


# --- 3. JSON/YAML Metrics Formatting Tests ---


class MockTerminal(Terminal):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self.payload: dict[str, any] | None = None

    def line(self, text: str = "") -> None:
        self.lines.append(text)

    def capture_result(self, data: dict[str, any]) -> None:
        self.payload = data


def test_metrics_json_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    project_dot = project_dir / ".loghop"
    project_dot.mkdir()
    (project_dot / "config.toml").write_text("project_name = 'test'", encoding="utf-8")
    (project_dot / "sessions").mkdir()
    (project_dot / "handoffs").mkdir()

    monkeypatch.setattr("loghop.cli_commands.metrics.find_project_root", lambda _p: project_dir)
    monkeypatch.setattr(
        "loghop.cli_commands.metrics.collect_metrics",
        lambda _r: {
            "sessions_total": 5,
            "handoffs_total": 3,
            "timeline_events_total": 10,
            "sessions_by_status": {"active": 2, "completed": 3},
            "sessions_by_provider": {"claude": 5},
        },
    )

    term = MockTerminal()

    # Test JSON Format
    args = argparse.Namespace(format="json")
    rc = handle_metrics(args, term)
    assert rc == 0
    assert term.payload is not None
    assert term.payload["sessions_total"] == 5
    assert '"sessions_total": 5' in term.lines[0]

    # Test YAML Format
    term = MockTerminal()
    args = argparse.Namespace(format="yaml")
    rc = handle_metrics(args, term)
    assert rc == 0
    assert term.payload is not None
    assert term.payload["handoffs_total"] == 3
    assert "handoffs_total: 3" in term.lines[0]


# --- 4. Automatic Shell Alias Installer Tests ---


def test_alias_install_and_uninstall(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Mock home directory
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    bashrc = tmp_path / ".bashrc"
    zshrc = tmp_path / ".zshrc"
    fish_dir = tmp_path / ".config" / "fish"
    fish_dir.mkdir(parents=True)
    fish_config = fish_dir / "config.fish"

    bashrc.write_text("echo 'hello bash'\n", encoding="utf-8")
    zshrc.write_text("echo 'hello zsh'\n", encoding="utf-8")
    fish_config.write_text("echo 'hello fish'\n", encoding="utf-8")

    # 1. Dry run install
    reports = install_aliases(dry_run=True)
    assert all(r.action.startswith("would-") for r in reports)
    assert "# >>> loghop aliases >>>" not in bashrc.read_text(encoding="utf-8")

    # 2. Real install
    reports = install_aliases()
    assert all(r.action in ("created", "updated") for r in reports)

    bash_content = bashrc.read_text(encoding="utf-8")
    assert "# >>> loghop aliases >>>" in bash_content
    assert "alias claude='loghop wrap claude'" in bash_content
    assert "alias codex='loghop wrap codex'" in bash_content
    assert "# <<< loghop aliases <<<" in bash_content

    # Verify backup exists
    assert (tmp_path / ".bashrc.loghop.bak").exists()

    # 3. Idempotent install
    reports2 = install_aliases()
    assert all(r.action == "unchanged" for r in reports2)

    # 4. Dry run uninstall
    reports_un_dry = install_aliases(uninstall=True, dry_run=True)
    assert all(r.action == "would-remove" for r in reports_un_dry)
    assert "# >>> loghop aliases >>>" in bashrc.read_text(encoding="utf-8")

    # 5. Real uninstall
    reports_un = install_aliases(uninstall=True)
    assert all(r.action == "removed" for r in reports_un)

    bash_un_content = bashrc.read_text(encoding="utf-8")
    assert "# >>> loghop aliases >>>" not in bash_un_content
    assert "alias claude=" not in bash_un_content
