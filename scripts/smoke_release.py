#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test an installed loghop artifact.")
    parser.add_argument("--loghop-bin", required=True, help="path to the installed `loghop` binary")
    parser.add_argument(
        "--python-bin",
        help="optional Python interpreter for `python -m loghop` and TUI import checks",
    )
    parser.add_argument(
        "--expect-tui",
        action="store_true",
        help="verify that the installed environment includes the optional TUI extra",
    )
    return parser.parse_args()


def _cli_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    expect: int = 0,
) -> str:
    proc = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != expect:
        cmd = " ".join(argv)
        raise RuntimeError(
            f"command failed: {cmd}\n"
            f"cwd: {cwd}\n"
            f"expected exit: {expect}\n"
            f"actual exit: {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc.stdout


def _write_file(path: Path, body: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if executable:
        path.chmod(path.stat().st_mode | 0o111)


def _install_fake_providers(bin_dir: Path) -> None:
    claude = textwrap.dedent(
        """\
        #!/bin/sh
        set -eu
        if [ "${1:-}" = "--version" ]; then
          echo "claude 1.0.0"
          exit 0
        fi
        ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
        slug="$(pwd | tr '/' '-')"
        out_dir="$HOME/.claude/projects/$slug"
        mkdir -p "$out_dir"
        cat > "$out_dir/session.jsonl" <<JSONL
        {"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Wrapped smoke run completed.\\nDecision: keep release smoke checks.\\nTODO: review published package."}]},"timestamp":"$ts"}
        JSONL
        exit 0
        """
    )
    codex = textwrap.dedent(
        """\
        #!/bin/sh
        set -eu
        if [ "${1:-}" = "--version" ]; then
          echo "codex 1.0.0"
          exit 0
        fi
        ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
        yyyy="$(date -u +"%Y")"
        mm="$(date -u +"%m")"
        dd="$(date -u +"%d")"
        out_dir="$HOME/.codex/sessions/$yyyy/$mm/$dd"
        mkdir -p "$out_dir"
        cat > "$out_dir/rollout-smoke.jsonl" <<JSONL
        {"timestamp":"$ts","type":"session_meta","payload":{"id":"smoke","cwd":"$(pwd)"}}
        {"timestamp":"$ts","type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"Wrapped Codex smoke run completed.\\nDecision: keep the codex shim smoke test."}]}}
        JSONL
        exit 0
        """
    )
    _write_file(bin_dir / "claude", claude, executable=True)
    _write_file(bin_dir / "codex", codex, executable=True)


def _git_init(repo: Path, env: dict[str, str]) -> None:
    _run(["git", "init", "-q"], cwd=repo, env=env)
    _run(["git", "config", "user.email", "smoke@example.com"], cwd=repo, env=env)
    _run(["git", "config", "user.name", "Smoke"], cwd=repo, env=env)
    _run(["git", "config", "commit.gpgsign", "false"], cwd=repo, env=env)
    (repo / "app.py").write_text("print('hello')\n", encoding="utf-8")
    _run(["git", "add", "app.py"], cwd=repo, env=env)
    _run(["git", "commit", "-q", "-m", "initial"], cwd=repo, env=env)


def _assert_exists(path: Path) -> None:
    if not path.exists():
        raise RuntimeError(f"expected path to exist: {path}")


def _assert_missing(path: Path) -> None:
    if path.exists():
        raise RuntimeError(f"expected path to be absent: {path}")


def _assert_contains(text: str, needle: str, *, context: str) -> None:
    if needle not in text:
        raise RuntimeError(f"expected {context} to contain {needle!r}\n{text}")


def _assert_not_contains(text: str, needle: str, *, context: str) -> None:
    if needle in text:
        raise RuntimeError(f"expected {context} not to contain {needle!r}\n{text}")


def _main() -> int:
    args = _parse_args()
    loghop_bin = _cli_path(args.loghop_bin)
    python_bin = _cli_path(args.python_bin) if args.python_bin else None

    if not loghop_bin.exists():
        raise RuntimeError(f"loghop binary not found: {loghop_bin}")
    if python_bin is not None and not python_bin.exists():
        raise RuntimeError(f"python binary not found: {python_bin}")

    with tempfile.TemporaryDirectory(prefix="loghop-smoke-") as tmp:
        root = Path(tmp)
        home = root / "home"
        repo = root / "smoke-repo"
        outside = root / "outside"
        bin_dir = root / "providers"
        local_bin = home / ".local" / "bin"
        repo.mkdir()
        outside.mkdir()
        home.mkdir()
        local_bin.mkdir(parents=True)
        _install_fake_providers(bin_dir)

        env = os.environ.copy()
        env["HOME"] = str(home)
        env["NO_COLOR"] = "1"
        env["PATH"] = os.pathsep.join(
            [str(local_bin), str(loghop_bin.parent), str(bin_dir), env.get("PATH", "")]
        )

        _run([str(loghop_bin), "--version"], cwd=outside, env=env)
        help_text = _run([str(loghop_bin), "--help"], cwd=outside, env=env)
        _assert_contains(help_text, "loghop run", context="top-level help")
        _assert_not_contains(help_text, "install-prompt", context="top-level help")
        sessions_help = _run([str(loghop_bin), "sessions", "--help"], cwd=outside, env=env)
        _assert_contains(sessions_help, "Omit the subcommand", context="sessions help")
        projects_help = _run([str(loghop_bin), "projects", "--help"], cwd=outside, env=env)
        _assert_contains(projects_help, "Omit the subcommand", context="projects help")
        if python_bin is not None:
            _run([str(python_bin), "-m", "loghop", "--help"], cwd=outside, env=env)

        _run([str(loghop_bin), "providers"], cwd=outside, env=env)
        _run([str(loghop_bin), "install-hooks"], cwd=outside, env=env)
        _run([str(loghop_bin), "install-prompt", "--codex", "--claude"], cwd=outside, env=env)
        _run(
            [str(loghop_bin), "install-shims", "--codex", "--prefix", str(local_bin)],
            cwd=outside,
            env=env,
        )
        _run([str(loghop_bin), "doctor"], cwd=outside, env=env)
        _assert_exists(home / ".loghop" / "loghop.log")

        (local_bin / "codex").unlink()
        _run([str(loghop_bin), "doctor"], cwd=outside, env=env, expect=1)
        _run([str(loghop_bin), "doctor", "--fix"], cwd=outside, env=env)
        _assert_exists(local_bin / "codex")

        _git_init(repo, env)
        _run([str(loghop_bin), "init", "--no-prompt"], cwd=repo, env=env)
        _run([str(loghop_bin), "goal", "Ship smoke flow"], cwd=repo, env=env)
        _run([str(loghop_bin), "install-hooks", "--scope", "project"], cwd=repo, env=env)
        _run([str(loghop_bin), "install-prompt", "--scope", "project"], cwd=repo, env=env)
        _run(
            [
                str(loghop_bin),
                "handoff",
                "build",
                "--provider",
                "claude",
                "--goal",
                "Initial smoke",
            ],
            cwd=repo,
            env=env,
        )
        _run(["codex"], cwd=repo, env=env)
        _assert_exists(repo / ".loghop" / "sessions" / "S-001.md")
        _assert_exists(repo / ".loghop" / "sessions" / "S-001.transcript.jsonl")
        _run([str(loghop_bin), "wrap", "claude"], cwd=repo, env=env)
        _assert_exists(repo / ".loghop" / "loghop.log")
        _assert_exists(repo / ".loghop" / "sessions" / "S-002.md")
        _assert_exists(repo / ".loghop" / "sessions" / "S-002.transcript.jsonl")
        _run([str(loghop_bin), "sessions"], cwd=repo, env=env)
        _run([str(loghop_bin), "sessions", "show", "S-001"], cwd=repo, env=env)
        _run([str(loghop_bin), "sessions", "show", "S-002"], cwd=repo, env=env)

        _run(
            [
                str(loghop_bin),
                "run",
                "smoke-repo",
                "--provider",
                "claude",
                "--goal",
                "Follow-up",
            ],
            cwd=outside,
            env=env,
        )
        _assert_exists(repo / ".loghop" / "sessions" / "S-003.md")
        _run([str(loghop_bin), "projects"], cwd=outside, env=env)
        _run([str(loghop_bin), "projects", "show", "smoke-repo"], cwd=outside, env=env)

        if python_bin is not None and args.expect_tui:
            _run(
                [str(python_bin), "-c", "import textual, loghop.tui.app"],
                cwd=outside,
                env=env,
            )

        _assert_exists(repo / "AGENTS.md")
        _assert_exists(repo / "CLAUDE.md")
        _assert_exists(repo / ".claude" / "settings.json")

        _run([str(loghop_bin), "uninstall", "-y", "--purge"], cwd=repo, env=env)
        _assert_missing(home / ".loghop")
        project_claude = repo / ".claude" / "settings.json"
        if project_claude.exists():
            body = project_claude.read_text(encoding="utf-8")
            if "loghop hook " in body:
                raise RuntimeError("project-scope Claude hooks were not removed")
        for entry in (repo / "AGENTS.md", repo / "CLAUDE.md"):
            if entry.exists() and "loghop-prompt.md" in entry.read_text(encoding="utf-8"):
                raise RuntimeError(f"project-scope prompt include still present in {entry}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_main())
    except RuntimeError as exc:
        sys.stderr.write(f"{exc}\n")
        raise SystemExit(1) from exc
