import json
import shlex
import shutil
import sys
from pathlib import Path

from loghop.install._config import _backup
from loghop.install._types import InstallReport
from loghop.store._io import atomic_write_text, project_lock


def install_claude_hooks(
    *,
    scope_user: bool = True,
    project_root: Path | None = None,
    uninstall: bool = False,
    dry_run: bool = False,
) -> list[InstallReport]:
    """Merge SessionStart/SessionEnd hook entries into Claude's settings.json.

    Holds a per-file PID lock around the read-modify-write so concurrent
    invocations cannot clobber third-party hooks (TOCTOU race).
    """
    settings_path = _claude_settings_path(scope_user, project_root)
    if settings_path is None:
        return []
    if dry_run:
        # Dry-run does not write — no lock needed and we don't want to create
        # the parent directory just to drop a lockfile.
        if uninstall:
            return [_remove_claude_hooks(settings_path, dry_run=True)]
        return [_ensure_claude_hooks(settings_path, dry_run=True)]
    lock_path = settings_path.parent / ".loghop-settings.lock"
    try:
        with project_lock(lock_path):
            if uninstall:
                return [_remove_claude_hooks(settings_path, dry_run=False)]
            return [_ensure_claude_hooks(settings_path, dry_run=False)]
    except TimeoutError as exc:
        return [InstallReport(settings_path, "error", str(exc))]
    except ValueError as exc:
        return [InstallReport(settings_path, "error", str(exc))]
    except OSError as exc:
        # Lock could not be created (read-only dir, EACCES, etc.). Surface the
        # failure as a clean error report rather than crashing the caller.
        return [InstallReport(settings_path, "error", f"could not lock settings.json: {exc}")]


def claude_hooks_installed(
    *,
    scope_user: bool = True,
    project_root: Path | None = None,
) -> bool:
    """Return True if loghop's Claude session hooks are present in settings.json."""
    path = _claude_settings_path(scope_user, project_root)
    if path is None or not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False
    for event in ("SessionStart", "SessionEnd"):
        entries = hooks.get(event)
        if not isinstance(entries, list):
            return False
        if not any(_is_loghop_hook_entry(e) for e in entries):
            return False
    return True


def _claude_settings_path(scope_user: bool, project_root: Path | None) -> Path | None:
    if scope_user:
        return Path.home() / ".claude" / "settings.json"
    if project_root is None:
        return None
    return project_root / ".claude" / "settings.json"


def _claude_hook_entries() -> dict[str, list[dict[str, object]]]:
    return {
        "SessionStart": [
            {
                "matcher": "startup|resume",
                "hooks": [
                    {
                        "type": "command",
                        "command": _loghop_hook_command("claude-session-start"),
                        "timeout": 10,
                    }
                ],
                "_loghop": True,
            }
        ],
        "SessionEnd": [
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": _loghop_hook_command("claude-session-end"),
                        "timeout": 30,
                    }
                ],
                "_loghop": True,
            }
        ],
    }


def _loghop_hook_command(event: str) -> str:
    launcher = _loghop_launcher_argv()
    return shlex.join([*launcher, "hook", event])


def _loghop_launcher_argv() -> list[str]:
    cli_path = shutil.which("loghop")
    if cli_path and Path(cli_path).is_absolute():
        return [cli_path]
    python = Path(sys.executable).expanduser()
    if not python.is_absolute():
        python = python.resolve(strict=False)
    return [str(python), "-m", "loghop"]


def _read_settings_strict(path: Path) -> dict[str, object] | InstallReport:
    """Read settings.json, surface corruption as a hard error report.

    Unlike the lenient _read_json_or_empty helper, malformed JSON here returns
    an InstallReport with action='error' so the caller can abort the install
    rather than silently overwrite the file.
    """
    try:
        if path.is_symlink():
            return InstallReport(
                path,
                "error",
                "settings.json is a symlink; refusing to replace it",
            )
    except OSError as exc:
        return InstallReport(path, "error", f"could not inspect settings.json: {exc}")
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return InstallReport(path, "error", f"could not read settings.json: {exc}")
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return InstallReport(
            path,
            "error",
            f"settings.json is not valid JSON ({exc.msg} at line {exc.lineno}); "
            "fix it manually before installing loghop hooks",
        )
    if not isinstance(data, dict):
        return InstallReport(path, "error", "settings.json top-level is not an object")
    return data


def _ensure_claude_hooks(path: Path, *, dry_run: bool) -> InstallReport:
    settings = _read_settings_strict(path)
    if isinstance(settings, InstallReport):
        return settings
    hooks_block = settings.setdefault("hooks", {})
    if not isinstance(hooks_block, dict):
        return InstallReport(path, "error", "settings.json `hooks` is not an object")
    desired_serialized: dict[str, str] = {}
    existing_serialized: dict[str, str] = {}
    for event, entries in _claude_hook_entries().items():
        existing = hooks_block.setdefault(event, [])
        if not isinstance(existing, list):
            return InstallReport(path, "error", f"settings.json `hooks.{event}` is not a list")
        existing_serialized[event] = json.dumps(existing, sort_keys=True)
        non_loghop = [e for e in existing if not _is_loghop_hook_entry(e)]
        new_entries = non_loghop + entries
        desired_serialized[event] = json.dumps(new_entries, sort_keys=True)
        if not dry_run:
            existing[:] = new_entries
    no_change = existing_serialized == desired_serialized
    is_new = not path.exists()
    if no_change and not is_new:
        return InstallReport(path, "unchanged")
    if dry_run:
        return InstallReport(path, "would-create" if is_new else "would-update")
    backup = _backup(path)
    if path.exists() and backup is None:
        return InstallReport(path, "error", "could not back up settings.json before updating")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(settings, indent=2, sort_keys=False) + "\n")
    except OSError as exc:
        return InstallReport(path, "error", f"could not write settings.json: {exc}")
    return InstallReport(path, "created" if is_new else "updated")


def _remove_claude_hooks(path: Path, *, dry_run: bool) -> InstallReport:
    if not path.exists():
        return InstallReport(path, "unchanged", "settings.json absent")
    settings = _read_settings_strict(path)
    if isinstance(settings, InstallReport):
        return settings
    hooks_block = settings.get("hooks")
    if not isinstance(hooks_block, dict):
        return InstallReport(path, "unchanged", "no hooks block")
    removed_anything = _remove_loghop_events(hooks_block, dry_run=dry_run)
    if not removed_anything:
        return InstallReport(path, "unchanged")
    if dry_run:
        return InstallReport(path, "would-remove")
    if not hooks_block:
        settings.pop("hooks", None)
    backup = _backup(path)
    if backup is None:
        return InstallReport(path, "error", "could not back up settings.json before updating")
    try:
        atomic_write_text(path, json.dumps(settings, indent=2, sort_keys=False) + "\n")
    except OSError as exc:
        return InstallReport(path, "error", f"could not write settings.json: {exc}")
    return InstallReport(path, "updated")


def _remove_loghop_events(hooks_block: dict[str, object], *, dry_run: bool) -> bool:
    removed_anything = False
    for event in ("SessionStart", "SessionEnd"):
        entries = hooks_block.get(event)
        if not isinstance(entries, list):
            continue
        new_entries = [e for e in entries if not _is_loghop_hook_entry(e)]
        if len(new_entries) != len(entries):
            removed_anything = True
            if dry_run:
                continue
            if new_entries:
                hooks_block[event] = new_entries
            else:
                hooks_block.pop(event, None)
    return removed_anything


def _is_loghop_hook_entry(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("_loghop") is True:
        return True
    hooks = entry.get("hooks")
    if not isinstance(hooks, list):
        return False
    return any(
        isinstance(h, dict)
        and isinstance(h.get("command"), str)
        and _is_loghop_hook_command(h["command"])
        for h in hooks
    )


def _is_loghop_hook_command(command: str) -> bool:
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if (
        len(argv) == 3  # noqa: PLR2004
        and argv[1] == "hook"
        and argv[2]
        in {
            "claude-session-start",
            "claude-session-end",
        }
    ):
        return argv[0] == "loghop" or Path(argv[0]).name == "loghop"
    return (
        len(argv) == 5  # noqa: PLR2004
        and Path(argv[0]).is_absolute()
        and argv[1:4] == ["-m", "loghop", "hook"]
        and argv[4] in {"claude-session-start", "claude-session-end"}
    )
