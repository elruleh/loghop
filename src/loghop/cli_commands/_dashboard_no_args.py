import argparse
from pathlib import Path

from loghop.cli_commands._helpers import resolve_default_provider
from loghop.cli_commands.dashboard import handle_dashboard
from loghop.redact import redact_text
from loghop.store import find_project_root
from loghop.store._registry import load_registry
from loghop.store._session import latest_session
from loghop.terminal import Terminal, TerminalOptions


def handle_dashboard_no_args(args: argparse.Namespace) -> int:
    term = Terminal(
        TerminalOptions(
            plain=getattr(args, "plain", False),
            quiet=getattr(args, "quiet", False),
            verbose=getattr(args, "verbose", False),
            json_mode=getattr(args, "json", False),
        )
    )
    project_root = find_project_root(Path.cwd())
    if project_root is not None and not getattr(args, "global_view", False):
        from loghop.store import load_config, project_paths

        paths = project_paths(project_root)
        config = load_config(paths)
        goal = redact_text(config.goal or "") or "(not set)"
        last = latest_session(paths)
        provider_hint = resolve_default_provider(project_root)
        rows: list[tuple[str, str]] = [
            ("repo", project_root.name),
            ("goal", goal),
        ]
        if last:
            rows.append(("last session", f"{last.id} ({last.provider})"))
            summary = last.summary or ""
            if summary:
                rows.append(("summary", summary[:80] + ("\u2026" if len(summary) > 80 else "")))  # noqa: PLR2004
        else:
            rows.append(("last session", "none yet"))
        if provider_hint:
            rows.append(("default provider", provider_hint))
        term.section("loghop", rows)
        if provider_hint:
            term.info(f"Run `loghop run` (uses {provider_hint})")
        else:
            term.info("Install codex or claude on PATH to launch a provider")
        return 0

    projects = load_registry()
    if not projects:
        term.info("No loghop projects registered yet")
        term.info("Run `loghop init` inside a Git repo to get started")
        return 0
    return handle_dashboard(args, term)
