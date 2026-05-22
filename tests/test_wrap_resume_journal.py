from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import init_repo

from loghop.store import delete_project_data, project_paths
from loghop.store._registry import load_registry
from loghop.store._session import create_session, find_session, finish_session

CliRunner = Callable[..., tuple[int, str, str]]


def _write_claude_transcript(cwd: Path, lines: list[dict[str, Any]]) -> Path:
    slug = str(cwd.resolve()).replace("/", "-")
    proj_dir = Path.home() / ".claude" / "projects" / slug
    proj_dir.mkdir(parents=True, exist_ok=True)
    out = proj_dir / "session.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    return out


def _install_fake_provider(bin_dir: Path, name: str, exit_code: int = 0) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / name
    auth_status = (
        'if [ "$1" = "auth" ] && [ "$2" = "status" ]; then\n'
        "  printf '{\"loggedIn\":true}\\n'\n"
        "  exit 0\n"
        "fi\n"
        if name == "claude"
        else ""
    )
    script.write_text(f"#!/bin/sh\n{auth_status}exit {exit_code}\n")
    script.chmod(0o755)
    return script


def _install_provider_that_writes_transcript(
    bin_dir: Path, name: str, cwd: Path, payload: str
) -> Path:
    """Install a fake provider that, when run, writes a Claude-style transcript.

    The transcript's mtime will be after the wrap launch_ts, so capture finds it.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    slug = str(cwd.resolve()).replace("/", "-")
    transcript_dir = Path.home() / ".claude" / "projects" / slug
    script = bin_dir / name
    script.write_text(
        f"""#!/bin/sh
set -e
mkdir -p {transcript_dir}
cat > {transcript_dir}/session.jsonl << 'JSONL'
{payload}
JSONL
exit 0
"""
    )
    script.chmod(0o755)
    return script


def _backdate_session(root: Path, session_id: str, hours_ago: int) -> None:
    from loghop.store._index import rebuild_index

    md = project_paths(root).sessions / f"{session_id}.md"
    text = md.read_text()
    old = (datetime.now(tz=UTC) - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")
    import re

    text = re.sub(r'"ts_start":\s*"[^"]*"', f'"ts_start": "{old}"', text)
    text = re.sub(r"ts_start:\s*.*", f"ts_start: '{old}'", text)
    md.write_text(text)
    rebuild_index(project_paths(root))


class TestWrap:
    def test_wrap_inside_loghop_creates_session_and_captures(
        self,
        cli: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = init_repo(tmp_path)
        bin_dir = tmp_path / "bin"
        payload = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "wrapped run output."}],
                },
                "timestamp": "2026-04-24T10:00:00Z",
            }
        )
        _install_provider_that_writes_transcript(bin_dir, "claude", root, payload)
        monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")

        code, stdout, _ = cli(["wrap", "claude"], cwd=root)
        assert code == 0
        assert "session S-001" in stdout

        meta = next(p for p in load_registry() if p.path == str(root.resolve()))
        assert meta.session_count == 1

        sessions_dir = project_paths(root).sessions
        assert (sessions_dir / "S-001.md").exists()
        assert (sessions_dir / "S-001.transcript.jsonl").exists()

    def test_wrap_outside_loghop_execs_directly(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Plain dir, no .loghop. Wrap should exec the binary directly and
        # never touch the registry.
        plain = tmp_path / "plain"
        plain.mkdir()
        bin_dir = tmp_path / "bin"
        _install_fake_provider(bin_dir, "claude")
        monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
        monkeypatch.chdir(plain)

        # Stub os.execvp so the test process is not replaced.
        called: dict[str, object] = {}

        def fake_execvp(path: str, argv: list[str]) -> None:
            called["path"] = path
            called["argv"] = argv

        from argparse import Namespace

        from loghop.cli_commands import wrap as wrap_module
        from loghop.terminal import Terminal, TerminalOptions

        monkeypatch.setattr("loghop.cli_commands.wrap.os.execvp", fake_execvp)
        args = Namespace(provider="claude", passthrough=["--foo", "bar"])
        result = wrap_module.handle_wrap(args, Terminal(TerminalOptions(plain=True)))

        assert result == 0
        assert called["path"] == str(bin_dir / "claude")
        assert called["argv"] == [str(bin_dir / "claude"), "--foo", "bar"]
        assert load_registry() == []

    def test_wrap_outside_loghop_codex_skips_loghop_shim(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        shim_dir = tmp_path / "shim"
        shim_dir.mkdir()
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        shim = shim_dir / "codex"
        shim.write_text("#!/bin/sh\n# Managed by loghop install-shims\nexit 99\n")
        shim.chmod(0o755)
        real = _install_fake_provider(real_dir, "codex")
        monkeypatch.setenv("PATH", f"{shim_dir}:{real_dir}:/usr/bin:/bin")
        monkeypatch.chdir(plain)

        called: dict[str, object] = {}

        def fake_execvp(path: str, argv: list[str]) -> None:
            called["path"] = path
            called["argv"] = argv

        from argparse import Namespace

        from loghop.cli_commands import wrap as wrap_module
        from loghop.terminal import Terminal, TerminalOptions

        monkeypatch.setattr("loghop.cli_commands.wrap.os.execvp", fake_execvp)
        args = Namespace(provider="codex", passthrough=["--version"])
        result = wrap_module.handle_wrap(args, Terminal(TerminalOptions(plain=True)))

        assert result == 0
        assert called["path"] == str(real)
        assert called["argv"] == [str(real), "--version"]

    def test_wrap_captures_failure_returncode(
        self,
        cli: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = init_repo(tmp_path)
        bin_dir = tmp_path / "bin"
        _install_fake_provider(bin_dir, "claude", exit_code=7)
        monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")

        code, _, _ = cli(["wrap", "claude"], cwd=root)
        assert code == 7
        meta_path = project_paths(root).sessions / "S-001.md"
        assert "failed" in meta_path.read_text()

    def test_wrap_prefers_real_provider_from_shim_env_inside_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = init_repo(tmp_path)
        bin_dir = tmp_path / "bin"
        shim = _install_fake_provider(bin_dir, "claude")
        real = _install_fake_provider(bin_dir, "claude-real")
        monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
        monkeypatch.setenv("LOGHOP_REAL_CLAUDE", str(real))
        monkeypatch.chdir(root)

        called: list[list[str]] = []

        def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            called.append(argv)
            return subprocess.CompletedProcess(argv, 0)

        from loghop.cli_commands import wrap as wrap_module
        from loghop.terminal import Terminal, TerminalOptions

        monkeypatch.setattr(wrap_module, "find_project_root", lambda _cwd: root)
        monkeypatch.setattr(wrap_module, "current_files_changed", lambda _root: [])
        monkeypatch.setattr("loghop.cli_commands.wrap.subprocess.run", fake_run)
        monkeypatch.setattr(
            "loghop.session_lifecycle.capture_from_transcript", lambda *_a, **_kw: {}
        )
        args = argparse.Namespace(provider="claude", passthrough=[])
        rc = wrap_module.handle_wrap(args, Terminal(TerminalOptions(plain=True)))

        assert rc == 0
        provider_calls = [argv for argv in called if argv and argv[0] == str(real)]
        assert provider_calls == [[str(real)]]
        assert str(shim) != str(real)

    def test_wrap_codex_does_not_inject_claude_api_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = init_repo(tmp_path)
        bin_dir = tmp_path / "bin"
        real = _install_fake_provider(bin_dir, "codex")
        monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "secret-token")
        monkeypatch.chdir(root)

        captured_env: dict[str, str] = {}

        def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            del argv
            env = kwargs.get("env")
            assert isinstance(env, dict)
            captured_env.update({str(k): str(v) for k, v in env.items()})
            return subprocess.CompletedProcess([str(real)], 0)

        from loghop.cli_commands import wrap as wrap_module
        from loghop.terminal import Terminal, TerminalOptions

        monkeypatch.setattr(wrap_module, "find_project_root", lambda _cwd: root)
        monkeypatch.setattr(wrap_module, "current_files_changed", lambda _root: [])
        monkeypatch.setattr("loghop.cli_commands.wrap.subprocess.run", fake_run)
        monkeypatch.setattr(
            "loghop.session_lifecycle.capture_from_transcript", lambda *_a, **_kw: {}
        )
        args = argparse.Namespace(provider="codex", passthrough=[])
        rc = wrap_module.handle_wrap(args, Terminal(TerminalOptions(plain=True)))

        assert rc == 0
        assert "ANTHROPIC_API_KEY" not in captured_env
        assert captured_env.get("ANTHROPIC_AUTH_TOKEN") == "secret-token"

    def test_wrap_preserves_subdirectory_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = init_repo(tmp_path)
        subdir = root / "nested"
        subdir.mkdir()
        bin_dir = tmp_path / "bin"
        real = _install_fake_provider(bin_dir, "claude-real")
        monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
        monkeypatch.setenv("LOGHOP_REAL_CLAUDE", str(real))
        monkeypatch.chdir(subdir)

        captured: list[tuple[list[str], Path]] = []

        def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured.append((argv, Path(str(kwargs["cwd"]))))
            return subprocess.CompletedProcess(argv, 0)

        from loghop.cli_commands import wrap as wrap_module
        from loghop.terminal import Terminal, TerminalOptions

        monkeypatch.setattr(wrap_module, "find_project_root", lambda _cwd: root)
        monkeypatch.setattr(wrap_module, "current_files_changed", lambda _root: [])
        monkeypatch.setattr("loghop.cli_commands.wrap.subprocess.run", fake_run)
        monkeypatch.setattr(
            "loghop.session_lifecycle.capture_from_transcript", lambda *_a, **_kw: {}
        )
        args = argparse.Namespace(provider="claude", passthrough=[])
        rc = wrap_module.handle_wrap(args, Terminal(TerminalOptions(plain=True)))

        assert rc == 0
        provider_cwds = [cwd for argv, cwd in captured if argv and argv[0] == str(real)]
        assert provider_cwds == [subdir]


class TestResumeTarget:
    def test_resume_with_project_name_chdirs_first(
        self,
        cli: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = init_repo(tmp_path, name="alpha")
        # Seed a previous session so resume has something to chain onto.
        s = create_session(target, provider="claude", goal="prev goal")
        finish_session(target, s.id, status="succeeded", returncode=0)

        bin_dir = tmp_path / "bin"
        _install_fake_provider(bin_dir, "claude")
        monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")

        outside = tmp_path / "elsewhere"
        outside.mkdir()
        code, stdout, _ = cli(["resume", "alpha", "--goal", "next step"], cwd=outside)
        assert code == 0
        assert "alpha" in stdout
        # Second session should now exist in alpha.
        assert (project_paths(target).sessions / "S-002.md").exists()

    def test_resume_unknown_target_errors(self, cli: CliRunner, tmp_path: Path) -> None:
        code, _, stderr = cli(["resume", "no-such-project", "--goal", "x"], cwd=tmp_path)
        assert code != 0
        assert "no registered project" in stderr.lower()

    def test_resume_duplicate_target_name_errors(self, cli: CliRunner, tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        init_repo(tmp_path / "a", name="dup")
        init_repo(tmp_path / "b", name="dup")
        outside = tmp_path / "elsewhere"
        outside.mkdir()

        code, _, stderr = cli(["resume", "dup", "--goal", "x"], cwd=outside)

        assert code == 2
        assert "ambiguous target" in stderr.lower()

    def test_resume_rejects_registered_project_without_loghop_data(
        self, cli: CliRunner, tmp_path: Path
    ) -> None:
        target = init_repo(tmp_path, name="alpha")
        delete_project_data(target)

        outside = tmp_path / "elsewhere"
        outside.mkdir()
        code, _, stderr = cli(["resume", "alpha", "--goal", "x"], cwd=outside)

        assert code != 0
        assert "no registered project" in stderr.lower()

    def test_resume_target_reconciles_stale_running_session_before_chaining(
        self, cli: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = init_repo(tmp_path, name="alpha")
        stuck = create_session(target, provider="claude", goal="prev goal")
        _backdate_session(target, stuck.id, hours_ago=2)
        _write_claude_transcript(
            target,
            [
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "rescued before resume"}],
                    },
                    "timestamp": "2026-04-24T10:00:00Z",
                }
            ],
        )

        bin_dir = tmp_path / "bin"
        _install_fake_provider(bin_dir, "claude")
        monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")

        outside = tmp_path / "elsewhere"
        outside.mkdir()
        code, _, _ = cli(["resume", "alpha", "--goal", "next step"], cwd=outside)
        assert code == 0

        reconciled = find_session(project_paths(target), "S-001")
        assert reconciled.status == "interrupted"
        assert reconciled.summary == "rescued before resume"
        assert (project_paths(target).sessions / "S-002.md").exists()


class TestJournal:
    def test_journal_renders_sessions_grouped_by_date(self, cli: CliRunner, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        # Two sessions with summaries + decisions.
        s1 = create_session(root, provider="claude", goal="goal one")
        finish_session(
            root,
            s1.id,
            status="succeeded",
            returncode=0,
            summary="first summary",
            decisions=["use sqlite"],
            todos_pending=["wire migrations"],
        )
        s2 = create_session(root, provider="codex", goal="goal two")
        finish_session(
            root,
            s2.id,
            status="succeeded",
            returncode=0,
            summary="second summary",
        )

        code, stdout, _ = cli(["journal"], cwd=root)
        assert code == 0
        assert "loghop journal" in stdout
        assert "first summary" in stdout
        assert "second summary" in stdout
        assert "use sqlite" in stdout
        assert "wire migrations" in stdout

    def test_journal_since_filters_old_sessions(self, cli: CliRunner, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        s = create_session(root, provider="claude", goal="g")
        finish_session(root, s.id, status="succeeded", returncode=0, summary="recent")
        # Backdate the session by hand-editing its frontmatter.
        md = project_paths(root).sessions / f"{s.id}.md"
        content = md.read_text()
        old_ts = (datetime.now(tz=UTC) - timedelta(days=30)).isoformat().replace("+00:00", "Z")
        # Replace both ts_start and ts_end so the timeline rebuild picks up the old date.
        import re

        content = re.sub(r"ts_start:\s*.*", f"ts_start: '{old_ts}'", content)
        content = re.sub(r"ts_end:\s*.*", f"ts_end: '{old_ts}'", content)
        md.write_text(content)
        # Rebuild both the session index and the timeline so journal sees the backdated session.
        from loghop.store._index import rebuild_index
        from loghop.store._timeline import remove_session_timeline_events

        paths = project_paths(root)
        rebuild_index(paths)
        remove_session_timeline_events(paths, s.id)

        code, stdout, _ = cli(["journal", "--since", "7d"], cwd=root)
        assert code == 0
        assert "no sessions match" in stdout.lower()

    def test_journal_all_aggregates_across_projects(self, cli: CliRunner, tmp_path: Path) -> None:
        a = init_repo(tmp_path, name="alpha")
        b = init_repo(tmp_path, name="beta")
        sa = create_session(a, provider="claude", goal="a")
        finish_session(a, sa.id, status="succeeded", returncode=0, summary="from alpha")
        sb = create_session(b, provider="codex", goal="b")
        finish_session(b, sb.id, status="succeeded", returncode=0, summary="from beta")

        code, stdout, _ = cli(["journal", "--all"], cwd=tmp_path)
        assert code == 0
        assert "from alpha" in stdout
        assert "from beta" in stdout
        assert "_alpha_" in stdout or "alpha" in stdout
        assert "_beta_" in stdout or "beta" in stdout

    def test_journal_all_shows_project_name_even_with_one_project(
        self, cli: CliRunner, tmp_path: Path
    ) -> None:
        root = init_repo(tmp_path, name="alpha")
        s = create_session(root, provider="claude", goal="g")
        finish_session(root, s.id, status="succeeded", returncode=0, summary="solo")

        code, stdout, _ = cli(["journal", "--all"], cwd=tmp_path)
        assert code == 0
        assert "solo" in stdout
        assert "_alpha_" in stdout or "alpha" in stdout

    def test_journal_invalid_since_errors(self, cli: CliRunner, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        code, _, stderr = cli(["journal", "--since", "junk"], cwd=root)
        assert code != 0
        assert "since" in stderr.lower()

    def test_journal_since_hours(self, cli: CliRunner, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        s = create_session(root, provider="claude", goal="g")
        finish_session(root, s.id, status="succeeded", returncode=0, summary="recent")
        code, stdout, _ = cli(["journal", "--since", "12h"], cwd=root)
        assert code == 0
        assert "recent" in stdout

    def test_journal_since_weeks(self, cli: CliRunner, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        s = create_session(root, provider="claude", goal="g")
        finish_session(root, s.id, status="succeeded", returncode=0, summary="recent")
        code, stdout, _ = cli(["journal", "--since", "2w"], cwd=root)
        assert code == 0
        assert "recent" in stdout

    def test_journal_project_flag(self, cli: CliRunner, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        s = create_session(root, provider="claude", goal="g")
        finish_session(root, s.id, status="succeeded", returncode=0, summary="from project")
        code, stdout, _ = cli(["journal", "--project", root.name], cwd=tmp_path)
        assert code == 0
        assert "from project" in stdout

    def test_journal_project_flag_not_found(self, cli: CliRunner, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        code, _, stderr = cli(["journal", "--project", "nonexistent-xyz"], cwd=root)
        assert code == 2
        assert "no registered project" in stderr.lower()
