from __future__ import annotations

import argparse
from typing import Any, Never

from loghop.cli_commands.admin import (
    handle_completion,
    handle_doctor,
    handle_init,
    handle_install,
    handle_providers_list,
    handle_uninstall,
)
from loghop.cli_commands.annotate import handle_session_annotate
from loghop.cli_commands.backup import handle_backup_create, handle_backup_restore
from loghop.cli_commands.dashboard import (
    handle_dashboard,
    handle_projects_cleanup,
    handle_projects_purge,
    handle_projects_remove,
    handle_projects_show,
)
from loghop.cli_commands.goal import handle_goal
from loghop.cli_commands.handoff import (
    handle_handoff_build,
    handle_handoff_list,
    handle_handoff_run,
    handle_handoff_show,
)
from loghop.cli_commands.health import handle_health
from loghop.cli_commands.hook import handle_hook
from loghop.cli_commands.install import (
    handle_install_aliases,
    handle_install_hooks,
    handle_install_prompt,
    handle_install_shims,
    handle_uninstall_aliases,
)
from loghop.cli_commands.journal import handle_journal
from loghop.cli_commands.metrics import handle_metrics
from loghop.cli_commands.migrate import handle_migrate
from loghop.cli_commands.resume import handle_resume
from loghop.cli_commands.run import handle_run
from loghop.cli_commands.sessions import (
    handle_sessions_delete,
    handle_sessions_list,
    handle_sessions_reconcile,
    handle_sessions_show,
)
from loghop.cli_commands.status import handle_status
from loghop.cli_commands.timeline import handle_timeline
from loghop.cli_commands.topics import (
    handle_topics_close,
    handle_topics_list,
    handle_topics_rename,
    handle_topics_show,
    handle_topics_switch,
)
from loghop.cli_commands.tui import handle_tui
from loghop.cli_commands.wrap import handle_wrap
from loghop.providers import SUPPORTED_PROVIDER_NAMES
from loghop.store._constants import DEFAULT_TIMEOUT

_PROVIDER_CHOICES = SUPPORTED_PROVIDER_NAMES
_VISIBLE_COMMANDS_METAVAR = (
    "{init,goal,status,health,metrics,backup,migrate,run,sessions,projects,doctor,tui,"
    "handoff,resume,topics,install,uninstall,completion,providers,journal,timeline,wrap}"
)


class _ParseError(Exception):
    def __init__(self, parser: argparse.ArgumentParser, message: str) -> None:
        super().__init__(message)
        self.parser = parser
        self.message = message


class _LoghopArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise _ParseError(self, message)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid integer value: {value}") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = _LoghopArgumentParser(
        prog="loghop",
        description=("Keep Claude Code and Codex in sync on the same project."),
        epilog=(
            "get started:\n"
            "  loghop init                    set up in a git repo\n"
            "  loghop run                     resume work\n"
            '  loghop goal "ship auth"       optional: set a default goal\n'
            "\n"
            "run `loghop <command> --help` for details."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="emit a JSON envelope")
    parser.add_argument("--plain", action="store_true", help="disable color and box drawing")
    parser.add_argument("--quiet", action="store_true", help="only print errors")
    parser.add_argument("--verbose", action="store_true", help="print extra details")
    parser.add_argument("--version", action="store_true", help="print the installed version")
    parser.add_argument(
        "--global",
        dest="global_view",
        action="store_true",
        help="show the projects view even inside a loghop repo",
    )
    subparsers = parser.add_subparsers(dest="command", metavar=_VISIBLE_COMMANDS_METAVAR)

    _add_init_subparser(subparsers)
    _add_goal_subparser(subparsers)
    _add_run_subparser(subparsers)
    _add_sessions_subparser(subparsers)
    _add_projects_subparser(subparsers)
    _add_doctor_subparser(subparsers)
    _add_tui_subparser(subparsers)
    _add_health_subparser(subparsers)
    _add_metrics_subparser(subparsers)
    _add_backup_subparser(subparsers)
    _add_migrate_subparser(subparsers)
    _add_handoff_subparser(subparsers)
    _add_resume_subparser(subparsers)
    _add_topics_subparser(subparsers)
    _add_install_subparser(subparsers)
    _add_uninstall_subparser(subparsers)
    _add_completion_subparser(subparsers)
    _add_providers_subparser(subparsers)
    _add_journal_subparser(subparsers)
    _add_timeline_subparser(subparsers)
    _add_wrap_subparser(subparsers)
    _add_status_subparser(subparsers)
    _add_install_prompt_subparser(subparsers)
    _add_install_hooks_subparser(subparsers)
    _add_install_shims_subparser(subparsers)
    _add_install_aliases_subparser(subparsers)
    _add_uninstall_aliases_subparser(subparsers)
    _add_hook_subparser(subparsers)

    return parser


def _add_init_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "init",
        help="initialize the current Git repo and offer optional integrations",
    )
    p.add_argument(
        "--no-prompt",
        action="store_true",
        help="skip optional setup prompts and assume No (for CI/scripted installs)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="preview install changes without writing anything to disk",
    )
    p.add_argument(
        "--force-reinstall",
        action="store_true",
        help="ignore saved choices and re-run install steps from scratch",
    )
    p.set_defaults(handler=handle_init)


def _add_install_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "install",
        help="install or repair global integrations without initializing a project",
    )
    p.add_argument(
        "--no-prompt",
        action="store_true",
        help="skip optional setup prompts and assume No (for CI/scripted installs)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="preview install changes without writing anything to disk",
    )
    p.add_argument(
        "--force-reinstall",
        action="store_true",
        help="ignore saved choices and re-run install steps from scratch",
    )
    p.set_defaults(handler=handle_install)


def _add_doctor_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "doctor",
        help="check install health and report fixes or warnings",
    )
    p.add_argument(
        "--fix",
        action="store_true",
        help="reinstall missing components and resolve detected issues",
    )
    p.set_defaults(handler=handle_doctor)


def _add_uninstall_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "uninstall",
        help="remove hooks, codex shim, and prompt assets",
    )
    p.add_argument(
        "--keep-config",
        action="store_true",
        help="preserve ~/.loghop/config.toml (saved init choices)",
    )
    p.add_argument(
        "--purge",
        action="store_true",
        help="also delete the entire ~/.loghop directory (config, registry, sessions, prompt file)",
    )
    p.add_argument("--dry-run", action="store_true", help="preview without writing")
    p.add_argument("-y", "--yes", action="store_true", help="skip confirmation prompt")
    p.set_defaults(handler=handle_uninstall)


def _add_completion_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "completion",
        help="print a shell completion script",
    )
    p.add_argument("shell", choices=("bash", "zsh", "fish"))
    p.set_defaults(handler=handle_completion)


def _add_providers_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("providers", help="inspect provider configuration")
    p.set_defaults(handler=handle_providers_list, providers_command="list")
    sub = p.add_subparsers(dest="providers_command", metavar="[list]", required=False)
    sub.default = "list"
    sub.add_parser("list", help="list currently available providers").set_defaults(
        handler=handle_providers_list
    )


def _add_goal_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("goal", help="set or show the project goal")
    p.add_argument("text", nargs="?", default=None, help="goal text (omit to print)")
    p.add_argument("--clear", action="store_true", help="clear the project goal")
    p.set_defaults(handler=handle_goal)


def _add_run_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "run",
        help="launch a provider, continuing from the previous useful session when possible",
    )
    p.add_argument(
        "target",
        nargs="?",
        help="project name or path (defaults to the current repo)",
    )
    _add_provider_goal_args(p)
    _add_topic_launch_args(p)
    _add_launch_args(p)
    p.set_defaults(handler=handle_run)


def _add_handoff_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("handoff", help="build and run handoffs")
    p.set_defaults(
        handler=handle_handoff_run,
        handoff_command="run",
        provider=None,
        goal=None,
        interactive=False,
        timeout=DEFAULT_TIMEOUT,
    )
    sub = p.add_subparsers(dest="handoff_command", required=False)
    sub.default = "run"

    h_build = sub.add_parser("build", help="build a handoff markdown artifact")
    _add_provider_goal_args(h_build)
    _add_topic_launch_args(h_build)
    h_build.set_defaults(handler=handle_handoff_build)

    h_run = sub.add_parser("run", help="build a handoff and launch the provider")
    _add_provider_goal_args(h_run)
    _add_topic_launch_args(h_run)
    _add_launch_args(h_run)
    h_run.set_defaults(handler=handle_handoff_run)

    h_list = sub.add_parser("list", help="list handoffs")
    h_list.add_argument("--provider", choices=_PROVIDER_CHOICES, help="filter by provider")
    h_list.set_defaults(handler=handle_handoff_list)

    h_show = sub.add_parser("show", help="show a handoff")
    h_show.add_argument("handoff_id", nargs="?", help="handoff id such as H-001")
    h_show.add_argument("--latest", action="store_true", help="show the most recent handoff")
    h_show.set_defaults(handler=handle_handoff_show)


def _add_status_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("status", help="show project status")
    p.set_defaults(handler=handle_status)


def _add_health_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("health", help="run project health checks")
    p.set_defaults(handler=handle_health)


def _add_metrics_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("metrics", help="export project metrics")
    p.add_argument(
        "--format",
        choices=("summary", "prometheus", "json", "yaml"),
        default="summary",
        help="output format (default: summary)",
    )
    p.set_defaults(handler=handle_metrics)


def _add_backup_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("backup", help="backup or restore local loghop data")
    sub = p.add_subparsers(dest="backup_command", required=True)
    create = sub.add_parser("create", help="create a tar.gz backup")
    create.add_argument("--output", help="archive path (default: .loghop/backups/...)")
    create.set_defaults(handler=handle_backup_create)
    restore = sub.add_parser("restore", help="restore a loghop backup")
    restore.add_argument("archive", help="backup archive path")
    restore.add_argument("-y", "--yes", action="store_true", help="skip confirmation")
    restore.set_defaults(handler=handle_backup_restore)


def _add_migrate_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("migrate", help="migrate local loghop metadata to this version")
    p.add_argument("--dry-run", action="store_true", help="report migrations without writing")
    p.set_defaults(handler=handle_migrate)


def _add_tui_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("tui", help="open the optional terminal user interface")
    p.add_argument(
        "--global",
        dest="global_view",
        action="store_true",
        help="start in the global projects view",
    )
    p.add_argument(
        "--tui-debug",
        action="store_true",
        help="enable TUI debug logging to .loghop/tui-debug.log",
    )
    p.set_defaults(handler=handle_tui)


def _add_journal_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "journal",
        help="aggregate sessions into a chronological diary",
    )
    p.add_argument(
        "--since",
        help="only include sessions newer than this (e.g. 7d, 12h, 2w)",
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "--all",
        action="store_true",
        help="aggregate across every registered project",
    )
    group.add_argument(
        "--project",
        help="aggregate one project by name or path (defaults to current repo)",
    )
    p.set_defaults(handler=handle_journal)


def _add_timeline_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "timeline",
        help="show the shared project timeline across providers",
    )
    p.add_argument("--provider", choices=_PROVIDER_CHOICES, help="filter by provider")
    p.add_argument("--since", help="only include events newer than this (e.g. 7d, 12h, 2w)")
    p.add_argument(
        "--all-status",
        action="store_true",
        help="include failed, interrupted, empty, and auth-failure events",
    )
    p.add_argument(
        "--limit",
        type=_positive_int,
        default=50,
        help="maximum events to show (default: 50)",
    )
    p.set_defaults(handler=handle_timeline)


def _add_install_prompt_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "install-prompt",
        help="advanced: install the loghop AGENTS.md / CLAUDE.md prompt block",
    )
    _hide_subparser_from_help(subparsers, "install-prompt")
    p.add_argument("--codex", action="store_true", help="install in codex AGENTS.md")
    p.add_argument("--claude", action="store_true", help="install in claude CLAUDE.md")
    p.add_argument(
        "--scope",
        choices=("user", "project"),
        default="user",
        help="advanced: write to home config (default) or only the current project",
    )
    p.add_argument("--uninstall", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="preview changes without writing")
    p.set_defaults(handler=handle_install_prompt)


def _add_install_hooks_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "install-hooks",
        help="advanced: install Claude Code session hooks",
    )
    _hide_subparser_from_help(subparsers, "install-hooks")
    p.add_argument(
        "--scope",
        choices=("user", "project"),
        default="user",
    )
    p.add_argument("--uninstall", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="preview changes without writing")
    p.set_defaults(handler=handle_install_hooks)


def _add_install_shims_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "install-shims",
        help="advanced: install the Codex PATH shim that delegates to `loghop wrap codex`",
    )
    _hide_subparser_from_help(subparsers, "install-shims")
    p.add_argument("--codex", action="store_true")
    p.add_argument(
        "--prefix",
        help="directory to install shims into (default: ~/.local/bin)",
    )
    p.add_argument("--uninstall", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="preview changes without writing")
    p.set_defaults(handler=handle_install_shims)


def _add_install_aliases_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "install-aliases",
        help="advanced: install shell aliases in local shell profile files",
    )
    _hide_subparser_from_help(subparsers, "install-aliases")
    p.add_argument("--uninstall", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="preview changes without writing")
    p.set_defaults(handler=handle_install_aliases)


def _add_uninstall_aliases_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "uninstall-aliases",
        help="advanced: uninstall shell aliases from local shell profile files",
    )
    _hide_subparser_from_help(subparsers, "uninstall-aliases")
    p.add_argument("--dry-run", action="store_true", help="preview changes without writing")
    p.set_defaults(handler=handle_uninstall_aliases)


def _add_hook_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "hook",
        help="internal: handle a stdin-JSON event from a provider hook",
    )
    _hide_subparser_from_help(subparsers, "hook")
    p.add_argument(
        "event",
        choices=("claude-session-start", "claude-session-end"),
    )
    p.set_defaults(handler=handle_hook)


def _hide_subparser_from_help(
    subparsers: argparse._SubParsersAction[Any],
    command: str,
) -> None:
    subparsers._choices_actions = [
        action for action in subparsers._choices_actions if getattr(action, "dest", None) != command
    ]


def _add_sessions_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "sessions",
        help="browse session history",
        description="Browse session history. Omit the subcommand to list sessions.",
    )
    p.set_defaults(handler=handle_sessions_list, sessions_command="list", provider=None)
    sub = p.add_subparsers(
        dest="sessions_command",
        metavar="[list|show|reconcile|annotate|delete]",
        required=False,
    )
    sub.default = "list"

    s_list = sub.add_parser("list", help="list sessions grouped by date")
    s_list.add_argument("--provider", choices=_PROVIDER_CHOICES, help="filter by provider")
    s_list.add_argument("--expand", action="store_true", help="show full details inline")
    s_list.set_defaults(handler=handle_sessions_list)

    s_show = sub.add_parser("show", help="show a session")
    s_show.add_argument("session_id", nargs="?", help="session id such as S-001")
    s_show.add_argument("--latest", action="store_true", help="show the most recent session")
    s_show.set_defaults(handler=handle_sessions_show)

    sub.add_parser(
        "reconcile",
        help="rescue stranded `running` sessions by sweeping the provider transcript",
    ).set_defaults(handler=handle_sessions_reconcile)

    s_annotate = sub.add_parser("annotate", help="add notes to a session")
    s_annotate.add_argument("session_id", nargs="?", help="session id (defaults to latest)")
    s_annotate.add_argument("--summary", help="session summary text")
    s_annotate.add_argument("--decision", action="append", help="decision made (can repeat)")
    s_annotate.add_argument("--todo", action="append", help="pending todo (can repeat)")
    s_annotate.add_argument("--done", action="append", help="completed todo (can repeat)")
    s_annotate.set_defaults(handler=handle_session_annotate)

    s_delete = sub.add_parser("delete", help="delete a session and its transcript")
    s_delete.add_argument("session_id", nargs="?", help="session id such as S-001")
    s_delete.add_argument("--latest", action="store_true", help="delete the most recent session")
    s_delete.add_argument("-y", "--yes", action="store_true", help="skip confirmation")
    s_delete.set_defaults(handler=handle_sessions_delete)


def _add_wrap_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "wrap",
        help="run the provider binary transparently and auto-capture the session",
    )
    p.add_argument("provider", choices=_PROVIDER_CHOICES)
    p.add_argument(
        "passthrough",
        nargs=argparse.REMAINDER,
        help="arguments forwarded verbatim to the provider",
    )
    p.set_defaults(handler=handle_wrap)


def _add_resume_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser("resume", help="resume from last session with a provider")
    p.add_argument(
        "target",
        nargs="?",
        help="project name or path (defaults to the current repo)",
    )
    p.add_argument(
        "--provider",
        choices=_PROVIDER_CHOICES,
        help="provider (defaults to last used or first available)",
    )
    p.add_argument("--goal", help="goal override for this run")
    _add_topic_launch_args(p)
    p.add_argument("--interactive", action="store_true", help="run the provider interactively")
    p.add_argument(
        "--timeout",
        type=_positive_int,
        default=DEFAULT_TIMEOUT,
        help=f"max seconds (default: {DEFAULT_TIMEOUT})",
    )
    p.set_defaults(handler=handle_resume)


def _add_projects_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "projects",
        help="manage registered projects",
        description="Manage registered projects. Omit the subcommand to list projects.",
    )
    p.set_defaults(handler=handle_dashboard, projects_command="list")
    sub = p.add_subparsers(
        dest="projects_command",
        metavar="[list|show|remove|purge|cleanup|prune]",
        required=False,
    )
    sub.default = "list"
    sub.add_parser("list", help="list all registered projects").set_defaults(
        handler=handle_dashboard
    )
    p_show = sub.add_parser("show", help="show a project's goal, sessions and handoffs without cd")
    p_show.add_argument("target", help="project name or absolute path")
    p_show.set_defaults(handler=handle_projects_show)
    p_remove = sub.add_parser(
        "remove", help="remove a project from the registry but keep local .loghop data"
    )
    p_remove.add_argument("target", help="project name or absolute path")
    p_remove.add_argument("-y", "--yes", action="store_true", help="skip confirmation")
    p_remove.set_defaults(handler=handle_projects_remove)
    p_purge = sub.add_parser(
        "purge", help="delete a project's local .loghop data and unregister it"
    )
    p_purge.add_argument("target", help="project name or absolute path")
    p_purge.add_argument("-y", "--yes", action="store_true", help="skip confirmation")
    p_purge.set_defaults(handler=handle_projects_purge)
    sub.add_parser("cleanup", help="remove missing projects from registry").set_defaults(
        handler=handle_projects_cleanup
    )
    sub.add_parser(
        "prune", help="alias for `cleanup` — drop registry entries whose path is gone"
    ).set_defaults(handler=handle_projects_cleanup)


def _add_topics_subparser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "topics",
        help="group related sessions into work topics",
        description="Manage work topics. Omit the subcommand to list topics.",
    )
    p.set_defaults(handler=handle_topics_list, topics_command="list")
    sub = p.add_subparsers(
        dest="topics_command",
        metavar="[list|show|switch|close|rename]",
        required=False,
    )
    sub.default = "list"
    sub.add_parser("list", help="list topics").set_defaults(handler=handle_topics_list)
    show = sub.add_parser("show", help="show a topic")
    show.add_argument("topic_id", help="topic id such as T-001")
    show.set_defaults(handler=handle_topics_show)
    switch = sub.add_parser("switch", help="make a topic active")
    switch.add_argument("topic_id", help="topic id such as T-001")
    switch.set_defaults(handler=handle_topics_switch)
    close = sub.add_parser("close", help="close a topic and clear it if active")
    close.add_argument("topic_id", help="topic id such as T-001")
    close.set_defaults(handler=handle_topics_close)
    rename = sub.add_parser("rename", help="rename a topic")
    rename.add_argument("topic_id", help="topic id such as T-001")
    rename.add_argument("title", help="new topic title")
    rename.set_defaults(handler=handle_topics_rename)


def _add_topic_launch_args(parser: argparse.ArgumentParser) -> None:
    topic_group = parser.add_mutually_exclusive_group()
    topic_group.add_argument("--topic", help="attach this run to topic id such as T-001")
    topic_group.add_argument(
        "--new-topic", action="store_true", help="start a new topic from the goal"
    )
    topic_group.add_argument(
        "--no-topic", action="store_true", help="do not attach this run to a topic"
    )


def _add_provider_goal_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--provider",
        choices=_PROVIDER_CHOICES,
        help="provider (defaults to last used or first available)",
    )
    parser.add_argument("--goal", help="goal override (defaults to project goal or ad hoc)")


def _add_launch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="run the provider interactively (blocks stdin)",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_int,
        default=DEFAULT_TIMEOUT,
        help=f"maximum seconds to wait for the provider (default: {DEFAULT_TIMEOUT})",
    )
