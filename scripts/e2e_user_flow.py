#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(os.environ.get("LOGHOP_REPO_ROOT", str(_DEFAULT_REPO_ROOT))).resolve()
RUN_ROOT = Path(os.environ.get("LOGHOP_E2E_ROOT") or tempfile.mkdtemp(prefix="loghop-e2e-"))
OPTIONS: argparse.Namespace | None = None

records: list[dict[str, Any]] = []
evidence: dict[str, Any] = {"run_root": str(RUN_ROOT), "repo_root": str(REPO_ROOT)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the end-to-end loghop user-flow verification in an isolated environment."
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="repository root to install and test (default: current loghop checkout)",
    )
    parser.add_argument(
        "--run-root",
        default=str(RUN_ROOT),
        help="directory where the isolated HOME, venv, repos, and reports will be created",
    )
    parser.add_argument(
        "--real-providers",
        action="store_true",
        help="use real `codex` and `claude` from PATH instead of fake transcript-writing providers",
    )
    parser.add_argument(
        "--skip-pytest",
        action="store_true",
        help="skip the repository pytest verification step at the end",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="skip running scripts/smoke_release.py against the installed isolated binary",
    )
    return parser.parse_args()


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def record_event(kind: str, **data: Any) -> None:
    records.append({"kind": kind, "ts": now(), **data})


def run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    expect: int | tuple[int, ...] = 0,
    label: str | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    start = time.monotonic()
    proc = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    duration = round(time.monotonic() - start, 3)
    expected = (expect,) if isinstance(expect, int) else tuple(expect)
    rec = {
        "label": label or " ".join(argv),
        "argv": argv,
        "cwd": str(cwd),
        "returncode": proc.returncode,
        "duration_s": duration,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
        "expected": list(expected),
    }
    records.append({"kind": "command", "ts": now(), **rec})
    if proc.returncode not in expected:
        raise AssertionError(
            f"command failed: {label or ' '.join(argv)}\n"
            f"cwd: {cwd}\nexpected: {expected}\nactual: {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def assert_true(condition: bool, message: str, **data: Any) -> None:
    records.append(
        {"kind": "assertion", "ts": now(), "message": message, "passed": bool(condition), **data}
    )
    if not condition:
        raise AssertionError(
            message + ("\n" + json.dumps(data, indent=2, ensure_ascii=False) if data else "")
        )


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def assert_contains(path_or_text: Path | str, needle: str, context: str) -> None:
    text = read_text(path_or_text) if isinstance(path_or_text, Path) else path_or_text
    assert_true(needle in text, f"{context} contains {needle!r}", sample=text[:2000])


def assert_not_contains(path_or_text: Path | str, needle: str, context: str) -> None:
    text = read_text(path_or_text) if isinstance(path_or_text, Path) else path_or_text
    assert_true(needle not in text, f"{context} does not contain {needle!r}", sample=text[:2000])


def assert_exists(path: Path, context: str) -> None:
    assert_true(path.exists(), f"{context} exists", path=str(path))


def assert_missing(path: Path, context: str) -> None:
    assert_true(not path.exists(), f"{context} is absent", path=str(path))


PRIVATE_FILE_MODE = 0o600


def assert_private_file(path: Path, context: str) -> None:
    assert_exists(path, context)
    mode = stat.S_IMODE(path.stat().st_mode)
    assert_true(mode == PRIVATE_FILE_MODE, f"{context} is 0600", path=str(path), mode=oct(mode))


def write_exec(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


def install_fake_providers(fake_bin: Path) -> None:
    provider_script = r"""#!/usr/bin/env python3
from __future__ import annotations
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

provider = Path(sys.argv[0]).name
args = sys.argv[1:]
home = Path(os.environ["HOME"])

def ts() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

def find_cd(argv: list[str]) -> str:
    if "--cd" in argv:
        idx = argv.index("--cd")
        if idx + 1 < len(argv):
            return argv[idx + 1]
    return os.getcwd()

def prompt_text(argv: list[str]) -> str:
    filtered: list[str] = []
    skip_next = False
    for item in argv:
        if skip_next:
            skip_next = False
            continue
        if item in {"exec", "--print", "--bare", "--color", "--cd"}:
            if item in {"--color", "--cd"}:
                skip_next = True
            continue
        if item == "--":
            continue
        filtered.append(item)
    return " ".join(filtered).strip() or f"direct {provider} invocation"

def loghop_block(summary: str, decision: str, done: str, pending: str) -> str:
    return (
        f"{summary}\n"
        "```loghop\n"
        f"summary: {summary}\n"
        "decisions:\n"
        f"  - {decision}\n"
        "todos_done:\n"
        f"  - {done}\n"
        "todos_pending:\n"
        f"  - {pending}\n"
        "```"
    )

if args[:2] == ["auth", "status"]:
    print(json.dumps({"loggedIn": True, "provider": "fake-claude"}))
    raise SystemExit(0)
if args[:1] == ["--version"]:
    print(f"{provider} fake-e2e 1.0.0")
    raise SystemExit(0)

cwd = str(Path(find_cd(args)).resolve())
prompt = prompt_text(args)
stamp = ts()
uid = uuid.uuid4().hex[:10]

if provider == "codex":
    today = datetime.now(timezone.utc)
    transcript = home / ".codex" / "sessions" / f"{today.year:04d}" / f"{today.month:02d}" / f"{today.day:02d}" / f"rollout-loghop-e2e-{uid}.jsonl"
    assistant = loghop_block(
        "Codex E2E captured shared memory for the next CLI.",
        "Codex wrote timeline data that Claude should be able to read",
        "Codex provider run completed",
        "Next CLI should verify cross-provider memory",
    )
    write_jsonl(transcript, [
        {"timestamp": stamp, "type": "session_meta", "payload": {"id": f"fake-codex-{uid}", "cwd": cwd}},
        {"timestamp": stamp, "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": prompt}]}},
        {"timestamp": stamp, "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": assistant}]}},
    ])
    print(f"fake codex completed in {cwd}; transcript={transcript}")
    raise SystemExit(0)

if provider == "claude":
    slug = cwd.replace("/", "-")
    transcript = home / ".claude" / "projects" / slug / f"claude-loghop-e2e-{uid}.jsonl"
    assistant = loghop_block(
        "Claude E2E captured and continued from shared memory.",
        "Claude consumed prior Codex context from the handoff",
        "Claude provider run completed",
        "Codex should verify Claude memory on the next run",
    )
    write_jsonl(transcript, [
        {"timestamp": stamp, "type": "user", "message": {"role": "user", "content": prompt}},
        {"timestamp": stamp, "type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": assistant}]}},
    ])
    print(f"fake claude completed in {cwd}; transcript={transcript}")
    raise SystemExit(0)

print(f"unknown fake provider name: {provider}", file=sys.stderr)
raise SystemExit(2)
"""
    write_exec(fake_bin / "codex", provider_script)
    write_exec(fake_bin / "claude", provider_script)


def git_init(repo: Path, env: dict[str, str]) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-q"], cwd=repo, env=env, label=f"git init {repo.name}")
    run(["git", "config", "user.email", "e2e@example.com"], cwd=repo, env=env)
    run(["git", "config", "user.name", "Loghop E2E"], cwd=repo, env=env)
    run(["git", "config", "commit.gpgsign", "false"], cwd=repo, env=env)
    (repo / "README.md").write_text(f"# {repo.name}\n", encoding="utf-8")
    run(["git", "add", "README.md"], cwd=repo, env=env)
    run(["git", "commit", "-q", "-m", "initial"], cwd=repo, env=env)


def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def main() -> int:
    options = OPTIONS or parse_args()
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    home = RUN_ROOT / "home"
    fake_bin = RUN_ROOT / "fake-bin"
    venv = RUN_ROOT / "venv"
    outside = RUN_ROOT / "outside"
    local_bin = home / ".local" / "bin"
    project_a = RUN_ROOT / "project-alpha"
    project_b = RUN_ROOT / "project-beta"
    for path in (home, fake_bin, outside, local_bin):
        path.mkdir(parents=True, exist_ok=True)

    if not options.real_providers:
        install_fake_providers(fake_bin)

    base_env = os.environ.copy()
    base_env["NO_COLOR"] = "1"
    base_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"

    run(
        ["python3", "-m", "venv", str(venv)],
        cwd=REPO_ROOT,
        env=base_env,
        label="create isolated install venv",
        timeout=120,
    )
    py = venv / "bin" / "python"
    loghop = venv / "bin" / "loghop"
    run(
        [str(py), "-m", "pip", "install", "--upgrade", "pip"],
        cwd=REPO_ROOT,
        env=base_env,
        label="upgrade pip in isolated venv",
        timeout=180,
    )
    run(
        [str(py), "-m", "pip", "install", ".[tui]"],
        cwd=REPO_ROOT,
        env=base_env,
        label="install loghop[tui] from working tree",
        timeout=240,
    )
    assert_exists(loghop, "installed loghop console script")

    env = base_env.copy()
    env["HOME"] = str(home)
    path_parts = [str(local_bin), str(venv / "bin")]
    if not options.real_providers:
        path_parts.append(str(fake_bin))
    path_parts.append(env.get("PATH", ""))
    env["PATH"] = os.pathsep.join(path_parts)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    env.pop("ANTHROPIC_BASE_URL", None)

    def lh(
        *args: str,
        cwd: Path = outside,
        expect: int | tuple[int, ...] = 0,
        label: str | None = None,
        timeout: int = 120,
    ) -> subprocess.CompletedProcess[str]:
        return run(
            [str(loghop), "--plain", *args],
            cwd=cwd,
            env=env,
            expect=expect,
            label=label,
            timeout=timeout,
        )

    # Installation and global configuration checks.
    lh("--version", label="loghop --version")
    run([str(py), "-m", "loghop", "--help"], cwd=outside, env=env, label="python -m loghop --help")
    lh("providers", label="detect fake providers")
    lh("install", "--dry-run", label="preview install plan")
    lh("install-hooks", label="install user Claude hooks")
    lh("install-prompt", "--codex", "--claude", label="install user prompt includes")
    lh("install-shims", "--codex", "--prefix", str(local_bin), label="install Codex shim")
    lh("doctor", label="doctor healthy after install")
    assert_private_file(home / ".loghop" / "loghop-prompt.md", "shared global prompt")
    assert_exists(home / ".claude" / "settings.json", "Claude user settings")
    assert_contains(home / ".claude" / "settings.json", "claude-session-start", "Claude hooks")
    assert_contains(home / ".codex" / "AGENTS.md", "loghop-prompt.md", "Codex prompt include")
    assert_contains(home / ".claude" / "CLAUDE.md", "loghop-prompt.md", "Claude prompt include")
    assert_exists(local_bin / "codex", "Codex shim")

    # Doctor repair path: remove shim, detect, fix.
    (local_bin / "codex").unlink()
    lh("doctor", expect=1, label="doctor detects missing shim")
    lh("doctor", "--fix", label="doctor repairs missing shim")
    assert_exists(local_bin / "codex", "Codex shim after doctor --fix")

    # Project setup and config persistence.
    git_init(project_a, env)
    lh("init", cwd=project_a, label="initialize project alpha")
    lh("init", cwd=project_a, label="re-run init idempotently")
    lh("install-hooks", "--scope", "project", cwd=project_a, label="install project Claude hooks")
    lh(
        "install-prompt",
        "--scope",
        "project",
        cwd=project_a,
        label="install project prompt includes",
    )
    lh("goal", "Cross-CLI memory verification", cwd=project_a, label="set project goal")
    goal_read = lh("goal", cwd=project_a, label="read persisted project goal")
    assert_contains(goal_read.stdout, "Cross-CLI memory verification", "goal output")
    assert_private_file(project_a / ".loghop" / "config.toml", "project config")
    assert_private_file(project_a / "loghop.md", "project memory file")
    assert_contains(project_a / ".gitignore", ".loghop/", "project .gitignore")
    assert_contains(project_a / ".gitignore", "loghop.md", "project .gitignore")

    # Provider sessions through loghop run, with handoff memory in both directions.
    lh(
        "run",
        "--provider",
        "codex",
        "--goal",
        "Codex seeds memory",
        "--timeout",
        "15",
        cwd=project_a,
        label="loghop run with Codex",
    )
    assert_private_file(project_a / ".loghop" / "sessions" / "S-001.md", "Codex session markdown")
    assert_private_file(
        project_a / ".loghop" / "sessions" / "S-001.transcript.jsonl", "Codex redacted transcript"
    )
    assert_private_file(project_a / ".loghop" / "timeline.jsonl", "project timeline")
    assert_contains(
        project_a / ".loghop" / "sessions" / "S-001.md",
        "Codex E2E captured shared memory",
        "S-001 metadata",
    )
    assert_contains(project_a / "loghop.md", "Provider: codex", "memory after Codex")

    lh(
        "run",
        "--provider",
        "claude",
        "--goal",
        "Claude reads Codex memory",
        "--timeout",
        "15",
        cwd=project_a,
        label="loghop run with Claude",
    )
    assert_private_file(project_a / ".loghop" / "sessions" / "S-002.md", "Claude session markdown")
    assert_private_file(
        project_a / ".loghop" / "sessions" / "S-002.transcript.jsonl", "Claude redacted transcript"
    )
    h002 = project_a / ".loghop" / "handoffs" / "H-002.md"
    assert_private_file(h002, "Claude resume handoff")
    assert_contains(h002, "Session: S-001", "Claude handoff references previous Codex session")
    assert_contains(h002, "Provider: codex", "Claude handoff provider context")
    assert_contains(
        h002, "Codex E2E captured shared memory", "Claude handoff includes Codex summary"
    )
    assert_contains(project_a / "loghop.md", "Provider: claude", "memory after Claude")

    lh(
        "run",
        "--provider",
        "codex",
        "--goal",
        "Codex reads Claude memory",
        "--timeout",
        "15",
        cwd=project_a,
        label="second loghop run with Codex",
    )
    assert_private_file(
        project_a / ".loghop" / "sessions" / "S-003.md", "second Codex session markdown"
    )
    h003 = project_a / ".loghop" / "handoffs" / "H-003.md"
    assert_private_file(h003, "Codex resume handoff")
    assert_contains(h003, "Session: S-002", "Codex handoff references previous Claude session")
    assert_contains(h003, "Provider: claude", "Codex handoff provider context")
    assert_contains(h003, "Claude E2E captured", "Codex handoff includes Claude summary")

    # Direct CLI wrapping through installed shim and explicit wrap.
    run(
        ["codex", "Direct shim Codex capture"],
        cwd=project_a,
        env=env,
        label="direct codex CLI through loghop shim",
        timeout=60,
    )
    assert_private_file(
        project_a / ".loghop" / "sessions" / "S-004.md", "direct Codex shim session markdown"
    )
    assert_contains(
        project_a / ".loghop" / "sessions" / "S-004.md", "Codex E2E", "direct Codex session capture"
    )
    lh(
        "wrap",
        "claude",
        "Direct Claude wrap capture",
        cwd=project_a,
        label="direct Claude CLI through loghop wrap",
    )
    assert_private_file(
        project_a / ".loghop" / "sessions" / "S-005.md", "direct Claude wrap session markdown"
    )
    assert_contains(
        project_a / ".loghop" / "sessions" / "S-005.md",
        "Claude E2E",
        "direct Claude session capture",
    )

    # Browsing and persistence commands.
    lh("status", cwd=project_a, label="project status")
    sessions_out = lh("sessions", "list", "--expand", cwd=project_a, label="list expanded sessions")
    assert_contains(sessions_out.stdout, "S-005", "sessions list includes latest")
    show_out = lh("sessions", "show", "S-002", cwd=project_a, label="show Claude session")
    assert_contains(show_out.stdout, "Claude E2E", "sessions show S-002")
    timeline_out = lh(
        "timeline", "--all-status", "--limit", "20", cwd=project_a, label="timeline command"
    )
    assert_contains(timeline_out.stdout, "S-001", "timeline includes Codex run")
    assert_contains(timeline_out.stdout, "S-002", "timeline includes Claude run")
    journal_out = lh("journal", "--all", cwd=outside, label="global journal")
    assert_contains(
        journal_out.stdout, "Codex E2E", "global journal includes Codex session content"
    )
    assert_contains(
        journal_out.stdout, "Claude E2E", "global journal includes Claude session content"
    )

    # Session deletion and negative cases.
    lh("sessions", "delete", "S-004", "-y", cwd=project_a, label="delete direct Codex session")
    assert_missing(project_a / ".loghop" / "sessions" / "S-004.md", "deleted session markdown")
    assert_missing(
        project_a / ".loghop" / "sessions" / "S-004.transcript.jsonl", "deleted session transcript"
    )
    timeline_after_delete = read_text(project_a / ".loghop" / "timeline.jsonl")
    assert_not_contains(
        timeline_after_delete, '"session_id": "S-004"', "timeline after session delete"
    )
    lh(
        "sessions",
        "delete",
        "S-999",
        "-y",
        cwd=project_a,
        expect=(1, 2),
        label="delete non-existent session fails",
    )
    lh(
        "sessions",
        "delete",
        "BAD",
        "-y",
        cwd=project_a,
        expect=(1, 2),
        label="delete invalid session id fails",
    )
    lh(
        "run",
        "missing-project",
        "--provider",
        "codex",
        "--timeout",
        "5",
        cwd=outside,
        expect=(1, 2, 20),
        label="run missing project fails",
    )

    # Project registry add/remove via cleanup.
    git_init(project_b, env)
    lh("init", cwd=project_b, label="initialize project beta")
    projects_out = lh("projects", cwd=outside, label="list registered projects")
    assert_contains(projects_out.stdout, "project-alpha", "projects list")
    assert_contains(projects_out.stdout, "project-beta", "projects list")
    assert_private_file(home / ".loghop" / "projects.toml", "global project registry")
    shutil.rmtree(project_b)
    cleanup_out = lh("projects", "cleanup", cwd=outside, label="cleanup removed project beta")
    assert_contains(cleanup_out.stdout, "Removed 1 missing project", "projects cleanup output")
    registry_text = read_text(home / ".loghop" / "projects.toml")
    assert_contains(registry_text, "project-alpha", "registry after cleanup")
    assert_not_contains(registry_text, "project-beta", "registry after cleanup")

    # TUI dependency smoke check from installed extra.
    run(
        [str(py), "-c", "import textual, loghop.tui.app; print('tui import ok')"],
        cwd=outside,
        env=env,
        label="TUI extra import smoke",
    )

    if not options.skip_pytest:
        run(
            [str(REPO_ROOT / ".venv" / "bin" / "python"), "-m", "pytest", "-q"],
            cwd=REPO_ROOT,
            env=base_env,
            timeout=300,
            label="repository pytest verification",
        )

    if not options.skip_smoke:
        run(
            [
                "python3",
                str(REPO_ROOT / "scripts" / "smoke_release.py"),
                "--loghop-bin",
                str(loghop),
                "--python-bin",
                str(py),
                "--expect-tui",
            ],
            cwd=REPO_ROOT,
            env=base_env,
            timeout=240,
            label="official smoke_release verification",
        )

    # Uninstall/purge global artifacts and project-scope prompt/hook entries.
    lh("uninstall", "-y", "--purge", cwd=project_a, label="uninstall and purge global artifacts")
    assert_missing(home / ".loghop", "purged global .loghop")
    assert_missing(local_bin / "codex", "removed Codex shim")
    if (project_a / "AGENTS.md").exists():
        assert_not_contains(
            project_a / "AGENTS.md", "loghop-prompt.md", "project AGENTS after uninstall"
        )
    if (project_a / "CLAUDE.md").exists():
        assert_not_contains(
            project_a / "CLAUDE.md", "loghop-prompt.md", "project CLAUDE after uninstall"
        )
    if (project_a / ".claude" / "settings.json").exists():
        assert_not_contains(
            project_a / ".claude" / "settings.json",
            "loghop hook",
            "project Claude hooks after uninstall",
        )

    evidence.update(
        {
            "home": str(home),
            "project_alpha": str(project_a),
            "installed_loghop": str(loghop),
            "session_files_remaining": sorted(
                p.name for p in (project_a / ".loghop" / "sessions").glob("S-*.md")
            ),
            "handoff_files": sorted(
                p.name for p in (project_a / ".loghop" / "handoffs").glob("H-*.md")
            ),
            "timeline_events_remaining": parse_jsonl(project_a / ".loghop" / "timeline.jsonl"),
        }
    )
    return 0


if __name__ == "__main__":
    OPTIONS = parse_args()
    REPO_ROOT = Path(str(OPTIONS.repo_root)).expanduser().resolve()
    RUN_ROOT = Path(str(OPTIONS.run_root)).expanduser().resolve()
    evidence = {"run_root": str(RUN_ROOT), "repo_root": str(REPO_ROOT)}
    report_path = RUN_ROOT / "e2e-report.json"
    md_path = RUN_ROOT / "e2e-report.md"
    try:
        rc = main()
        status = "passed"
        error = ""
    except BaseException as exc:  # noqa: BLE001 - test harness should always write a report
        rc = 1
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
        record_event("error", error=error)
    report = {"status": status, "error": error, "evidence": evidence, "records": records}
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    commands = [r for r in records if r.get("kind") == "command"]
    assertions = [r for r in records if r.get("kind") == "assertion"]
    failed_assertions = [r for r in assertions if not r.get("passed")]
    md = [
        "# loghop E2E user-flow report",
        "",
        f"- Status: **{status}**",
        f"- Error: {error or '(none)'}",
        f"- Run root: `{RUN_ROOT}`",
        f"- Commands: {len(commands)}",
        f"- Assertions: {len(assertions)}",
        f"- Failed assertions: {len(failed_assertions)}",
        "",
        "## Command summary",
        "",
    ]
    md.extend(
        f"- `{rec['label']}` → exit {rec['returncode']} ({rec['duration_s']}s)" for rec in commands
    )
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": status,
                "error": error,
                "report": str(report_path),
                "markdown": str(md_path),
            },
            ensure_ascii=False,
        )
    )
    raise SystemExit(rc)
