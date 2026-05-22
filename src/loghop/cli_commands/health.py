from __future__ import annotations

import argparse
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from loghop.gittools import GitRepo
from loghop.providers import detect_all
from loghop.store import find_project_root, project_paths
from loghop.terminal import Terminal

_Status = Literal["pass", "warn", "fail"]


@dataclass(frozen=True)
class HealthCheck:
    name: str
    status: _Status
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "message": self.message}


def handle_health(_args: argparse.Namespace, term: Terminal) -> int:
    root = find_project_root(Path.cwd())
    if root is None:
        checks = [
            HealthCheck(
                "project_initialized",
                "fail",
                "current directory is not inside an initialized loghop project",
            )
        ]
        _render(term, checks)
        term.capture_result({"healthy": False, "checks": [check.to_dict() for check in checks]})
        return 20

    checks = collect_health(root)
    healthy = all(check.status != "fail" for check in checks)
    _render(term, checks)
    term.capture_result({"healthy": healthy, "checks": [check.to_dict() for check in checks]})
    return 0 if healthy else 1


def collect_health(root: Path) -> list[HealthCheck]:
    paths = project_paths(root)
    checks: list[HealthCheck] = [
        HealthCheck("project_initialized", "pass", f"initialized at {root}"),
        _git_check(root),
        _directory_check(paths.dot, "loghop_directory"),
        _file_check(paths.config, "config_file"),
        _timeline_check(paths.timeline),
        _providers_check(),
    ]
    return checks


def _git_check(root: Path) -> HealthCheck:
    repo = GitRepo.from_cwd(root)
    if repo is None:
        return HealthCheck("git_repository", "fail", "git repository is not accessible")
    return HealthCheck("git_repository", "pass", "git repository is accessible")


def _directory_check(path: Path, name: str) -> HealthCheck:
    if path.is_symlink():
        return HealthCheck(name, "fail", f"refusing symlinked directory: {path}")
    if not path.is_dir():
        return HealthCheck(name, "fail", f"missing directory: {path}")
    permission_status = _private_mode_status(path)
    if permission_status:
        return HealthCheck(name, "warn", permission_status)
    return HealthCheck(name, "pass", f"directory exists: {path}")


def _file_check(path: Path, name: str) -> HealthCheck:
    if path.is_symlink():
        return HealthCheck(name, "fail", f"refusing symlinked file: {path}")
    if not path.exists():
        return HealthCheck(name, "fail", f"missing file: {path}")
    if not path.is_file():
        return HealthCheck(name, "fail", f"not a regular file: {path}")
    permission_status = _private_mode_status(path)
    if permission_status:
        return HealthCheck(name, "warn", permission_status)
    return HealthCheck(name, "pass", f"file exists: {path}")


def _timeline_check(path: Path) -> HealthCheck:
    if path.is_symlink():
        return HealthCheck("timeline_file", "fail", f"refusing symlinked file: {path}")
    if not path.exists():
        return HealthCheck("timeline_file", "pass", "timeline will be created on first session")
    return _file_check(path, "timeline_file")


def _providers_check() -> HealthCheck:
    installed = sorted(name for name, detection in detect_all().items() if detection.installed)
    if not installed:
        return HealthCheck("providers", "warn", "no supported provider found on PATH")
    return HealthCheck("providers", "pass", "available providers: " + ", ".join(installed))


def _private_mode_status(path: Path) -> str:
    if os.name == "nt":
        return ""
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        return f"could not stat permissions: {exc}"
    if mode & 0o077:
        return f"permissions are too broad: {oct(mode)}"
    return ""


def _render(term: Terminal, checks: list[HealthCheck]) -> None:
    rows = [(check.name, f"{check.status}: {check.message}") for check in checks]
    term.section("loghop health", rows)
