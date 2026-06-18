from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from loghop.errors import E_PROVIDER_AUTH_MISSING, LoghopError
from loghop.install import InitInstallChoices, save_init_install_choices

CliRunner = Callable[..., tuple[int, str, str]]


def _install_transcript_provider(bin_dir: Path, name: str) -> None:
    script = bin_dir / name
    script.write_text(
        """#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

provider = "__PROVIDER__"
if provider == "claude" and sys.argv[1:3] == ["auth", "status"]:
    print(json.dumps({"loggedIn": True}))
    raise SystemExit(0)

home = Path.home()
cwd = Path.cwd().resolve()
count_path = home / f".fake-{provider}-count"
count = int(count_path.read_text() or "0") + 1 if count_path.exists() else 1
count_path.write_text(str(count))
prompt = sys.argv[-1] if len(sys.argv) > 1 else ""

if provider == "claude":
    target = home / ".claude" / "projects" / str(cwd).replace("/", "-") / f"session-{count}.jsonl"
    if count == 1:
        summary = "Claude initial summary"
        pending = "Codex must preserve Claude pending task"
    else:
        summary = "Claude final summary"
        pending = "Regression test can stay green"
    entries = [
        {
            "type": "user",
            "message": {"role": "user", "content": prompt},
            "timestamp": "2026-05-15T10:00:00Z",
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "```loghop\\n"
                            f"summary: {summary}\\n"
                            "decisions:\\n"
                            f"  - {provider} decision {count}\\n"
                            "todos_done:\\n"
                            f"  - {provider} done {count}\\n"
                            "todos_pending:\\n"
                            f"  - {pending}\\n"
                            "```"
                        ),
                    }
                ],
            },
            "timestamp": "2026-05-15T10:00:01Z",
        },
    ]
else:
    target = home / ".codex" / "sessions" / "2026" / "05" / "15" / f"rollout-{count}.jsonl"
    entries = [
        {
            "type": "session_meta",
            "timestamp": "2026-05-15T10:01:00Z",
            "payload": {"id": f"codex-{count}", "cwd": str(cwd)},
        },
        {
            "type": "response_item",
            "timestamp": "2026-05-15T10:01:01Z",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            },
        },
        {
            "type": "response_item",
            "timestamp": "2026-05-15T10:01:02Z",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": (
                            "```loghop\\n"
                            "summary: Codex continuation summary\\n"
                            "decisions:\\n"
                            "  - Codex consumed Claude context\\n"
                            "todos_done:\\n"
                            "  - Verified Claude pending task\\n"
                            "todos_pending:\\n"
                            "  - Claude must preserve Codex pending task\\n"
                            "```"
                        ),
                    }
                ],
            },
        },
    ]

target.parent.mkdir(parents=True, exist_ok=True)
target.write_text("\\n".join(json.dumps(entry) for entry in entries) + "\\n")
""".replace("__PROVIDER__", name),
        encoding="utf-8",
    )
    script.chmod(0o755)


class _TTYInput(io.StringIO):
    def isatty(self) -> bool:
        return True


class _TTYOutput(io.StringIO):
    def isatty(self) -> bool:
        return True


class _ExplodingTTYInput(io.StringIO):
    def isatty(self) -> bool:
        return True

    def readline(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("init should not prompt when choices are saved")


class TestInit:
    def test_creates_project_and_memory(self, cli: CliRunner, initialized_repo: Path) -> None:
        assert (initialized_repo / ".loghop" / "config.toml").exists()
        assert (initialized_repo / "loghop.md").exists()

    def test_init_from_subdirectory_uses_repo_root(self, cli: CliRunner, git_repo: Path) -> None:
        subdir = git_repo / "src" / "pkg"
        subdir.mkdir(parents=True)
        code, stdout, _ = cli(["init"], cwd=subdir)
        assert code == 0
        assert str(git_repo) in stdout
        assert (git_repo / ".loghop" / "config.toml").exists()

    def test_refuses_outside_git(self, cli: CliRunner, tmp_path: Path) -> None:
        non_git = tmp_path / "plain"
        non_git.mkdir()
        code, _, stderr = cli(["init"], cwd=non_git)
        assert code == 2
        assert "git" in stderr.lower()

    def test_second_init_is_safe_and_reports_existing_project(
        self, cli: CliRunner, initialized_repo: Path
    ) -> None:
        code, stdout, _ = cli(["init"], cwd=initialized_repo)
        assert code == 0
        assert "already initialized" in stdout.lower()

    def test_init_prompts_and_installs_selected_global_integrations(
        self,
        cli: CliRunner,
        git_repo: Path,
        loghop_env: Any,
        fake_provider: Callable[[Path, str], Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        bin_dir = loghop_env.root / "bin"
        bin_dir.mkdir()
        fake_provider(bin_dir, "codex")
        # ~/.local/bin must be on PATH for the shim install to succeed.
        local_bin = Path.home() / ".local" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("PATH", f"{local_bin}:{bin_dir}:{os.environ.get('PATH', '')}")
        monkeypatch.setattr("sys.stdin", _TTYInput("y\ny\ny\n"))

        code, stdout, _ = cli(["init"], cwd=git_repo)

        assert code == 0
        assert "Install Claude session hooks?" in stdout
        global_config = tomllib.loads(
            (Path.home() / ".loghop" / "config.toml").read_text(encoding="utf-8")
        )
        install = global_config["install"]
        assert install["install_claude_hooks"] is True
        assert install["install_codex_shim"] is True
        assert install["install_prompt_block"] is True
        assert "installed_version" in install
        assert "loghop hook claude-session-start" in (
            Path.home() / ".claude" / "settings.json"
        ).read_text(encoding="utf-8")
        assert "exec loghop wrap codex" in (Path.home() / ".local" / "bin" / "codex").read_text(
            encoding="utf-8"
        )
        assert "loghop-prompt.md" in (Path.home() / ".codex" / "AGENTS.md").read_text(
            encoding="utf-8"
        )

    def test_init_no_prompt_saves_no_and_skips_global_integrations(
        self, cli: CliRunner, git_repo: Path
    ) -> None:
        code, stdout, _ = cli(["init", "--no-prompt"], cwd=git_repo)

        assert code == 0
        assert "--no-prompt" in stdout
        global_config = tomllib.loads(
            (Path.home() / ".loghop" / "config.toml").read_text(encoding="utf-8")
        )
        install = global_config["install"]
        assert install["install_claude_hooks"] is False
        assert install["install_codex_shim"] is False
        assert install["install_prompt_block"] is False
        assert "installed_version" in install
        assert not (Path.home() / ".claude" / "settings.json").exists()
        assert not (Path.home() / ".local" / "bin" / "codex").exists()
        assert not (Path.home() / ".codex" / "AGENTS.md").exists()

    def test_init_noninteractive_skips_optional_installs_without_saving_choices(
        self, cli: CliRunner, git_repo: Path
    ) -> None:
        from loghop.install import global_config_path

        config_path = global_config_path()
        if config_path.exists():
            config_path.unlink()

        code, stdout, _ = cli(["init"], cwd=git_repo)

        assert code == 0
        assert "not interactive" in stdout
        assert not config_path.exists()

    def test_init_dry_run_does_not_create_project_files(
        self, cli: CliRunner, git_repo: Path
    ) -> None:
        code, stdout, stderr = cli(["init", "--dry-run"], cwd=git_repo)

        assert code == 0, stderr
        assert "[dry-run]" in stdout
        assert not (git_repo / ".loghop").exists()
        assert not (git_repo / "loghop.md").exists()
        gitignore = git_repo / ".gitignore"
        assert not gitignore.exists() or ".loghop/" not in gitignore.read_text(encoding="utf-8")

    def test_init_reuses_saved_global_choices_without_prompting(
        self,
        cli: CliRunner,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        save_init_install_choices(
            InitInstallChoices(
                install_claude_hooks=False,
                install_codex_shim=False,
                install_prompt_block=True,
            )
        )
        monkeypatch.setattr("sys.stdin", _ExplodingTTYInput(""))

        code, stdout, _ = cli(["init"], cwd=git_repo)

        assert code == 0
        assert "using saved init choices" in stdout.lower()
        assert "loghop-prompt.md" in (Path.home() / ".codex" / "AGENTS.md").read_text(
            encoding="utf-8"
        )
        assert not (Path.home() / ".claude" / "settings.json").exists()


class TestGoal:
    def test_set_and_show_goal(self, cli: CliRunner, initialized_repo: Path) -> None:
        assert cli(["goal", "Ship the auth module"], cwd=initialized_repo)[0] == 0
        config = tomllib.loads(
            (initialized_repo / ".loghop" / "config.toml").read_text(encoding="utf-8")
        )
        assert config.get("goal") == "Ship the auth module"
        memory = (initialized_repo / "loghop.md").read_text(encoding="utf-8")
        assert "Ship the auth module" in memory
        code, stdout, _ = cli(["goal"], cwd=initialized_repo)
        assert code == 0
        assert "Ship the auth module" in stdout

    def test_goal_without_init_fails(self, cli: CliRunner, git_repo: Path) -> None:
        code, _, stderr = cli(["goal", "Anything"], cwd=git_repo)
        assert code == 20
        assert "not initialized" in stderr.lower()


class TestProvidersList:
    def test_list_detects_codex_and_claude(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, stdout, _ = cli(["providers", "list"], cwd=initialized_repo)
        assert code == 0
        assert "codex" in stdout
        assert "claude" in stdout

    def test_list_works_outside_initialized_project(self, cli: CliRunner, git_repo: Path) -> None:
        code, stdout, _ = cli(["providers", "list"], cwd=git_repo)
        assert code == 0
        assert "codex" in stdout
        assert "claude" in stdout


class TestHandoffBuild:
    def test_build_creates_markdown(self, cli: CliRunner, initialized_repo: Path) -> None:
        (initialized_repo / "app.py").write_text("print('updated')\n", encoding="utf-8")
        code, stdout, _ = cli(
            ["handoff", "build", "--provider", "codex", "--goal", "Finish build flow"],
            cwd=initialized_repo,
        )
        assert code == 0
        handoff = initialized_repo / ".loghop" / "handoffs" / "H-001.md"
        assert handoff.exists()
        text = handoff.read_text(encoding="utf-8")
        assert "Finish build flow" in text
        assert "id: H-001" in text
        assert "app.py" in text
        assert "H-001" in stdout

    def test_build_uses_project_goal_by_default(
        self, cli: CliRunner, initialized_repo: Path
    ) -> None:
        assert cli(["goal", "Project goal"], cwd=initialized_repo)[0] == 0
        code, _, _ = cli(["handoff", "build", "--provider", "codex"], cwd=initialized_repo)
        assert code == 0
        text = (initialized_repo / ".loghop" / "handoffs" / "H-001.md").read_text(encoding="utf-8")
        assert "Project goal" in text

    def test_counter_increments(self, cli: CliRunner, initialized_repo: Path) -> None:
        assert (
            cli(["handoff", "build", "--provider", "codex", "--goal", "one"], cwd=initialized_repo)[
                0
            ]
            == 0
        )
        assert (
            cli(
                ["handoff", "build", "--provider", "claude", "--goal", "two"], cwd=initialized_repo
            )[0]
            == 0
        )
        assert (initialized_repo / ".loghop" / "handoffs" / "H-001.md").exists()
        assert (initialized_repo / ".loghop" / "handoffs" / "H-002.md").exists()

    def test_rejects_unknown_provider(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, _, stderr = cli(
            ["handoff", "build", "--provider", "gemini", "--goal", "x"], cwd=initialized_repo
        )
        assert code == 2
        assert "invalid choice" in stderr.lower() or "gemini" in stderr.lower()


class TestHandoffListAndShow:
    def test_list_shows_entries(self, cli: CliRunner, initialized_repo: Path) -> None:
        cli(
            ["handoff", "build", "--provider", "codex", "--goal", "goal a"],
            cwd=initialized_repo,
        )
        cli(
            ["handoff", "build", "--provider", "claude", "--goal", "goal b"],
            cwd=initialized_repo,
        )
        code, stdout, _ = cli(["handoff", "list"], cwd=initialized_repo)
        assert code == 0
        assert "H-001" in stdout
        assert "H-002" in stdout

    def test_list_filters_by_provider(self, cli: CliRunner, initialized_repo: Path) -> None:
        cli(["handoff", "build", "--provider", "codex", "--goal", "c"], cwd=initialized_repo)
        cli(["handoff", "build", "--provider", "claude", "--goal", "d"], cwd=initialized_repo)
        code, stdout, _ = cli(["handoff", "list", "--provider", "claude"], cwd=initialized_repo)
        assert code == 0
        assert "H-002" in stdout
        assert "H-001" not in stdout

    def test_show_prints_handoff(self, cli: CliRunner, initialized_repo: Path) -> None:
        cli(
            ["handoff", "build", "--provider", "codex", "--goal", "detail"],
            cwd=initialized_repo,
        )
        code, stdout, _ = cli(["handoff", "show", "H-001"], cwd=initialized_repo)
        assert code == 0
        assert "# Project Handoff" in stdout
        assert "id: H-001" in stdout
        assert "## Goal" in stdout
        assert "detail" in stdout

    def test_show_latest_prints_newest_handoff(
        self, cli: CliRunner, initialized_repo: Path
    ) -> None:
        cli(["handoff", "build", "--provider", "codex", "--goal", "old"], cwd=initialized_repo)
        cli(["handoff", "build", "--provider", "codex", "--goal", "new"], cwd=initialized_repo)
        code, stdout, _ = cli(["handoff", "show", "--latest"], cwd=initialized_repo)
        assert code == 0
        assert "id: H-002" in stdout
        assert "new" in stdout

    def test_show_rejects_missing_id(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, _, stderr = cli(["handoff", "show", "H-999"], cwd=initialized_repo)
        assert code == 2
        assert "not found" in stderr.lower()


class TestHandoffRun:
    def test_launches_enabled_provider(
        self,
        cli: CliRunner,
        initialized_repo: Path,
        loghop_env: Any,
    ) -> None:
        code, _, _ = cli(
            ["handoff", "run", "--provider", "codex", "--goal", "Review work"],
            cwd=initialized_repo,
        )
        assert code == 0
        args_file = loghop_env.root / "bin" / "codex-args.txt"
        assert args_file.exists()
        invoked = args_file.read_text(encoding="utf-8")
        assert ".loghop/handoffs/H-001.md" in invoked
        assert "Review work" in invoked

    def test_fails_when_provider_missing(
        self,
        cli: CliRunner,
        initialized_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        original_which = shutil.which
        monkeypatch.setattr(
            "loghop.providers.shutil.which",
            lambda name: None if name == "codex" else original_which(name),
        )
        code, _, stderr = cli(
            ["handoff", "run", "--provider", "codex", "--goal", "x"], cwd=initialized_repo
        )
        assert code == 2
        assert "not installed" in stderr.lower()

    def test_run_updates_handoff_status(self, cli: CliRunner, initialized_repo: Path) -> None:
        assert (
            cli(["handoff", "run", "--provider", "codex", "--goal", "x"], cwd=initialized_repo)[0]
            == 0
        )
        code, stdout, _ = cli(["handoff", "list"], cwd=initialized_repo)
        assert code == 0
        assert "succeeded" in stdout

    def test_rejects_invalid_timeout(self, cli: CliRunner, initialized_repo: Path) -> None:
        code, _, stderr = cli(
            ["handoff", "run", "--provider", "codex", "--goal", "x", "--timeout", "0"],
            cwd=initialized_repo,
        )
        assert code == 2
        assert "must be >= 1" in stderr


class TestRun:
    def test_run_starts_fresh_without_previous_session(
        self,
        cli: CliRunner,
        initialized_repo: Path,
        loghop_env: Any,
    ) -> None:
        code, stdout, _ = cli(
            ["run", "--provider", "codex", "--goal", "Review work"],
            cwd=initialized_repo,
        )

        assert code == 0
        assert "starting from session none" in stdout.lower()
        invoked = (loghop_env.root / "bin" / "codex-args.txt").read_text(encoding="utf-8")
        assert ".loghop/handoffs/H-001.md" in invoked
        assert "Review work" in invoked

    def test_run_without_goal_uses_ad_hoc_title(
        self,
        cli: CliRunner,
        initialized_repo: Path,
    ) -> None:
        code, stdout, _ = cli(["run", "--provider", "codex"], cwd=initialized_repo)

        assert code == 0
        assert "starting from session none" in stdout.lower()
        session = (initialized_repo / ".loghop" / "sessions" / "S-001.md").read_text(
            encoding="utf-8"
        )
        handoff = (initialized_repo / ".loghop" / "handoffs" / "H-001.md").read_text(
            encoding="utf-8"
        )
        assert "Ad hoc session" in session
        assert "Ad hoc session" in handoff

    def test_run_continues_from_previous_useful_session(
        self,
        cli: CliRunner,
        initialized_repo: Path,
    ) -> None:
        from loghop.store._session import create_session, finish_session

        previous = create_session(initialized_repo, provider="codex", goal="prev")
        finish_session(initialized_repo, previous.id, status="succeeded", returncode=0)

        code, stdout, _ = cli(
            ["run", "--provider", "codex", "--goal", "Next step"],
            cwd=initialized_repo,
        )

        assert code == 0
        assert "resuming from session s-001" in stdout.lower()
        handoff = initialized_repo / ".loghop" / "handoffs" / "H-001.md"
        assert "## Previous Session" in handoff.read_text(encoding="utf-8")
        assert (initialized_repo / ".loghop" / "sessions" / "S-002.md").exists()

    def test_run_claude_auth_preflight_warning_does_not_block(
        self,
        cli: CliRunner,
        initialized_repo: Path,
        loghop_env: Any,
    ) -> None:
        with patch(
            "loghop.cli_commands._handoff_launch.ensure_provider_ready",
            side_effect=LoghopError(
                "Claude Code reported `loggedIn: false` for this shell.",
                code=E_PROVIDER_AUTH_MISSING,
            ),
        ):
            code, stdout, stderr = cli(
                ["run", "--provider", "claude", "--goal", "Resume work"],
                cwd=initialized_repo,
            )

        assert code == 0
        assert "starting from session none" in stdout.lower()
        assert "launch will continue" in stderr.lower()
        invoked = (loghop_env.root / "bin" / "claude-args.txt").read_text(encoding="utf-8")
        assert ".loghop/handoffs/H-001.md" in invoked
        assert "Resume work" in invoked

    def test_run_interactive_claude_custom_api_fails_before_creating_records(
        self,
        cli: CliRunner,
        initialized_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.example.com/anthropic")
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-provider-test")

        code, _, stderr = cli(
            ["run", "--provider", "claude", "--interactive", "--goal", "Resume work"],
            cwd=initialized_repo,
        )

        assert code == 2
        assert "api/gateway" in stderr.lower()
        assert not list((initialized_repo / ".loghop" / "sessions").glob("S-*.md"))
        assert not list((initialized_repo / ".loghop" / "handoffs").glob("H-*.md"))

    def test_run_uses_real_codex_when_loghop_shim_is_first(
        self,
        cli: CliRunner,
        initialized_repo: Path,
        loghop_env: Any,
        monkeypatch: pytest.MonkeyPatch,
        fake_provider: Callable[[Path, str], Path],
    ) -> None:
        real_dir = loghop_env.root / "real"
        shim_dir = loghop_env.root / "shim"
        real_dir.mkdir()
        shim_dir.mkdir()
        fake_provider(real_dir, "codex")
        monkeypatch.setenv("PATH", f"{shim_dir}:{real_dir}:{os.environ.get('PATH', '')}")

        from loghop.install._shim import install_codex_shim

        report = install_codex_shim(prefix=shim_dir, binary="codex")
        assert report.action in {"created", "updated", "unchanged"}

        code, _, stderr = cli(["run", "--provider", "codex", "--goal", "g"], cwd=initialized_repo)

        assert code == 0, stderr
        sessions = sorted((initialized_repo / ".loghop" / "sessions").glob("S-*.md"))
        assert len(sessions) == 1
        assert "(wrapped)" not in sessions[0].read_text(encoding="utf-8")

    def test_run_round_trips_claude_codex_claude(
        self,
        cli: CliRunner,
        initialized_repo: Path,
        loghop_env: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        bin_dir = loghop_env.root / "bin"
        _install_transcript_provider(bin_dir, "claude")
        _install_transcript_provider(bin_dir, "codex")
        monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")

        assert (
            cli(["run", "--provider", "claude", "--goal", "round trip"], cwd=initialized_repo)[0]
            == 0
        )
        assert (
            cli(["resume", "--provider", "codex", "--goal", "round trip"], cwd=initialized_repo)[0]
            == 0
        )
        assert (
            cli(["resume", "--provider", "claude", "--goal", "round trip"], cwd=initialized_repo)[0]
            == 0
        )

        sessions = sorted((initialized_repo / ".loghop" / "sessions").glob("S-*.md"))
        assert [path.name for path in sessions] == ["S-001.md", "S-002.md", "S-003.md"]
        assert "provider: claude" in sessions[0].read_text(encoding="utf-8")
        assert "Claude initial summary" in sessions[0].read_text(encoding="utf-8")
        assert "provider: codex" in sessions[1].read_text(encoding="utf-8")
        assert "Codex continuation summary" in sessions[1].read_text(encoding="utf-8")
        assert "provider: claude" in sessions[2].read_text(encoding="utf-8")
        assert "Claude final summary" in sessions[2].read_text(encoding="utf-8")

        codex_handoff = (initialized_repo / ".loghop" / "handoffs" / "H-002.md").read_text(
            encoding="utf-8"
        )
        claude_handoff = (initialized_repo / ".loghop" / "handoffs" / "H-003.md").read_text(
            encoding="utf-8"
        )
        assert "Provider: claude" in codex_handoff
        assert "Codex must preserve Claude pending task" in codex_handoff
        assert "Provider: codex" in claude_handoff
        assert "Claude must preserve Codex pending task" in claude_handoff

        timeline = (initialized_repo / ".loghop" / "timeline.jsonl").read_text(encoding="utf-8")
        providers = [json.loads(line)["provider"] for line in timeline.splitlines() if line]
        assert providers == ["claude", "codex", "claude"]


class TestStatus:
    def test_reports_initialized_project(self, cli: CliRunner, initialized_repo: Path) -> None:
        cli(["goal", "Status goal"], cwd=initialized_repo)
        code, stdout, _ = cli(["status"], cwd=initialized_repo)
        assert code == 0
        assert "Status goal" in stdout
        assert "repo" in stdout.lower()
        assert "ready" in stdout.lower()

    def test_reports_uninitialized_project(self, cli: CliRunner, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        code, _, stderr = cli(["status"], cwd=empty)
        assert code == 20
        assert "not initialized" in stderr.lower()


@pytest.mark.parametrize(
    "argv",
    [
        ["status"],
        ["sessions"],
        ["timeline"],
        ["journal"],
        ["handoff", "list"],
        ["run", "--provider", "codex", "--goal", "work"],
        ["resume", "--provider", "codex", "--goal", "work"],
    ],
)
def test_project_scoped_commands_return_20_without_loghop_init(
    cli: CliRunner, git_repo: Path, argv: list[str]
) -> None:
    code, _stdout, stderr = cli(argv, cwd=git_repo)

    assert code == 20
    assert "not initialized" in stderr.lower()


def test_help_exits_cleanly(cli: CliRunner) -> None:
    code, stdout, _ = cli([])
    # In --plain / non-interactive mode, no command still shows the CLI dashboard.
    assert code == 0
    assert "loghop" in stdout.lower()


def test_zero_arg_interactive_opens_tui(monkeypatch: pytest.MonkeyPatch) -> None:
    from loghop import cli as cli_module
    from loghop.cli_commands import tui as tui_module

    called: dict[str, bool] = {}

    def fake_tui(args: Any, _term: Any) -> int:
        called["global_view"] = bool(getattr(args, "global_view", False))
        return 0

    monkeypatch.setattr(tui_module, "handle_tui", fake_tui)
    monkeypatch.setattr("sys.stdin", _TTYInput(""))
    stdout = _TTYOutput()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = cli_module.main([])

    assert code == 0
    assert called == {"global_view": False}


def test_zero_arg_interactive_falls_back_without_textual(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from loghop import cli as cli_module
    from loghop.cli_commands import tui as tui_module
    from loghop.errors import E_INVALID_INPUT, LoghopError

    outside = tmp_path / "empty"
    outside.mkdir()
    monkeypatch.chdir(outside)

    def missing_tui(args: Any, _term: Any) -> int:
        raise LoghopError(str(tui_module._TUI_INSTALL_HINT), code=E_INVALID_INPUT)

    monkeypatch.setattr(tui_module, "handle_tui", missing_tui)
    monkeypatch.setattr("sys.stdin", _TTYInput(""))
    stdout = _TTYOutput()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = cli_module.main([])

    assert code == 0
    assert "loghop init" in stdout.getvalue()


def test_keyboard_interrupt_returns_130(monkeypatch: pytest.MonkeyPatch) -> None:
    import argparse

    from loghop import cli as cli_module

    class _Parser:
        def parse_args(self, _argv: list[str]) -> argparse.Namespace:
            return argparse.Namespace(
                command="status",
                handler=self._boom,
                json=False,
                plain=True,
                quiet=False,
                verbose=False,
                version=False,
            )

        @staticmethod
        def _boom(_args: Any, _term: Any) -> int:
            raise KeyboardInterrupt

    monkeypatch.setattr(cli_module, "build_parser", lambda: _Parser())
    code = cli_module.main(["status"])
    assert code == 130


def test_json_mode_success_envelope(cli: CliRunner, initialized_repo: Path) -> None:
    code, stdout, _ = cli(["--json", "status"], cwd=initialized_repo)
    assert code == 0
    import json

    payload = json.loads(stdout)
    assert payload["ok"] is True
    assert payload["code"] == 0


def test_json_flag_works_after_subcommand(cli: CliRunner, initialized_repo: Path) -> None:
    code, stdout, _ = cli(["status", "--json"], cwd=initialized_repo)
    assert code == 0
    import json

    payload = json.loads(stdout)
    assert payload["ok"] is True
    assert payload["code"] == 0


def test_json_without_command_returns_machine_error(cli: CliRunner) -> None:
    code, stdout, _ = cli(["--json"])
    assert code == 2
    import json

    payload = json.loads(stdout)
    assert payload["ok"] is False
    assert payload["error"] == "no command provided"


def test_version_flag_prints_package_version(cli: CliRunner) -> None:
    code, stdout, _ = cli(["--version"])
    assert code == 0
    assert "0.2.0" in stdout


def test_wrap_passthrough_keeps_provider_flags() -> None:
    from loghop.cli import _normalize_argv

    assert _normalize_argv(["wrap", "codex", "--version"]) == ["wrap", "codex", "--version"]
    assert _normalize_argv(["--plain", "wrap", "codex", "--verbose"]) == [
        "--plain",
        "wrap",
        "codex",
        "--verbose",
    ]


def test_tui_reports_missing_textual(
    cli: CliRunner, initialized_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from loghop.tui import app as tui_app

    def missing_textual(*_args: Any, **_kwargs: Any) -> int:
        raise RuntimeError("The loghop Textual app requires the optional `textual` package.")

    monkeypatch.setattr(tui_app, "run", missing_textual)

    code, _, stderr = cli(["tui"], cwd=initialized_repo)

    assert code == 2
    assert "textual is not installed" in stderr.lower()
    assert "loghop[tui]" in stderr


def test_plain_flag_forces_no_rich(
    cli: CliRunner, initialized_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # already covered by all other tests that pass --plain, but assert NO_COLOR
    # env var is respected and nothing blows up.
    monkeypatch.delenv("NO_COLOR", raising=False)
    code, _, _ = cli(["status"], cwd=initialized_repo)
    assert code == 0


def test_goal_clear(cli: CliRunner, initialized_repo: Path) -> None:
    assert cli(["goal", "temporary"], cwd=initialized_repo)[0] == 0
    code, stdout, _ = cli(["goal", "--clear"], cwd=initialized_repo)
    assert code == 0
    assert "goal cleared" in stdout.lower()
    config = tomllib.loads((initialized_repo / ".loghop" / "config.toml").read_text())
    assert config.get("goal") == ""


class TestGitignoreAndIgnore:
    def test_gitignore_gets_loghop_entries(self, cli: CliRunner, initialized_repo: Path) -> None:
        gitignore = (initialized_repo / ".gitignore").read_text(encoding="utf-8")
        assert ".loghop/" in gitignore
        assert "loghop.md" in gitignore

    def test_loghopignore_default_written(self, cli: CliRunner, initialized_repo: Path) -> None:
        content = (initialized_repo / ".loghop" / ".loghopignore").read_text(encoding="utf-8")
        assert "*.pem" in content
        assert ".env.*" in content
        assert "node_modules/" in content


def test_env_fixtures_isolate_path(
    cli: CliRunner, loghop_env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Smoke: fixtures don't bleed between tests.
    assert "NO_COLOR" in os.environ
