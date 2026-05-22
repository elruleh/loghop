from pathlib import Path

from loghop.install._config import _backup, load_tracked_project_roots
from loghop.install._types import (
    _LOGHOP_PROMPT_BODY,
    _LOGHOP_PROMPT_FILENAME,
    InstallReport,
)
from loghop.store._io import atomic_write_private_text, atomic_write_text, safe_read_text
from loghop.store._registry import global_dir, load_registry


def install_loghop_prompt(
    *,
    scope_user: bool = True,
    project_root: Path | None = None,
    targets: tuple[str, ...] = ("codex", "claude"),
    uninstall: bool = False,
    remove_prompt_file: bool | None = None,
    dry_run: bool = False,
) -> list[InstallReport]:
    """Write ~/.loghop/loghop-prompt.md and @-include it from AGENTS.md / CLAUDE.md.

    targets: which provider entry-files to touch ("codex" → AGENTS.md,
             "claude" → CLAUDE.md).
    scope_user: True ⇒ ~/.codex/AGENTS.md & ~/.claude/CLAUDE.md.
                False ⇒ <project_root>/AGENTS.md & <project_root>/CLAUDE.md.
    """
    reports: list[InstallReport] = []
    prompt_path = _prompt_path_for(scope_user, project_root)
    if prompt_path is None:
        return []
    include_line = _include_line_for(prompt_path, scope_user=scope_user)
    legacy_include_line = f"@{global_dir() / _LOGHOP_PROMPT_FILENAME}"
    obsolete_lines = (
        () if scope_user or include_line == legacy_include_line else (legacy_include_line,)
    )

    if uninstall:
        current_entries = {
            entry
            for target in targets
            if (entry := _entry_file_for(target, scope_user, project_root)) is not None
        }
        if remove_prompt_file is None:
            search_entries = None  # search all entries, not just project-scope ones
            remove_prompt_file = not _prompt_file_referenced(
                prompt_path,
                include_line,
                excluded_entries=current_entries,
                search_entries=search_entries,
            )
        for target in targets:
            entry = _entry_file_for(target, scope_user, project_root)
            if entry is None:
                continue
            reports.append(
                _remove_include_lines(
                    entry,
                    (include_line, *obsolete_lines),
                    dry_run=dry_run,
                )
            )
        if remove_prompt_file:
            reports.append(_remove_prompt_file(prompt_path, dry_run=dry_run))
        return reports

    reports.append(_write_prompt_file(prompt_path, dry_run=dry_run))
    for target in targets:
        entry = _entry_file_for(target, scope_user, project_root)
        if entry is None:
            continue
        reports.append(
            _ensure_include_line(
                entry,
                include_line,
                dry_run=dry_run,
                obsolete_lines=obsolete_lines,
            )
        )
    return reports


def loghop_prompt_installed(
    *,
    scope_user: bool = True,
    project_root: Path | None = None,
    targets: tuple[str, ...] = ("codex", "claude"),
) -> bool:
    """Return True if the prompt file exists and every targeted entry includes it."""
    installed_targets = set(
        loghop_prompt_installed_targets(scope_user=scope_user, project_root=project_root)
    )
    return all(target in installed_targets for target in targets)


def loghop_prompt_installed_targets(
    *,
    scope_user: bool = True,
    project_root: Path | None = None,
) -> tuple[str, ...]:
    """Return the targets whose entry file currently includes the shared prompt."""
    prompt_path = _prompt_path_for(scope_user, project_root)
    if prompt_path is None:
        return ()
    include_line = _include_line_for(prompt_path, scope_user=scope_user)
    legacy_prompt_path = global_dir() / _LOGHOP_PROMPT_FILENAME
    legacy_include_line = f"@{legacy_prompt_path}"
    installed: list[str] = []
    for target in ("codex", "claude"):
        entry = _entry_file_for(target, scope_user, project_root)
        if entry is None or not entry.exists():
            continue
        body = safe_read_text(entry)
        has_current = prompt_path.exists() and include_line in body
        has_legacy = not scope_user and legacy_prompt_path.exists() and legacy_include_line in body
        if has_current or has_legacy:
            installed.append(target)
    return tuple(installed)


def _prompt_file_referenced(
    prompt_path: Path,
    include_line: str,
    *,
    excluded_entries: set[Path] | None = None,
    search_entries: set[Path] | None = None,
) -> bool:
    if not prompt_path.exists():
        return False
    excluded = {path.expanduser().resolve() for path in (excluded_entries or set())}
    entries = list(search_entries) if search_entries is not None else _all_entry_files()
    for entry in entries:
        if not entry.exists():
            continue
        try:
            resolved = entry.expanduser().resolve()
        except OSError:
            resolved = entry.expanduser()
        if resolved in excluded:
            continue
        try:
            body = safe_read_text(entry)
        except OSError:
            continue
        if include_line in body:
            return True
    return False


def _all_entry_files() -> list[Path]:
    files: list[Path] = [
        Path.home() / ".codex" / "AGENTS.md",
        Path.home() / ".claude" / "CLAUDE.md",
    ]
    roots = {path.expanduser() for path in load_tracked_project_roots()}
    roots.update(
        Path(str(entry.path)).expanduser()
        for entry in load_registry()
        if getattr(entry, "path", "")
    )
    for root in roots:
        files.append(root / "AGENTS.md")
        files.append(root / "CLAUDE.md")
    return files


def _entry_file_for(target: str, scope_user: bool, project_root: Path | None) -> Path | None:
    if target == "codex":
        if scope_user:
            return Path.home() / ".codex" / "AGENTS.md"
        if project_root is None:
            return None
        return project_root / "AGENTS.md"
    if target == "claude":
        if scope_user:
            return Path.home() / ".claude" / "CLAUDE.md"
        if project_root is None:
            return None
        return project_root / "CLAUDE.md"
    return None


def _prompt_path_for(scope_user: bool, project_root: Path | None) -> Path | None:
    if scope_user:
        return global_dir() / _LOGHOP_PROMPT_FILENAME
    if project_root is None:
        return None
    return project_root / ".loghop" / _LOGHOP_PROMPT_FILENAME


def _include_line_for(prompt_path: Path, *, scope_user: bool) -> str:
    if scope_user:
        return f"@{prompt_path}"
    return f"@.loghop/{prompt_path.name}"


def _write_prompt_file(path: Path, *, dry_run: bool) -> InstallReport:
    if path.exists() and safe_read_text(path) == _LOGHOP_PROMPT_BODY:
        return InstallReport(path, "unchanged")
    is_new = not path.exists()
    if dry_run:
        return InstallReport(path, "would-create" if is_new else "would-update")
    _backup(path)
    atomic_write_private_text(path, _LOGHOP_PROMPT_BODY)
    return InstallReport(path, "created" if is_new else "updated")


def _ensure_include_line(
    entry_path: Path,
    include_line: str,
    *,
    dry_run: bool,
    obsolete_lines: tuple[str, ...] = (),
) -> InstallReport:
    if entry_path.exists():
        body = safe_read_text(entry_path)
        filtered_lines = [
            line for line in body.splitlines() if line.strip() not in set(obsolete_lines)
        ]
        filtered_body = "\n".join(filtered_lines).rstrip() + ("\n" if filtered_lines else "")
        if include_line in filtered_body and filtered_body == body:
            return InstallReport(entry_path, "unchanged")
        is_new = False
        if include_line in filtered_body:
            new_body = filtered_body
        else:
            new_body = filtered_body.rstrip() + f"\n{include_line}\n"
    else:
        is_new = True
        new_body = include_line + "\n"
    if dry_run:
        return InstallReport(entry_path, "would-create" if is_new else "would-update")
    if not is_new:
        _backup(entry_path)
    atomic_write_text(entry_path, new_body)
    return InstallReport(entry_path, "created" if is_new else "updated")


def _remove_include_line(entry_path: Path, include_line: str, *, dry_run: bool) -> InstallReport:
    return _remove_include_lines(entry_path, (include_line,), dry_run=dry_run)


def _remove_include_lines(
    entry_path: Path,
    include_lines: tuple[str, ...],
    *,
    dry_run: bool,
) -> InstallReport:
    if not entry_path.exists():
        return InstallReport(entry_path, "unchanged", "file absent")
    body = safe_read_text(entry_path)
    targets = {line.strip() for line in include_lines}
    if not any(line in body for line in targets):
        return InstallReport(entry_path, "unchanged", "include line not present")
    if dry_run:
        return InstallReport(entry_path, "would-remove")
    _backup(entry_path)
    new_lines = [line for line in body.splitlines() if line.strip() not in targets]
    new_body = "\n".join(new_lines).rstrip() + ("\n" if new_lines else "")
    atomic_write_text(entry_path, new_body)
    return InstallReport(entry_path, "updated")


def _remove_prompt_file(path: Path, *, dry_run: bool) -> InstallReport:
    if not path.exists():
        return InstallReport(path, "unchanged", "file absent")
    if dry_run:
        return InstallReport(path, "would-remove")
    _backup(path)
    path.unlink()
    return InstallReport(path, "removed")
