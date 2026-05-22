"""Self-installation helpers for hooks, shims, and AGENTS.md/CLAUDE.md prompts.

These functions are pure (no CLI / Terminal coupling) so they can be reused
from ``loghop install-*`` subcommands and from the ``loghop init`` orchestrator.
Every function is idempotent and produces a ``.bak`` of any file it rewrites.
Each installer accepts ``dry_run=True`` to compute reports without touching
disk; reports use the ``would-*`` action prefix in that mode.
"""

from pathlib import Path

from loghop.install._alias import install_aliases
from loghop.install._config import (
    global_config_path,
    load_codex_shim_prefix,
    load_init_install_choices,
    load_installed_version,
    load_tracked_project_roots,
    save_init_install_choices,
)
from loghop.install._hooks import claude_hooks_installed, install_claude_hooks
from loghop.install._migrations import detect_drift, run_migrations
from loghop.install._prompt import (
    install_loghop_prompt,
    loghop_prompt_installed,
    loghop_prompt_installed_targets,
)
from loghop.install._shim import codex_shim_installed, install_codex_shim
from loghop.install._types import (
    GLOBAL_CONFIG_FILENAME,
    INIT_INSTALL_KEYS,
    InitInstallChoices,
    InstallReport,
    InstallStatus,
)


def is_installed(
    *,
    scope_user: bool = True,
    project_root: Path | None = None,
    shim_prefix: Path | None = None,
) -> InstallStatus:
    """Inspect the filesystem for evidence of each install component."""
    effective_shim_prefix = shim_prefix or load_codex_shim_prefix()
    return InstallStatus(
        claude_hooks=claude_hooks_installed(scope_user=scope_user, project_root=project_root),
        codex_shim=codex_shim_installed(prefix=effective_shim_prefix, binary="codex"),
        prompt_block=loghop_prompt_installed(scope_user=scope_user, project_root=project_root),
    )


__all__ = [
    "GLOBAL_CONFIG_FILENAME",
    "INIT_INSTALL_KEYS",
    "InitInstallChoices",
    "InstallReport",
    "InstallStatus",
    "claude_hooks_installed",
    "codex_shim_installed",
    "detect_drift",
    "global_config_path",
    "install_aliases",
    "install_claude_hooks",
    "install_codex_shim",
    "install_loghop_prompt",
    "is_installed",
    "load_codex_shim_prefix",
    "load_init_install_choices",
    "load_installed_version",
    "load_tracked_project_roots",
    "loghop_prompt_installed",
    "loghop_prompt_installed_targets",
    "run_migrations",
    "save_init_install_choices",
]
