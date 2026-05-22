from __future__ import annotations

import argparse
import dataclasses
import json
import tomllib
from pathlib import Path
from typing import Any

from loghop.gittools import GitRepo
from loghop.store import load_config, project_paths, save_config
from loghop.store._constants import FILE_MODE, VERSION
from loghop.store._io import atomic_write_text, safe_read_text
from loghop.terminal import Terminal


def handle_migrate(args: argparse.Namespace, term: Terminal) -> int:
    repo = GitRepo.from_cwd(Path.cwd())
    if repo is None:
        term.error("loghop migrate requires a Git repository")
        term.capture_result({"migrated": False, "error": "not_git_repo"})
        return 2
    root = repo.root.resolve()
    paths = project_paths(root)
    if not paths.dot.exists():
        term.error("loghop is not initialized in this repository")
        term.capture_result({"migrated": False, "error": "not_initialized"})
        return 20

    dry_run = bool(getattr(args, "dry_run", False))
    config_changed = _config_needs_migration(paths.config)
    timeline_changed = _timeline_needs_migration(paths.timeline)
    changed = config_changed or timeline_changed
    if changed and not dry_run:
        _migrate_config(paths.config, paths.root.name)
        _migrate_timeline(paths.timeline)
    if changed:
        term.success("migrations applied" if not dry_run else "migrations pending")
    else:
        term.info("no migrations needed")
    term.capture_result(
        {
            "changed": changed,
            "dry_run": dry_run,
            "config_changed": config_changed,
            "timeline_changed": timeline_changed,
            "target_version": VERSION,
        }
    )
    return 0


def _config_needs_migration(config_path: Path) -> bool:
    if not config_path.exists():
        return True
    try:
        raw = tomllib.loads(safe_read_text(config_path))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return raw.get("version") != VERSION or "handoff_patch_lines" not in raw


def _migrate_config(config_path: Path, project_name: str) -> None:
    paths = project_paths(config_path.parent.parent)
    config = load_config(paths)
    save_config(
        paths,
        dataclasses.replace(
            config, version=VERSION, project_name=config.project_name or project_name
        ),
    )


def _timeline_needs_migration(timeline_path: Path) -> bool:
    if not timeline_path.exists():
        return False
    return any("schema_version" not in event for event in _read_jsonl(timeline_path))


def _migrate_timeline(timeline_path: Path) -> None:
    if not timeline_path.exists():
        return
    events = []
    for event in _read_jsonl(timeline_path):
        migrated = dict(event)
        migrated.setdefault("schema_version", 1)
        events.append(migrated)
    text = "".join(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n" for event in events)
    atomic_write_text(timeline_path, text, file_mode=FILE_MODE)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        raw = safe_read_text(path)
    except OSError:
        return []
    events: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            events.append(data)
    return events
