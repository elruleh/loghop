from __future__ import annotations

import json
import os
import stat
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from loghop.cli import main
from loghop.cli_commands.backup import handle_backup_create, handle_backup_restore
from loghop.cli_commands.health import handle_health
from loghop.cli_commands.metrics import collect_metrics, handle_metrics
from loghop.cli_commands.migrate import handle_migrate
from loghop.store import create_handoff, create_session, finish_session, project_paths
from loghop.store._io import safe_read_text
from loghop.terminal import Terminal, TerminalOptions


def _term() -> Terminal:
    return Terminal(TerminalOptions(plain=True))


def test_health_reports_initialized_project(
    initialized_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(initialized_repo)
    term = _term()

    code = handle_health(SimpleNamespace(), term)

    assert code == 0
    assert term._result["healthy"] is True
    assert {check["name"] for check in term._result["checks"]} >= {
        "project_initialized",
        "git_repository",
        "loghop_directory",
        "config_file",
        "timeline_file",
    }


def test_health_returns_not_initialized_outside_project(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)
    term = _term()

    code = handle_health(SimpleNamespace(), term)

    assert code == 20
    assert term._result["healthy"] is False
    assert term._result["checks"][0]["status"] == "fail"


def test_metrics_counts_project_artifacts(initialized_repo: Path) -> None:
    create_handoff(initialized_repo, "codex", "ship")
    session = create_session(initialized_repo, provider="codex", goal="ship", handoff_id="H-001")
    finish_session(initialized_repo, session.id, status="succeeded", returncode=0)

    metrics = collect_metrics(initialized_repo)

    assert metrics["sessions_total"] == 1
    assert metrics["handoffs_total"] == 1
    assert metrics["timeline_events_total"] == 1
    assert metrics["sessions_by_status"]["succeeded"] == 1


def test_metrics_handler_can_emit_prometheus_text(
    initialized_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(initialized_repo)
    term = _term()

    code = handle_metrics(SimpleNamespace(format="prometheus"), term)

    assert code == 0
    assert "loghop_sessions_total" in term._result["text"]


def test_backup_create_rejects_symlink_output(initialized_repo: Path, tmp_path: Path) -> None:
    output = tmp_path / "backup.tar.gz"
    outside = tmp_path / "outside.tar.gz"
    outside.write_text("", encoding="utf-8")
    output.symlink_to(outside)

    with pytest.raises(ValueError, match="symlinked backup output"):
        handle_backup_create(SimpleNamespace(output=str(output)), _term())


def test_backup_create_and_restore_round_trip(initialized_repo: Path, tmp_path: Path) -> None:
    (initialized_repo / "loghop.md").write_text("memory\n", encoding="utf-8")
    output = tmp_path / "backup.tar.gz"
    create_term = _term()

    code = handle_backup_create(SimpleNamespace(output=str(output)), create_term)

    assert code == 0
    assert output.exists()
    if os.name != "nt":
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert create_term._result["archive"] == str(output)

    paths = project_paths(initialized_repo)
    paths.config.unlink()
    (initialized_repo / "loghop.md").unlink()
    restore_term = _term()

    code = handle_backup_restore(SimpleNamespace(archive=str(output), yes=True), restore_term)

    assert code == 0
    assert paths.config.exists()
    assert (initialized_repo / "loghop.md").read_text(encoding="utf-8") == "memory\n"


def test_backup_restore_rejects_existing_symlink_target(
    initialized_repo: Path, tmp_path: Path
) -> None:
    output = tmp_path / "backup.tar.gz"
    assert handle_backup_create(SimpleNamespace(output=str(output)), _term()) == 0
    config_path = project_paths(initialized_repo).config
    config_path.unlink()
    outside = tmp_path / "outside.toml"
    outside.write_text("", encoding="utf-8")
    config_path.symlink_to(outside)

    with pytest.raises(ValueError, match="symlinked restore target"):
        handle_backup_restore(SimpleNamespace(archive=str(output), yes=True), _term())


def test_backup_restore_rejects_traversal_archive(initialized_repo: Path, tmp_path: Path) -> None:
    archive = tmp_path / "evil.tar.gz"
    payload = tmp_path / "payload.txt"
    payload.write_text("owned", encoding="utf-8")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(payload, arcname="../owned.txt")

    term = _term()

    with pytest.raises(ValueError, match="unsafe backup member"):
        handle_backup_restore(SimpleNamespace(archive=str(archive), yes=True), term)


def test_migrate_updates_old_config_version(
    initialized_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = project_paths(initialized_repo)
    paths.config.write_text('version = 0\nproject_name = "old"\n', encoding="utf-8")
    monkeypatch.chdir(initialized_repo)
    term = _term()

    code = handle_migrate(SimpleNamespace(dry_run=False), term)

    assert code == 0
    assert "version = 1" in safe_read_text(paths.config)
    assert term._result["changed"] is True


def test_migrate_dry_run_does_not_write(
    initialized_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = project_paths(initialized_repo)
    paths.config.write_text('version = 0\nproject_name = "old"\n', encoding="utf-8")
    monkeypatch.chdir(initialized_repo)
    term = _term()

    code = handle_migrate(SimpleNamespace(dry_run=True), term)

    assert code == 0
    assert "version = 0" in safe_read_text(paths.config)
    assert term._result["changed"] is True


def test_cli_json_metrics_is_sanitized(
    initialized_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(initialized_repo)

    code = main(["--json", "metrics"])

    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["result"]["sessions_total"] == 0
