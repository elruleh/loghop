import argparse
import dataclasses
from pathlib import Path

from loghop.cli_commands._helpers import require_project_config
from loghop.gittools import GitRepo
from loghop.providers import SUPPORTED_PROVIDER_NAMES, detect_all
from loghop.redact import redact_text
from loghop.store import find_project_root, list_handoffs
from loghop.store._io import safe_read_text
from loghop.terminal import Terminal


def handle_status(_args: argparse.Namespace, term: Terminal) -> int:
    cwd = Path.cwd()
    project_root = find_project_root(cwd)
    if project_root is None:
        term.warn("loghop is not initialized in this directory")
        term.capture_result({"initialized": False})
        return 20
    root, paths, config = require_project_config()
    repo = GitRepo(root)
    snapshot = repo.snapshot()
    handoffs = list_handoffs(paths)
    last_handoff = handoffs[0] if handoffs else None
    goal = config.goal or ""
    display_goal = redact_text(goal)
    providers = detect_all()
    enabled = sorted(name for name in SUPPORTED_PROVIDER_NAMES if providers[name].installed)
    ready = bool(enabled)
    memory_lines = 0
    if paths.memory.exists():
        memory_lines = len(safe_read_text(paths.memory).splitlines())
    rows: list[tuple[str, str]] = [
        ("repo", root.name),
        ("branch", f"{snapshot.branch or 'n/a'} · dirty: {'yes' if snapshot.dirty else 'no'}"),
        ("goal", display_goal or "(not set)"),
        ("providers", ", ".join(enabled) if enabled else "none"),
        ("ready", "yes" if ready else "no - install codex or claude"),
        ("memory", f"{memory_lines} lines"),
        ("handoffs", str(len(handoffs))),
    ]
    if last_handoff:
        rows.append(("last handoff", f"{last_handoff.id} → {last_handoff.provider}"))
    term.section("loghop status", rows)
    term.capture_result(
        {
            "initialized": True,
            "repo": root.name,
            "branch": snapshot.branch,
            "dirty": snapshot.dirty,
            "goal": display_goal,
            "providers_enabled": enabled,
            "ready": ready,
            "memory_lines": memory_lines,
            "handoffs": len(handoffs),
            "last_handoff": dataclasses.asdict(last_handoff) if last_handoff else None,
        }
    )
    return 0
