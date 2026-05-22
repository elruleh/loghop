"""Idempotent migrations between installed loghop versions.

A migration is an action that brings an existing install up to date with the
running version. Since every installer is already idempotent (writes only on
content drift), the safe default for any drift is to re-apply the components
that are *currently installed* — that's enough to pick up format changes in
hook entries, shim bodies, or the prompt body.

Future versions can register concrete migrations here (e.g. removing a
deprecated hook entry) — the framework guarantees they run exactly once per
version transition.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from loghop import __version__
from loghop.install._config import (
    _backup,
    global_config_path,
    load_codex_shim_prefix,
    load_installed_version,
    load_tracked_project_roots,
    save_init_install_choices,
)
from loghop.install._hooks import claude_hooks_installed, install_claude_hooks
from loghop.install._prompt import (
    install_loghop_prompt,
    loghop_prompt_installed,
    loghop_prompt_installed_targets,
)
from loghop.install._shim import codex_shim_installed, install_codex_shim
from loghop.install._types import InstallReport


@dataclass(frozen=True)
class _MigrationOutcome:
    """Result of running migrations between two versions."""

    from_version: str | None
    to_version: str
    reports: list[InstallReport]

    @property
    def ran(self) -> bool:
        return self.from_version != self.to_version


def detect_drift() -> str | None:
    """Return the previously persisted version if it differs from running, else None."""
    saved = load_installed_version()
    if saved is None:
        return None
    if saved == __version__:
        return None
    return saved


def run_migrations(
    *,
    on_step: Callable[[str], None] | None = None,
) -> _MigrationOutcome:
    """Re-apply every currently installed component and stamp the new version.

    Idempotent: components that are already up-to-date emit `unchanged` reports.
    Components that aren't installed at all are left alone — the user opted out
    so reinstalling silently would surprise them.
    """
    from_version = load_installed_version()
    reports: list[InstallReport] = []

    def _step(label: str) -> None:
        if on_step is not None:
            on_step(label)

    reports.extend(_migration_backups())

    if claude_hooks_installed():
        _step("claude-hooks")
        reports.extend(install_claude_hooks())
    shim_prefix = load_codex_shim_prefix()
    if codex_shim_installed(prefix=shim_prefix):
        _step("codex-shim")
        reports.append(install_codex_shim(prefix=shim_prefix, binary="codex"))
    user_prompt_targets = loghop_prompt_installed_targets()
    if loghop_prompt_installed() or user_prompt_targets:
        _step("prompt-block")
        reports.extend(install_loghop_prompt(targets=user_prompt_targets or ("codex", "claude")))

    for project_root in load_tracked_project_roots():
        if claude_hooks_installed(scope_user=False, project_root=project_root):
            _step(f"claude-hooks:{project_root}")
            reports.extend(install_claude_hooks(scope_user=False, project_root=project_root))
        prompt_targets = loghop_prompt_installed_targets(
            scope_user=False, project_root=project_root
        )
        if prompt_targets:
            _step(f"prompt-block:{project_root}")
            reports.extend(
                install_loghop_prompt(
                    scope_user=False,
                    project_root=project_root,
                    targets=prompt_targets,
                )
            )

    if any(report.action == "error" for report in reports):
        return _MigrationOutcome(
            from_version=from_version,
            to_version=__version__,
            reports=reports,
        )

    # Stamp the new version even when nothing was reinstalled — the absence of
    # drift next time is itself a signal.
    from loghop.install._config import load_init_install_choices

    if not any(report.action == "error" for report in reports):
        saved = load_init_install_choices()
        if saved is not None:
            save_init_install_choices(saved)

    return _MigrationOutcome(
        from_version=from_version,
        to_version=__version__,
        reports=reports,
    )


def _migration_backups() -> list[InstallReport]:
    reports: list[InstallReport] = []
    paths: list[Path] = [global_config_path()]
    paths.append(Path.home() / ".claude" / "settings.json")
    paths.append(Path.home() / ".loghop" / "loghop-prompt.md")
    shim_prefix = load_codex_shim_prefix()
    if shim_prefix is not None:
        paths.append(shim_prefix / "codex")
    else:
        paths.append(Path.home() / ".local" / "bin" / "codex")
    for project_root in load_tracked_project_roots():
        paths.append(project_root / ".claude" / "settings.json")
        paths.append(project_root / ".loghop" / "loghop-prompt.md")
        paths.append(project_root / "AGENTS.md")
        paths.append(project_root / "CLAUDE.md")
    seen: set[str] = set()
    for path in paths:
        key = str(path.expanduser())
        if key in seen:
            continue
        seen.add(key)
        backup = _backup(path.expanduser())
        if backup is not None:
            reports.append(InstallReport(backup, "backup", f"from {path.expanduser()}"))
    return reports
