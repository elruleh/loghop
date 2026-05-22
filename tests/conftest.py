from __future__ import annotations

import contextlib
import io
import stat
import subprocess
import sys
import textwrap
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from loghop.cli import main

CliRunner = Callable[..., tuple[int, str, str]]


@dataclass
class Env:
    root: Path


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never touch the user's real ~/.loghop registry from tests."""
    fake_home = tmp_path / "home"
    fake_home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))


@pytest.fixture
def loghop_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    monkeypatch.setenv("NO_COLOR", "1")
    return Env(root=tmp_path)


@pytest.fixture
def cli(loghop_env: Env, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    def _run(argv: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        monkeypatch.chdir(cwd or loghop_env.root)
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--plain", *argv])
        return code, stdout.getvalue(), stderr.getvalue()

    return _run


@pytest.fixture
def git_repo(loghop_env: Env) -> Path:
    repo = loghop_env.root / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)
    (repo / "app.py").write_text("print('hello')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True, capture_output=True
    )
    return repo


@pytest.fixture
def initialized_repo(
    cli: CliRunner, git_repo: Path, loghop_env: Env, monkeypatch: pytest.MonkeyPatch
) -> Path:
    bin_dir = loghop_env.root / "bin"
    bin_dir.mkdir()
    _make_fake_provider(bin_dir, "codex")
    _make_fake_provider(bin_dir, "claude")
    monkeypatch.setenv("PATH", f"{bin_dir}:{_raw_path(monkeypatch)}")
    code, _, _ = cli(["init"], cwd=git_repo)
    assert code == 0
    return git_repo


@pytest.fixture
def fake_provider() -> Callable[[Path, str], Path]:
    return _make_fake_provider


def _make_fake_provider(directory: Path, name: str) -> Path:
    path = directory / name
    script = textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        if [ "$1" = "--version" ]; then
          echo "{name} 1.0.0"
          exit 0
        fi
        printf '%s\\n' "$@" > "{directory / f"{name}-args.txt"}"
        exit 0
        """
    ).lstrip()
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _raw_path(monkeypatch: pytest.MonkeyPatch) -> str:
    import os

    return os.environ.get("PATH", "")


def git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=root, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)


def init_repo(parent: Path, name: str = "repo") -> Path:
    from loghop.store import init_project

    root = parent / name
    root.mkdir()
    git_init(root)
    (root / "x").write_text("x")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "i"], cwd=root, check=True)
    init_project(root)
    return root
