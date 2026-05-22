from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest


def test_providers_list_reflects_init_detection(
    cli: Callable[..., tuple[int, str, str]],
    git_repo: Path,
    loghop_env: Any,
    fake_provider: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bin_dir = loghop_env.root / "bin"
    bin_dir.mkdir()
    fake_provider(bin_dir, "codex")

    def fake_which(name: str) -> str | None:
        if name == "codex":
            return str(bin_dir / "codex")
        return None

    monkeypatch.setattr("loghop.providers.shutil.which", fake_which)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    assert cli(["init"], cwd=git_repo)[0] == 0

    config_path = git_repo / ".loghop" / "config.toml"
    assert "providers" not in config_path.read_text(encoding="utf-8")

    code, stdout, _ = cli(["providers", "list"], cwd=git_repo)
    assert code == 0
    assert "codex" in stdout
    assert "available" in stdout
    assert "claude" in stdout
    assert "missing" in stdout


def test_providers_list_works_without_init(
    cli: Callable[..., tuple[int, str, str]], git_repo: Path
) -> None:
    code, stdout, _ = cli(["providers", "list"], cwd=git_repo)
    assert code == 0
    assert "codex" in stdout
    assert "claude" in stdout
