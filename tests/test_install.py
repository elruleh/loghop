from __future__ import annotations

import json
import os
import shlex
from pathlib import Path

import pytest

from loghop.install import (
    install_claude_hooks,
    install_codex_shim,
    install_loghop_prompt,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestPromptInstall:
    def test_creates_prompt_file_and_includes_in_agents(self) -> None:
        _write(Path.home() / ".codex" / "AGENTS.md", "@/home/raul/.codex/RTK.md\n")
        reports = install_loghop_prompt(targets=("codex",))
        actions = {r.path.name: r.action for r in reports}
        assert actions["loghop-prompt.md"] in {"created", "updated"}
        assert actions["AGENTS.md"] == "updated"

        agents_body = (Path.home() / ".codex" / "AGENTS.md").read_text()
        assert "@/home/raul/.codex/RTK.md" in agents_body  # RTK preserved
        assert str(Path.home() / ".loghop" / "loghop-prompt.md") in agents_body

    def test_idempotent(self) -> None:
        install_loghop_prompt(targets=("claude",))
        reports = install_loghop_prompt(targets=("claude",))
        # Second run should be no-op.
        for r in reports:
            assert r.action == "unchanged"

    def test_uninstall_removes_include_line_only(self) -> None:
        # First install so the AGENTS.md has the actual managed include line.
        install_loghop_prompt(targets=("codex",))
        agents_path = Path.home() / ".codex" / "AGENTS.md"
        prompt_path = Path.home() / ".loghop" / "loghop-prompt.md"
        # Add foreign content that must survive uninstall.
        body = agents_path.read_text()
        agents_path.write_text("@/somewhere/foreign.md\n" + body + "\nother content\n")

        reports = install_loghop_prompt(targets=("codex",), uninstall=True)
        result = agents_path.read_text()
        assert "@/somewhere/foreign.md" in result
        assert "other content" in result
        assert "loghop-prompt.md" not in result
        assert not prompt_path.exists()
        assert reports[0].action == "updated"


class TestClaudeHooksInstall:
    def test_merges_into_existing_settings_preserving_rtk(self) -> None:
        settings = {
            "permissions": {"allow": ["Bash(rtk *)"]},
            "model": "opus",
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "rtk hook claude"}],
                    }
                ]
            },
        }
        path = Path.home() / ".claude" / "settings.json"
        _write(path, json.dumps(settings, indent=2))

        reports = install_claude_hooks()
        assert reports[0].action == "updated"

        merged = json.loads(path.read_text())
        # RTK is intact.
        assert merged["permissions"]["allow"] == ["Bash(rtk *)"]
        assert merged["model"] == "opus"
        assert any(
            h["command"] == "rtk hook claude"
            for entry in merged["hooks"]["PreToolUse"]
            for h in entry["hooks"]
        )
        # SessionStart and SessionEnd are added.
        assert "SessionStart" in merged["hooks"]
        assert "SessionEnd" in merged["hooks"]
        start_hook = merged["hooks"]["SessionStart"][0]["hooks"][0]
        argv = shlex.split(start_hook["command"])
        assert argv[-2:] == ["hook", "claude-session-start"]
        assert Path(argv[0]).is_absolute()
        assert start_hook["timeout"] == 10

    def test_idempotent_does_not_duplicate(self) -> None:
        install_claude_hooks()
        install_claude_hooks()
        merged = json.loads((Path.home() / ".claude" / "settings.json").read_text())
        assert len(merged["hooks"]["SessionStart"]) == 1
        assert len(merged["hooks"]["SessionEnd"]) == 1

    def test_uninstall_removes_only_loghop_entries(self) -> None:
        path = Path.home() / ".claude" / "settings.json"
        install_claude_hooks()
        # Add a manual non-loghop SessionStart entry.
        merged = json.loads(path.read_text())
        merged["hooks"].setdefault("SessionStart", []).append(
            {"matcher": "*", "hooks": [{"type": "command", "command": "manual hook"}]}
        )
        path.write_text(json.dumps(merged, indent=2))

        install_claude_hooks(uninstall=True)
        result = json.loads(path.read_text())
        # Manual entry survives, loghop's gone.
        ss = result["hooks"]["SessionStart"]
        assert any(h["command"] == "manual hook" for entry in ss for h in entry["hooks"])
        assert not any("loghop" in h["command"] for entry in ss for h in entry["hooks"])


class TestShimInstall:
    def test_creates_executable_shim(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Provide a fake real binary somewhere in PATH that is NOT the prefix.
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "codex").write_text("#!/bin/sh\necho real\n")
        (real_dir / "codex").chmod(0o755)
        monkeypatch.setenv("PATH", f"{real_dir}:/usr/bin:/bin")

        prefix = tmp_path / "shimbin"
        report = install_codex_shim(prefix=prefix, binary="codex")
        assert report.action in {"created", "updated"}
        shim = prefix / "codex"
        assert shim.exists()
        assert os.access(shim, os.X_OK)
        body = shim.read_text()
        assert "exec loghop wrap codex" in body
        assert str(real_dir / "codex") in body

    def test_skips_when_no_real_binary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PATH", "/nonexistent")
        prefix = tmp_path / "shimbin"
        report = install_codex_shim(prefix=prefix, binary="codex")
        assert report.action == "skipped"
        assert not (prefix / "codex").exists()

    def test_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "codex").write_text("#!/bin/sh\necho real\n")
        (real_dir / "codex").chmod(0o755)
        monkeypatch.setenv("PATH", f"{real_dir}:/usr/bin:/bin")
        prefix = tmp_path / "shimbin"
        install_codex_shim(prefix=prefix, binary="codex")
        again = install_codex_shim(prefix=prefix, binary="codex")
        assert again.action == "unchanged"

    def test_refuses_to_overwrite_foreign_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "codex").write_text("#!/bin/sh\necho real\n")
        (real_dir / "codex").chmod(0o755)
        monkeypatch.setenv("PATH", f"{real_dir}:/usr/bin:/bin")
        prefix = tmp_path / "shimbin"
        prefix.mkdir()
        (prefix / "codex").write_text("#!/bin/sh\necho user-script\n")
        (prefix / "codex").chmod(0o755)
        report = install_codex_shim(prefix=prefix, binary="codex")
        assert report.action == "skipped"
        assert "user-script" in (prefix / "codex").read_text()

    def test_uninstall_removes_only_loghop_shim(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "codex").write_text("#!/bin/sh\necho real\n")
        (real_dir / "codex").chmod(0o755)
        monkeypatch.setenv("PATH", f"{real_dir}:/usr/bin:/bin")
        prefix = tmp_path / "shimbin"
        install_codex_shim(prefix=prefix, binary="codex")
        report = install_codex_shim(prefix=prefix, binary="codex", uninstall=True)
        assert report.action == "removed"
        assert not (prefix / "codex").exists()
