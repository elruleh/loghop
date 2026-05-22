import argparse
import shutil
from pathlib import Path

from loghop.cli_commands.install import _emit_reports
from loghop.install import (
    install_claude_hooks,
    install_codex_shim,
    install_loghop_prompt,
)
from loghop.install._config import (
    clear_tracked_project_roots,
    load_codex_shim_prefix,
    load_tracked_project_roots,
    save_codex_shim_prefix,
)
from loghop.store._registry import load_registry
from loghop.terminal import Terminal


def handle_uninstall(args: argparse.Namespace, term: Terminal) -> int:
    keep_config = bool(getattr(args, "keep_config", False))
    purge = bool(getattr(args, "purge", False))
    dry_run = bool(getattr(args, "dry_run", False))

    if (
        not getattr(args, "yes", False)
        and not dry_run
        and not term.confirm(
            "Remove loghop hooks, Codex shim, and prompt assets?"
            + (" This will also delete ~/.loghop (config, registry, history)." if purge else ""),
            default=False,
        )
    ):
        term.info("Aborted")
        return 0

    reports = []
    project_roots = {path.expanduser() for path in load_tracked_project_roots()}
    project_roots.update(
        Path(str(entry.path)).expanduser()
        for entry in load_registry()
        if getattr(entry, "path", "")
    )
    for root in project_roots:
        reports.extend(
            install_claude_hooks(
                scope_user=False,
                project_root=root,
                uninstall=True,
                dry_run=dry_run,
            )
        )
        reports.extend(
            install_loghop_prompt(
                scope_user=False,
                project_root=root,
                uninstall=True,
                remove_prompt_file=False,
                dry_run=dry_run,
            )
        )
    reports.extend(install_claude_hooks(uninstall=True, dry_run=dry_run))
    shim_prefix = load_codex_shim_prefix()
    seen_prefixes = {Path.home() / ".local" / "bin"}
    if shim_prefix is not None:
        seen_prefixes.add(shim_prefix)
    reports.extend(
        install_codex_shim(
            prefix=prefix,
            binary="codex",
            uninstall=True,
            dry_run=dry_run,
        )
        for prefix in sorted(seen_prefixes, key=str)
    )
    reports.extend(install_loghop_prompt(uninstall=True, dry_run=dry_run))
    rc = _emit_reports(reports, term)
    if rc != 0:
        return rc
    if not dry_run:
        save_codex_shim_prefix(None)
        clear_tracked_project_roots()

    if purge and not dry_run:
        global_dir = Path.home() / ".loghop"
        if global_dir.exists():
            shutil.rmtree(global_dir)
            term.success(f"Purged {global_dir}")
    elif not keep_config and not purge and not dry_run:
        from loghop.install import global_config_path

        cfg = global_config_path()
        if cfg.exists():
            cfg.unlink()
            term.info(f"Removed {cfg} (saved choices). Pass --keep-config to keep it.")

    return rc
