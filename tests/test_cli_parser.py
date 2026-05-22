from __future__ import annotations

import argparse

import pytest

from loghop.cli_parser import _LoghopArgumentParser, _ParseError, build_parser


class TestBuildParser:
    def test_builds_without_error(self) -> None:
        parser = build_parser()
        assert parser is not None
        assert parser.prog == "loghop"

    def test_top_level_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--json", "--plain", "--quiet", "--verbose"])
        assert args.json is True
        assert args.plain is True
        assert args.quiet is True
        assert args.verbose is True

    def test_version_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--version"])
        assert args.version is True

    def test_init_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["init", "--dry-run", "--no-prompt"])
        assert args.command == "init"
        assert args.dry_run is True
        assert args.no_prompt is True

    def test_goal_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["goal", "ship it"])
        assert args.command == "goal"
        assert args.text == "ship it"

    def test_goal_clear(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["goal", "--clear"])
        assert args.clear is True

    def test_status_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["status"])
        assert args.command == "status"

    def test_health_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["health"])
        assert args.command == "health"

    def test_metrics_prometheus_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["metrics", "--format", "prometheus"])
        assert args.command == "metrics"
        assert args.format == "prometheus"

    def test_backup_create_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["backup", "create", "--output", "x.tar.gz"])
        assert args.command == "backup"
        assert args.backup_command == "create"
        assert args.output == "x.tar.gz"

    def test_migrate_dry_run_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["migrate", "--dry-run"])
        assert args.command == "migrate"
        assert args.dry_run is True

    def test_handoff_build(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["handoff", "build", "--provider", "codex", "--goal", "test"])
        assert args.handoff_command == "build"
        assert args.provider == "codex"
        assert args.goal == "test"

    def test_handoff_run(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["handoff", "run", "--provider", "claude"])
        assert args.handoff_command == "run"
        assert args.provider == "claude"
        assert args.interactive is False

    def test_handoff_run_interactive(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["handoff", "run", "--provider", "codex", "--interactive"])
        assert args.interactive is True

    def test_handoff_run_timeout(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["handoff", "run", "--provider", "codex", "--timeout", "120"])
        assert args.timeout == 120

    def test_handoff_defaults_to_run(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["handoff"])
        assert args.handoff_command == "run"

    def test_run_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["run", "myproject", "--provider", "claude", "--goal", "next"])
        assert args.command == "run"
        assert args.target == "myproject"
        assert args.provider == "claude"
        assert args.goal == "next"

    def test_handoff_list(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["handoff", "list"])
        assert args.handoff_command == "list"

    def test_handoff_show(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["handoff", "show", "H-001"])
        assert args.handoff_command == "show"
        assert args.handoff_id == "H-001"

    def test_handoff_show_latest(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["handoff", "show", "--latest"])
        assert args.latest is True

    def test_sessions_list(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["sessions", "list"])
        assert args.sessions_command == "list"

    def test_sessions_defaults_to_list(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["sessions"])
        assert args.sessions_command == "list"

    def test_sessions_show(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["sessions", "show", "S-001"])
        assert args.sessions_command == "show"
        assert args.session_id == "S-001"

    def test_sessions_reconcile(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["sessions", "reconcile"])
        assert args.sessions_command == "reconcile"

    def test_sessions_annotate(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "sessions",
                "annotate",
                "S-001",
                "--summary",
                "did stuff",
                "--decision",
                "chose X",
                "--todo",
                "finish Y",
                "--done",
                "did Z",
            ]
        )
        assert args.sessions_command == "annotate"
        assert args.session_id == "S-001"
        assert args.summary == "did stuff"
        assert args.decision == ["chose X"]
        assert args.todo == ["finish Y"]
        assert args.done == ["did Z"]

    def test_wrap_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["wrap", "codex", "--some-arg"])
        assert args.command == "wrap"
        assert args.provider == "codex"

    def test_resume_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["resume", "--provider", "claude"])
        assert args.command == "resume"
        assert args.provider == "claude"

    def test_resume_with_target(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["resume", "myproject", "--provider", "codex"])
        assert args.target == "myproject"

    def test_projects_list(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["projects", "list"])
        assert args.projects_command == "list"

    def test_projects_defaults_to_list(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["projects"])
        assert args.projects_command == "list"

    def test_projects_show(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["projects", "show", "myproj"])
        assert args.projects_command == "show"
        assert args.target == "myproj"

    def test_projects_cleanup(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["projects", "cleanup"])
        assert args.projects_command == "cleanup"

    def test_projects_prune_alias(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["projects", "prune"])
        assert args.projects_command == "prune"

    def test_journal_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["journal", "--since", "7d"])
        assert args.command == "journal"
        assert args.since == "7d"

    def test_journal_all(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["journal", "--all"])
        assert args.all is True

    def test_timeline_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["timeline", "--provider", "codex", "--since", "12h"])
        assert args.command == "timeline"
        assert args.provider == "codex"
        assert args.since == "12h"

    def test_doctor_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["doctor", "--fix"])
        assert args.command == "doctor"
        assert args.fix is True

    def test_completion_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["completion", "bash"])
        assert args.command == "completion"
        assert args.shell == "bash"

    def test_providers_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["providers", "list"])
        assert args.command == "providers"
        assert args.providers_command == "list"

    def test_providers_defaults_to_list(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["providers"])
        assert args.command == "providers"
        assert args.providers_command == "list"

    def test_tui_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["tui"])
        assert args.command == "tui"

    def test_help_hides_internal_and_low_level_install_commands(self) -> None:
        parser = build_parser()
        help_text = parser.format_help()

        assert "install-prompt" not in help_text
        assert "install-hooks" not in help_text
        assert "install-shims" not in help_text
        assert "\n    status" in help_text
        assert "\n    hook" not in help_text

    def test_optional_list_commands_have_clear_help(self) -> None:
        parser = build_parser()

        sessions_help = parser.parse_args(["sessions"]).handler.__module__
        assert sessions_help == "loghop.cli_commands.sessions"
        projects_help = parser.parse_args(["projects"]).handler.__module__
        assert projects_help == "loghop.cli_commands.dashboard"

        subparsers = next(
            action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        )
        sessions_parser = subparsers.choices["sessions"]
        projects_parser = subparsers.choices["projects"]
        providers_parser = subparsers.choices["providers"]

        assert "Omit the subcommand to list sessions." in sessions_parser.format_help()
        assert "[list|show|reconcile|annotate|delete]" in sessions_parser.format_help()
        assert "Omit the subcommand to list projects." in projects_parser.format_help()
        assert "[list|show|remove|purge|cleanup|prune]" in projects_parser.format_help()
        assert "[list]" in providers_parser.format_help()
        assert "{list}" not in providers_parser.format_help()

    def test_hidden_low_level_commands_still_parse(self) -> None:
        parser = build_parser()

        prompt = parser.parse_args(["install-prompt", "--codex"])
        hooks = parser.parse_args(["install-hooks"])
        shims = parser.parse_args(["install-shims", "--codex"])
        hook = parser.parse_args(["hook", "claude-session-start"])

        assert prompt.command == "install-prompt"
        assert hooks.command == "install-hooks"
        assert shims.command == "install-shims"
        assert hook.command == "hook"


class TestLoghopArgumentParser:
    def test_raises_parse_error(self) -> None:
        parser = _LoghopArgumentParser(prog="test")
        parser.add_argument("--required", required=True)
        with pytest.raises(_ParseError):
            parser.parse_args([])

    def test_valid_args_no_error(self) -> None:
        parser = _LoghopArgumentParser(prog="test")
        parser.add_argument("name")
        args = parser.parse_args(["hello"])
        assert args.name == "hello"


class TestTimeoutValidation:
    def test_valid_timeout(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["handoff", "run", "--provider", "codex", "--timeout", "60"])
        assert args.timeout == 60

    def test_invalid_timeout_string(self) -> None:
        parser = build_parser()
        with pytest.raises(_ParseError):
            parser.parse_args(["handoff", "run", "--provider", "codex", "--timeout", "abc"])

    def test_zero_timeout_rejected(self) -> None:
        parser = build_parser()
        with pytest.raises(_ParseError):
            parser.parse_args(["handoff", "run", "--provider", "codex", "--timeout", "0"])

    def test_negative_timeout_rejected(self) -> None:
        parser = build_parser()
        with pytest.raises(_ParseError):
            parser.parse_args(["handoff", "run", "--provider", "codex", "--timeout", "-1"])
