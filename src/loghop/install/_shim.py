import os
import shlex
import shutil
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

from loghop.install._types import InstallReport


def install_codex_shim(
    *,
    prefix: Path | None = None,
    binary: str = "codex",
    uninstall: bool = False,
    dry_run: bool = False,
) -> InstallReport:
    """Create a PATH shim that delegates to `loghop wrap <binary>`."""
    explicit_prefix = prefix is not None
    is_windows = sys.platform.startswith("win") or os.name == "nt"
    target_dir = prefix or (Path.home() / ".local" / "bin")
    binary_ext = ".cmd" if is_windows else ""
    shim = target_dir / f"{binary}{binary_ext}"

    if uninstall:
        return _handle_uninstall(shim, dry_run)

    real = _detect_real_binary(binary, exclude_dir=target_dir)
    if real is None:
        return InstallReport(shim, "skipped", f"`{binary}` not found in PATH outside {target_dir}")

    body = _shim_body(binary, real)
    if shim.exists() and shim.read_text(encoding="utf-8") == body:
        return InstallReport(shim, "unchanged")
    if shim.exists() and not _is_loghop_shim(shim):
        return InstallReport(shim, "skipped", f"refusing to overwrite non-loghop file at {shim}")

    detail = _check_shim_preconditions(target_dir, explicit_prefix, dry_run, binary)
    if isinstance(detail, InstallReport):
        return detail

    is_new = not shim.exists()
    if dry_run:
        return InstallReport(shim, "would-create" if is_new else "would-update", detail)
    target_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_executable(shim, body)
    return InstallReport(shim, "created" if is_new else "updated", detail)


def _handle_uninstall(shim: Path, dry_run: bool) -> InstallReport:
    if not shim.exists():
        return InstallReport(shim, "unchanged", "no shim present")
    if not _is_loghop_shim(shim):
        return InstallReport(shim, "skipped", "file exists but is not a loghop shim")
    if dry_run:
        return InstallReport(shim, "would-remove")
    shim.unlink()
    return InstallReport(shim, "removed")


def _check_shim_preconditions(
    target_dir: Path, explicit_prefix: bool, dry_run: bool, binary: str
) -> str | InstallReport:
    detail_parts: list[str] = []
    if not _prefix_in_path(target_dir):
        if not explicit_prefix and not dry_run:
            return InstallReport(
                target_dir / binary,
                "error",
                f"{target_dir} is not on PATH; add it to PATH before installing "
                "the shim, or pass --prefix to a directory on PATH",
            )
        detail_parts.append(f"warning: {target_dir} is not on PATH; shim will not be invoked")
    elif not _prefix_is_first_in_path(target_dir):
        detail_parts.append(
            f"warning: {target_dir} is not first in PATH; the real `{binary}` "
            "may still be invoked first"
        )
    sibling_wrappers = _detect_sibling_wrappers(binary, target_dir)
    if sibling_wrappers:
        names = ", ".join(p.name for p in sibling_wrappers)
        detail_parts.append(
            f"warning: sibling wrapper(s) found in {target_dir} ({names}); "
            f"loghop's shim may double-wrap `{binary}`. Verify your tooling "
            "tolerates the chain."
        )
    return "; ".join(detail_parts)


def codex_shim_installed(
    *,
    prefix: Path | None = None,
    binary: str = "codex",
) -> bool:
    """Return True if a loghop-managed shim exists for ``binary`` under prefix."""
    is_windows = sys.platform.startswith("win") or os.name == "nt"
    target_dir = prefix or (Path.home() / ".local" / "bin")
    binary_ext = ".cmd" if is_windows else ""
    shim = target_dir / f"{binary}{binary_ext}"
    return shim.exists() and _is_loghop_shim(shim)


def detect_real_binary(name: str, *, exclude_dir: Path) -> str | None:
    return _detect_real_binary(name, exclude_dir=exclude_dir)


def _detect_real_binary(name: str, *, exclude_dir: Path) -> str | None:
    parts = (os.environ.get("PATH") or "").split(os.pathsep)
    cleaned = os.pathsep.join(p for p in parts if Path(p).resolve() != exclude_dir.resolve())
    return shutil.which(name, path=cleaned)


def _detect_sibling_wrappers(binary: str, target_dir: Path) -> list[Path]:
    """Return sibling files that look like third-party wrappers around ``binary``.

    Many tools install companion wrappers next to the binary they intercept
    (``codex-rtk``, ``codex.real``, ``codex-original``, ``rtk-codex``, …).
    Stacking loghop's shim on top creates a double-wrap chain that may
    surprise the user. We only scan ``target_dir`` itself — arbitrary
    wrappers elsewhere on PATH are out of scope, and the loghop shim itself
    (``target_dir/binary``) is excluded.
    """
    if not target_dir.is_dir():
        return []
    matches: list[Path] = []
    try:
        entries = list(target_dir.iterdir())
    except OSError:
        return []
    for entry in entries:
        name = entry.name
        if name == binary or not entry.is_file():
            continue
        # Match common wrapper-naming patterns: <binary>-*, *-<binary>,
        # <binary>.<suffix>, or <prefix>.<binary>. Keep it heuristic so we
        # don't depend on any specific tool.
        if (
            name.startswith(f"{binary}-")
            or name.endswith(f"-{binary}")
            or name.startswith(f"{binary}.")
            or name.endswith(f".{binary}")
        ):
            matches.append(entry)
    return matches


def _shim_body(binary: str, real_path: str) -> str:
    is_windows = sys.platform.startswith("win") or os.name == "nt"
    if is_windows:
        return (
            "@echo off\n"
            "rem Managed by loghop install-shims; do not edit manually.\n"
            f"set LOGHOP_REAL_{binary.upper()}={real_path}\n"
            f"loghop wrap {binary} %*\n"
        )
    return (
        "#!/bin/sh\n"
        "# Managed by loghop install-shims; do not edit manually.\n"
        f"export LOGHOP_REAL_{binary.upper()}={shlex.quote(real_path)}\n"
        f'exec loghop wrap {shlex.quote(binary)} "$@"\n'
    )


def _is_loghop_shim(path: Path) -> bool:
    try:
        head = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "Managed by loghop install-shims" in head


def _atomic_write_executable(path: Path, body: str) -> None:
    is_windows = sys.platform.startswith("win") or os.name == "nt"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        if not is_windows:
            os.chmod(tmp, 0o755)  # nosec B103 - PATH shim must be executable
        os.replace(tmp, path)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def _path_dirs() -> list[Path]:
    return [Path(p) for p in (os.environ.get("PATH") or "").split(os.pathsep) if p]


def _prefix_in_path(prefix: Path) -> bool:
    try:
        resolved = prefix.resolve()
    except OSError:
        return False
    for p in _path_dirs():
        try:
            if p.resolve() == resolved:
                return True
        except OSError:
            continue
    return False


def _prefix_is_first_in_path(prefix: Path) -> bool:
    parts = _path_dirs()
    if not parts:
        return False
    first = parts[0]
    try:
        return first.resolve() == prefix.resolve()
    except OSError:
        return False
