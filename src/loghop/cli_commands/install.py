import argparse
from pathlib import Path

from loghop.install import (
    InstallReport,
    install_aliases,
    install_claude_hooks,
    install_codex_shim,
    install_loghop_prompt,
)
from loghop.install._config import (
    save_codex_shim_prefix,
    track_project_root,
    untrack_project_root,
)
from loghop.install._hooks import claude_hooks_installed
from loghop.install._prompt import loghop_prompt_installed_targets
from loghop.store import find_project_root
from loghop.terminal import Terminal


def handle_install_prompt(args: argparse.Namespace, term: Terminal) -> int:
    targets = _resolve_prompt_targets(args)
    scope_user = args.scope != "project"
    project_root = find_project_root(Path.cwd()) if not scope_user else None
    if not scope_user and project_root is None:
        term.error("`--scope project` requires running inside a loghop repo")
        return 2
    reports = install_loghop_prompt(
        scope_user=scope_user,
        project_root=project_root,
        targets=targets,
        uninstall=bool(args.uninstall),
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    rc = _emit_reports(reports, term)
    _sync_project_scope_tracking(
        scope_user=scope_user,
        project_root=project_root,
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    return rc


def handle_install_hooks(args: argparse.Namespace, term: Terminal) -> int:
    scope_user = args.scope != "project"
    project_root = find_project_root(Path.cwd()) if not scope_user else None
    if not scope_user and project_root is None:
        term.error("`--scope project` requires running inside a loghop repo")
        return 2
    reports = install_claude_hooks(
        scope_user=scope_user,
        project_root=project_root,
        uninstall=bool(args.uninstall),
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    rc = _emit_reports(reports, term)
    _sync_project_scope_tracking(
        scope_user=scope_user,
        project_root=project_root,
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    return rc


def handle_install_shims(args: argparse.Namespace, term: Terminal) -> int:
    prefix = Path(args.prefix).expanduser() if args.prefix else None
    report = install_codex_shim(
        prefix=prefix,
        binary="codex",
        uninstall=bool(args.uninstall),
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    rc = _emit_reports([report], term)
    if not bool(getattr(args, "dry_run", False)) and report.action != "error":
        if bool(args.uninstall):
            save_codex_shim_prefix(None)
        else:
            save_codex_shim_prefix(prefix or (Path.home() / ".local" / "bin"))
    return rc


def _resolve_prompt_targets(args: argparse.Namespace) -> tuple[str, ...]:
    out: list[str] = []
    if args.codex:
        out.append("codex")
    if args.claude:
        out.append("claude")
    if not out:
        out = ["codex", "claude"]
    return tuple(out)


def _emit_reports(reports: list[InstallReport], term: Terminal) -> int:
    if not reports:
        term.info("Nothing to do")
        term.capture_result({"reports": []})
        return 0
    payload = []
    exit_code = 0
    for r in reports:
        verb = {
            "created": "Created",
            "updated": "Updated",
            "removed": "Removed",
            "skipped": "Skipped",
            "error": "Error",
            "would-create": "Would create",
            "would-update": "Would update",
            "would-remove": "Would remove",
        }.get(r.action, r.action.replace("-", " ").capitalize())
        msg = f"{verb}: {r.path}"
        if r.detail:
            msg = f"{msg} - {r.detail}"
        if r.action in ("created", "updated", "removed"):
            term.success(msg)
        elif r.action.startswith("would-"):
            term.info(f"[dry-run] {msg}")
        elif r.action == "skipped":
            term.warn(msg)
        elif r.action == "error":
            term.error(msg)
            exit_code = 1
        else:
            term.info(msg)
        payload.append({"path": str(r.path), "action": r.action, "detail": r.detail})
    term.capture_result({"reports": payload})
    return exit_code


def _sync_project_scope_tracking(
    *,
    scope_user: bool,
    project_root: Path | None,
    dry_run: bool,
) -> None:
    if scope_user or project_root is None or dry_run:
        return
    if claude_hooks_installed(
        scope_user=False, project_root=project_root
    ) or loghop_prompt_installed_targets(
        scope_user=False,
        project_root=project_root,
    ):
        track_project_root(project_root)
        return
    untrack_project_root(project_root)


def handle_install_aliases(args: argparse.Namespace, term: Terminal) -> int:
    reports = install_aliases(
        uninstall=bool(args.uninstall),
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    return _emit_reports(reports, term)


def handle_uninstall_aliases(args: argparse.Namespace, term: Terminal) -> int:
    reports = install_aliases(
        uninstall=True,
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    return _emit_reports(reports, term)
