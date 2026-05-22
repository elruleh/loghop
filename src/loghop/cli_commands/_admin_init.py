import argparse
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from loghop.cli_commands._helpers import LOGGER, require_git_repository_root
from loghop.cli_commands._install_ui import (
    render_explanation,
    render_summary,
    render_welcome,
)
from loghop.cli_commands.install import _emit_reports
from loghop.install import (
    InitInstallChoices,
    InstallReport,
    InstallStatus,
    detect_drift,
    install_claude_hooks,
    install_codex_shim,
    install_loghop_prompt,
    is_installed,
    load_init_install_choices,
    run_migrations,
    save_init_install_choices,
)
from loghop.logging import configure_project_logging
from loghop.providers import detect_all
from loghop.store import init_project
from loghop.terminal import Terminal


def handle_init(args: argparse.Namespace, term: Terminal) -> int:
    root = require_git_repository_root()
    force = bool(getattr(args, "force_reinstall", False))
    dry_run = bool(getattr(args, "dry_run", False))
    already = (root / ".loghop").is_dir()
    if already:
        from loghop.store._constants import project_paths

        paths = project_paths(root)
        configure_project_logging(root)
        LOGGER.info(
            "init on existing project",
            extra={"component": "init", "path": str(root)},
        )
        term.section(
            "loghop init",
            (
                ("root", str(paths.root)),
                ("config", str(paths.config.relative_to(paths.root))),
                ("memory", paths.memory.name),
            ),
        )
        if force or dry_run:
            term.info("Project already initialized. Skipping store setup and re-running installs.")
        else:
            term.info("Project already initialized. Checking install state.")
    else:
        from loghop.store._constants import project_paths

        paths = project_paths(root)
        term.section(
            "loghop init",
            (
                ("root", str(paths.root)),
                ("config", str(paths.config.relative_to(paths.root))),
                ("memory", paths.memory.name),
            ),
        )
        if dry_run:
            term.info("[dry-run] Would initialize project store and memory files")
        else:
            paths = init_project(root)
            configure_project_logging(root)
            LOGGER.info("initialized project", extra={"component": "init", "path": str(root)})
            term.success("Initialized project")
    detections = detect_all()
    installed = sorted(name for name, detection in detections.items() if detection.installed)
    if installed:
        term.info(f"Providers on PATH: {', '.join(installed)}")
    else:
        term.warn("No supported providers found on PATH")
    rc = _run_init_install_steps(args, term)
    term.info('Next: run `loghop goal "your goal"` to set a project goal')
    term.info("Review `.gitignore` before commit.")
    term.capture_result(
        {
            "root": str(paths.root),
            "config": str(paths.config.relative_to(paths.root)),
            "memory": paths.memory.name,
        }
    )
    return rc


def handle_install(args: argparse.Namespace, term: Terminal) -> int:
    return _run_init_install_steps(args, term)


def _run_init_install_steps(args: argparse.Namespace, term: Terminal) -> int:
    dry_run = bool(getattr(args, "dry_run", False))
    force = bool(getattr(args, "force_reinstall", False))
    status = is_installed()
    if status.all and not force and not dry_run:
        term.info(
            "Install already looks complete. Re-run with --force-reinstall to apply again, or --dry-run to preview."
        )
        return 0

    drift = detect_drift()
    if drift and not dry_run:
        from loghop import __version__

        term.info(f"Version drift detected ({drift} → {__version__}). Running migrations...")
        outcome = run_migrations(on_step=lambda s: term.info(f"  migrating {s}"))
        if outcome.reports:
            _emit_reports(outcome.reports, term)

    render_welcome(term, status, dry_run=dry_run)

    choices, persist_choices = _resolve_init_install_choices(args, term, status, force=force)
    steps = _build_install_steps(choices, dry_run)
    all_reports, failed = _execute_steps(steps, dry_run, term)
    if failed:
        return 1

    if all_reports:
        _emit_reports(all_reports, term)

    if not dry_run:
        if persist_choices:
            save_init_install_choices(choices)
    else:
        term.info("[dry-run] No changes written. Choices not saved.")

    render_summary(term, is_installed(), dry_run=dry_run)
    return 0


def _build_install_steps(
    choices: InitInstallChoices, dry_run: bool
) -> list[tuple[str, Callable[[], list[InstallReport]]]]:
    steps: list[tuple[str, Callable[[], list[InstallReport]]]] = []
    if choices.install_claude_hooks:
        steps.append(("claude-hooks", lambda: install_claude_hooks(dry_run=dry_run)))
    if choices.install_codex_shim:
        steps.append(("codex-shim", lambda: [install_codex_shim(binary="codex", dry_run=dry_run)]))
    if choices.install_prompt_block:
        steps.append(
            (
                "prompt",
                lambda: install_loghop_prompt(targets=("codex", "claude"), dry_run=dry_run),
            )
        )
    return steps


def _execute_steps(
    steps: list[tuple[str, Callable[[], list[InstallReport]]]],
    dry_run: bool,
    term: Terminal,
) -> tuple[list[InstallReport], bool]:
    all_reports: list[InstallReport] = []
    rollback_ops: list[_RollbackOp] = []
    try:
        for name, step in steps:
            reports = step()
            all_reports.extend(reports)
            if not dry_run:
                rollback_ops.extend(_collect_rollback_ops(reports))
            for r in reports:
                if r.action == "error":
                    raise _InstallStepError(name, r.detail or "precondition failed")
    except _InstallStepError as exc:
        if not dry_run:
            _rollback(rollback_ops, term)
        LOGGER.error(
            "install step failed",
            extra={"component": "install", "step": exc.step, "error": exc.message},
        )
        term.error(f"Install step `{exc.step}` failed: {exc.message}")
        if all_reports:
            _emit_reports(all_reports, term)
        return all_reports, True
    except Exception as exc:  # pragma: no cover - defensive  # noqa: BLE001
        if not dry_run:
            _rollback(rollback_ops, term)
        LOGGER.exception(
            "install aborted",
            extra={
                "component": "install",
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        term.error(f"Install aborted: {exc}")
        return all_reports, True
    return all_reports, False


class _InstallStepError(Exception):
    def __init__(self, step: str, message: str) -> None:
        super().__init__(f"{step}: {message}")
        self.step = step
        self.message = message


@dataclass(frozen=True)
class _RollbackOp:
    path: Path
    restore_from: Path | None = None
    remove_created: bool = False


def _collect_rollback_ops(reports: list[InstallReport]) -> list[_RollbackOp]:
    ops: list[_RollbackOp] = []
    for report in reports:
        if report.action not in {"created", "updated", "removed"}:
            continue
        bak = report.path.with_suffix(report.path.suffix + ".loghop.bak")
        if bak.exists():
            ops.append(_RollbackOp(path=report.path, restore_from=bak))
        elif report.action == "created":
            ops.append(_RollbackOp(path=report.path, remove_created=True))
    return ops


def _rollback(ops: list[_RollbackOp], term: Terminal) -> None:
    if not ops:
        return
    term.warn(f"Rolling back {len(ops)} change(s)")
    for op in reversed(ops):
        try:
            if op.restore_from is not None:
                shutil.copy2(op.restore_from, op.path)
                continue
            if op.remove_created and op.path.exists():
                op.path.unlink()
        except OSError as exc:
            term.error(f"Rollback failed for {op.path}: {exc}")


def _resolve_init_install_choices(
    args: argparse.Namespace,
    term: Terminal,
    status: InstallStatus,
    *,
    force: bool,
) -> tuple[InitInstallChoices, bool]:
    dry_run = bool(getattr(args, "dry_run", False))
    no_prompt = bool(getattr(args, "no_prompt", False))

    if dry_run:
        choices = InitInstallChoices(
            install_claude_hooks=not status.claude_hooks,
            install_codex_shim=not status.codex_shim,
            install_prompt_block=not status.prompt_block,
        )
        if not (
            choices.install_claude_hooks
            or choices.install_codex_shim
            or choices.install_prompt_block
        ):
            choices = InitInstallChoices(
                install_claude_hooks=True,
                install_codex_shim=True,
                install_prompt_block=True,
            )
        term.info("[dry-run] Previewing install plan for missing components")
        return choices, False

    if no_prompt:
        choices = InitInstallChoices(
            install_claude_hooks=False,
            install_codex_shim=False,
            install_prompt_block=False,
        )
        save_init_install_choices(choices)
        term.info("Skipped init prompts (--no-prompt). Saved No for optional installs.")
        return choices, True

    saved = load_init_install_choices()
    if saved is not None and not force:
        term.info("Using saved init choices from ~/.loghop/config.toml")
        return saved, False

    if not _can_prompt(term):
        choices = InitInstallChoices(
            install_claude_hooks=False,
            install_codex_shim=False,
            install_prompt_block=False,
        )
        term.info("stdin is not interactive. Skipping optional installs without saving choices.")
        return choices, False

    if status.any and not force:
        term.info("Partial install detected. Answering Yes only installs missing pieces.")

    render_explanation(term, "claude-hooks")
    install_claude = term.confirm("Install Claude session hooks?", default=not status.claude_hooks)
    render_explanation(term, "codex-shim")
    install_shim = term.confirm("Install Codex PATH shim?", default=not status.codex_shim)
    render_explanation(term, "prompt-block")
    install_prompt = term.confirm("Install loghop prompt block?", default=not status.prompt_block)
    return (
        InitInstallChoices(
            install_claude_hooks=install_claude,
            install_codex_shim=install_shim,
            install_prompt_block=install_prompt,
        ),
        True,
    )


def _can_prompt(term: Terminal) -> bool:
    if term.json_mode:
        return False
    stream = term.input_stream
    isatty = getattr(stream, "isatty", None)
    if not callable(isatty):
        return False
    try:
        return bool(isatty())
    except OSError:
        return False
