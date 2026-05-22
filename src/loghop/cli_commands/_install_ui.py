"""Tutorial-style UI helpers for `loghop init`.

Renders:
- a welcome / plan panel before any prompts run,
- per-component explanations next to the Y/n questions,
- a final summary panel with paths and next-step hints.

All helpers are no-ops in non-interactive modes (json, no_prompt, non-tty)
so CI output stays terse and scriptable.
"""

from pathlib import Path

from loghop.install import InstallStatus
from loghop.terminal import Terminal

_COMPONENT_BLURBS: dict[str, tuple[str, str]] = {
    "claude-hooks": (
        "Claude session hooks",
        "Adds SessionStart/SessionEnd entries in ~/.claude/settings.json so "
        "loghop can capture Claude Code sessions automatically.",
    ),
    "codex-shim": (
        "Codex PATH shim",
        "Drops a small wrapper at ~/.local/bin/codex so plain `codex` calls "
        "run through `loghop wrap` and record the session.",
    ),
    "prompt-block": (
        "Prompt block",
        "Writes ~/.loghop/loghop-prompt.md and @-includes it from CLAUDE.md "
        "and AGENTS.md so providers emit a structured summary block.",
    ),
}


def render_welcome(term: Terminal, status: InstallStatus, *, dry_run: bool) -> None:
    """Print the 'what loghop install does' panel."""
    if not _ui_enabled(term):
        return
    rows: list[tuple[str, str]] = [
        ("hooks", _state(status.claude_hooks)),
        ("shim", _state(status.codex_shim)),
        ("prompt", _state(status.prompt_block)),
    ]
    title = "loghop install — preview" if dry_run else "loghop install"
    term.section(title, rows)
    term.line("")
    for key in ("claude-hooks", "codex-shim", "prompt-block"):
        name, blurb = _COMPONENT_BLURBS[key]
        term.line(f"  • {name}", style="info")
        term.line(f"    {blurb}")
    term.line("")
    if dry_run:
        term.info("Dry run only. Nothing will be written to disk.")


def render_summary(
    term: Terminal,
    status_after: InstallStatus,
    *,
    dry_run: bool,
) -> None:
    """Print a final 'what's installed and what to do next' panel."""
    if not _ui_enabled(term):
        return
    home = Path.home()
    rows = [
        (
            "claude-hooks",
            _state(status_after.claude_hooks),
            str(home / ".claude" / "settings.json"),
        ),
        ("codex-shim", _state(status_after.codex_shim), str(home / ".local" / "bin" / "codex")),
        (
            "prompt-block",
            _state(status_after.prompt_block),
            str(home / ".loghop" / "loghop-prompt.md"),
        ),
    ]
    term.line("")
    term.table(
        rows,
        headers=("component", "state", "path"),
        title="install summary" + (" (dry-run)" if dry_run else ""),
    )
    if dry_run:
        return
    term.line("")
    term.line("next steps:", style="info")
    term.line("  • run `loghop doctor`")
    term.line("  • resume work with `loghop run`")
    term.line('  • optional: set a default goal with `loghop goal "your goal"`')
    term.line("  • use `loghop install-*` only for manual repair or custom scope")


def render_explanation(term: Terminal, key: str) -> None:
    """Optional per-prompt blurb so the user knows what each Y/n means."""
    if not _ui_enabled(term):
        return
    blurb = _COMPONENT_BLURBS.get(key)
    if blurb is None:
        return
    term.line("")
    term.line(f"  ↳ {blurb[1]}")


def _ui_enabled(term: Terminal) -> bool:
    if term.json_mode or term.quiet:
        return False
    stream = term.input_stream
    isatty = getattr(stream, "isatty", None)
    if not callable(isatty):
        return False
    try:
        return bool(isatty())
    except OSError:
        return False


def _state(installed: bool) -> str:
    return "installed" if installed else "not installed"
