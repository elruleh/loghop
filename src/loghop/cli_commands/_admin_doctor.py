import argparse
import shutil
from collections.abc import Callable
from pathlib import Path

from loghop.cli_commands.install import _emit_reports
from loghop.install import (
    claude_hooks_installed,
    codex_shim_installed,
    install_claude_hooks,
    install_codex_shim,
    install_loghop_prompt,
    load_init_install_choices,
    load_installed_version,
    loghop_prompt_installed,
    loghop_prompt_installed_targets,
    run_migrations,
)
from loghop.install._config import load_codex_shim_prefix
from loghop.install._shim import (
    _detect_real_binary,
    _prefix_in_path,
    _prefix_is_first_in_path,
)
from loghop.logging import get_logger
from loghop.terminal import Terminal

_LOGGER = get_logger()


def handle_doctor(args: argparse.Namespace, term: Terminal) -> int:
    fix = bool(getattr(args, "fix", False))
    components, problems = _collect_doctor_state()

    if fix:
        applied = _apply_doctor_fixes(components, term)
        if applied:
            components, problems = _collect_doctor_state()

    rows: list[tuple[str, str, str]] = [
        (str(c["name"]), str(c["state"]), str(c["detail"])) for c in components
    ]
    term.table(rows, headers=("component", "state", "detail"), title="loghop doctor")
    term.capture_result(
        {
            "ok": not problems,
            "problems": problems,
            "components": [{k: v for k, v in c.items() if k != "fix"} for c in components],
        }
    )

    if problems:
        for p in problems:
            term.error(p)
        if not fix:
            term.info("Run `loghop doctor --fix` to repair detected issues")
        return 1
    term.success("Install looks healthy")
    return 0


def _collect_doctor_state() -> tuple[list[dict[str, object]], list[str]]:
    from loghop import __version__

    components: list[dict[str, object]] = []
    problems: list[str] = []
    saved_choices = load_init_install_choices()

    def _opted_out(key: str) -> bool:
        if saved_choices is None:
            return False
        return getattr(saved_choices, key) is False

    _check_claude_hooks(components, problems, _opted_out)
    _check_codex_shim(components, problems, _opted_out)
    _check_prompt_block(components, problems, _opted_out)
    _check_version(components, problems, __version__)
    _check_cli_path(components, problems)
    return components, problems


def _check_component(
    components: list[dict[str, object]],
    problems: list[str],
    *,
    name: str,
    state: str,
    detail: str,
    fix: str | None = None,
    problem: str | None = None,
) -> None:
    components.append({"name": name, "state": state, "detail": detail, "fix": fix})
    if problem:
        problems.append(problem)


def _check_claude_hooks(
    components: list[dict[str, object]],
    problems: list[str],
    opted_out: Callable[[str], bool],
) -> None:
    if claude_hooks_installed():
        _check_component(
            components,
            problems,
            name="claude-hooks",
            state="ok",
            detail=str(Path.home() / ".claude" / "settings.json"),
        )
    elif opted_out("install_claude_hooks"):
        _check_component(
            components,
            problems,
            name="claude-hooks",
            state="skipped",
            detail="opted out in ~/.loghop/config.toml",
        )
    else:
        _check_component(
            components,
            problems,
            name="claude-hooks",
            state="missing",
            detail="run `loghop install-hooks --claude`",
            fix="claude-hooks",
            problem="claude session hooks are not installed",
        )


def _check_codex_shim(
    components: list[dict[str, object]],
    problems: list[str],
    opted_out: Callable[[str], bool],
) -> None:
    shim_prefix = load_codex_shim_prefix() or (Path.home() / ".local" / "bin")
    shim = shim_prefix / "codex"
    if codex_shim_installed(prefix=shim_prefix):
        _check_shim_installed(components, problems, shim)
    elif opted_out("install_codex_shim"):
        _check_component(
            components,
            problems,
            name="codex-shim",
            state="skipped",
            detail="opted out in ~/.loghop/config.toml",
        )
    else:
        _check_component(
            components,
            problems,
            name="codex-shim",
            state="missing",
            detail="run `loghop install-shims --codex`",
            fix="codex-shim",
            problem="codex PATH shim is not installed",
        )


def _check_shim_installed(
    components: list[dict[str, object]], problems: list[str], shim: Path
) -> None:
    warnings: list[str] = []
    state = "ok"
    if not _prefix_in_path(shim.parent):
        warnings.append(f"{shim.parent} not on PATH")
        state = "warn"
    elif not _prefix_is_first_in_path(shim.parent):
        warnings.append(f"{shim.parent} not first in PATH")
        state = "warn"
    real = _detect_real_binary("codex", exclude_dir=shim.parent)
    if real is None:
        warnings.append("real codex not resolvable")
        problems.append("real codex binary not found outside the shim directory")
        state = "warn"
    detail = str(shim) + ("  [warn: " + "; ".join(warnings) + "]" if warnings else "")
    components.append({"name": "codex-shim", "state": state, "detail": detail, "fix": None})


def _check_prompt_block(
    components: list[dict[str, object]],
    problems: list[str],
    opted_out: Callable[[str], bool],
) -> None:
    installed_targets = loghop_prompt_installed_targets()
    if loghop_prompt_installed():
        installed_targets = installed_targets or ("codex", "claude")
        _check_component(
            components,
            problems,
            name="prompt-block",
            state="ok",
            detail=(
                f"{Path.home() / '.loghop' / 'loghop-prompt.md'}"
                f"  [targets: {', '.join(installed_targets)}]"
            ),
        )
    elif installed_targets:
        _check_component(
            components,
            problems,
            name="prompt-block",
            state="ok",
            detail=(
                f"{Path.home() / '.loghop' / 'loghop-prompt.md'}"
                f"  [targets: {', '.join(installed_targets)}]"
            ),
        )
    elif opted_out("install_prompt_block"):
        _check_component(
            components,
            problems,
            name="prompt-block",
            state="skipped",
            detail="opted out in ~/.loghop/config.toml",
        )
    else:
        _check_component(
            components,
            problems,
            name="prompt-block",
            state="missing",
            detail="run `loghop install-prompt`",
            fix="prompt-block",
            problem="loghop prompt block is not installed",
        )


def _check_version(
    components: list[dict[str, object]], problems: list[str], current_version: str
) -> None:
    saved_version = load_installed_version()
    if saved_version and saved_version != current_version:
        _check_component(
            components,
            problems,
            name="version",
            state="drift",
            detail=f"installed={saved_version}, running={current_version}"
            " - re-run `loghop init` or `loghop doctor --fix`",
            fix="version",
            problem=f"version drift: installed={saved_version} vs running={current_version}",
        )
    else:
        _check_component(
            components,
            problems,
            name="version",
            state="ok",
            detail=saved_version or current_version,
        )


def _check_cli_path(components: list[dict[str, object]], problems: list[str]) -> None:
    cli_path = shutil.which("loghop")
    if cli_path:
        _check_component(components, problems, name="loghop-cli", state="ok", detail=cli_path)
    else:
        _check_component(
            components,
            problems,
            name="loghop-cli",
            state="missing",
            detail="`loghop` is not on PATH",
            problem="`loghop` is not on PATH; hooks and shims will fail when invoked",
        )


def _apply_doctor_fixes(components: list[dict[str, object]], term: Terminal) -> bool:
    applied = False
    shim_prefix = load_codex_shim_prefix()
    for c in components:
        kind = c.get("fix")
        if not kind:
            continue
        applied = True
        term.info(f"Fixing {c['name']}...")
        try:
            if kind == "claude-hooks":
                _emit_reports(install_claude_hooks(), term)
            elif kind == "codex-shim":
                _emit_reports([install_codex_shim(prefix=shim_prefix, binary="codex")], term)
            elif kind == "prompt-block":
                _emit_reports(install_loghop_prompt(), term)
            elif kind == "version":
                outcome = run_migrations(on_step=lambda s: term.info(f"  migrating {s}"))
                if outcome.reports:
                    _emit_reports(outcome.reports, term)
                term.success(f"Migrated {outcome.from_version} -> {outcome.to_version}")
        except Exception as exc:
            _LOGGER.exception(
                "doctor fix failed",
                extra={
                    "component": "doctor",
                    "fix": str(kind),
                    "name": str(c.get("name", "")),
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            term.error(f"Fix failed for {c['name']}: {exc}")
    return applied
