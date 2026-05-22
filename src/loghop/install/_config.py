import json
import os
import shutil
import sys
import tomllib
from contextlib import suppress
from pathlib import Path
from typing import Any

import tomli_w

from loghop import __version__
from loghop.install._types import (
    GLOBAL_CONFIG_FILENAME,
    INIT_INSTALL_KEYS,
    InitInstallChoices,
)
from loghop.store._io import atomic_write_private_text, safe_read_text
from loghop.store._registry import global_dir


def global_config_path() -> Path:
    return global_dir() / GLOBAL_CONFIG_FILENAME


def load_init_install_choices() -> InitInstallChoices | None:
    config = _load_global_config()
    install = config.get("install")
    if not isinstance(install, dict):
        return None
    values: dict[str, bool] = {}
    for key in INIT_INSTALL_KEYS:
        value = install.get(key)
        if not isinstance(value, bool):
            return None
        values[key] = value
    return InitInstallChoices(**values)


def save_init_install_choices(choices: InitInstallChoices) -> None:
    config = _load_global_config()
    install = config.setdefault("install", {})
    if not isinstance(install, dict):
        install = {}
        config["install"] = install
    install.update(choices.as_dict())
    install["installed_version"] = __version__
    _save_global_config(config)


def load_installed_version() -> str | None:
    config = _load_global_config()
    install = config.get("install")
    if not isinstance(install, dict):
        return None
    value = install.get("installed_version")
    return value if isinstance(value, str) else None


def load_codex_shim_prefix() -> Path | None:
    config = _load_global_config()
    install = config.get("install")
    if not isinstance(install, dict):
        return None
    value = install.get("codex_shim_prefix")
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value).expanduser()


def save_codex_shim_prefix(prefix: Path | None) -> None:
    config = _load_global_config()
    install = config.setdefault("install", {})
    if not isinstance(install, dict):
        install = {}
        config["install"] = install
    if prefix is None:
        install.pop("codex_shim_prefix", None)
    else:
        install["codex_shim_prefix"] = str(prefix.expanduser())
    _save_global_config(config)


def load_tui_preferences() -> dict[str, str]:
    config = _load_global_config()
    tui = config.get("tui")
    if not isinstance(tui, dict):
        return {}
    out: dict[str, str] = {}
    for key in ("theme", "language"):
        value = tui.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()
    return out


def save_tui_preferences(
    *,
    theme: str | None = None,
    language: str | None = None,
) -> None:
    config = _load_global_config()
    tui = config.setdefault("tui", {})
    if not isinstance(tui, dict):
        tui = {}
        config["tui"] = tui
    if theme is not None:
        if theme.strip():
            tui["theme"] = theme.strip()
        else:
            tui.pop("theme", None)
    if language is not None:
        if language.strip():
            tui["language"] = language.strip()
        else:
            tui.pop("language", None)
    if not tui:
        config.pop("tui", None)
    _save_global_config(config)


def load_tracked_project_roots() -> list[Path]:
    config = _load_global_config()
    install = config.get("install")
    if not isinstance(install, dict):
        return []
    raw = install.get("project_roots")
    if not isinstance(raw, list):
        return []
    roots: list[Path] = []
    seen: set[str] = set()
    for value in raw:
        if not isinstance(value, str) or not value.strip():
            continue
        resolved = str(Path(value).expanduser())
        if resolved in seen:
            continue
        seen.add(resolved)
        roots.append(Path(resolved))
    return roots


def track_project_root(root: Path) -> None:
    config = _load_global_config()
    install = config.setdefault("install", {})
    if not isinstance(install, dict):
        install = {}
        config["install"] = install
    roots = [str(path) for path in load_tracked_project_roots()]
    resolved = str(root.expanduser().resolve())
    if resolved not in roots:
        roots.append(resolved)
    install["project_roots"] = roots
    _save_global_config(config)


def untrack_project_root(root: Path) -> None:
    config = _load_global_config()
    install = config.get("install")
    if not isinstance(install, dict):
        return
    resolved = str(root.expanduser().resolve())
    roots = [str(path) for path in load_tracked_project_roots() if str(path) != resolved]
    if roots:
        install["project_roots"] = roots
    else:
        install.pop("project_roots", None)
    _save_global_config(config)


def clear_tracked_project_roots() -> None:
    config = _load_global_config()
    install = config.get("install")
    if not isinstance(install, dict):
        return
    install.pop("project_roots", None)
    _save_global_config(config)


def _backup(path: Path) -> Path | None:
    """Copy ``path`` to a sibling ``.loghop.bak`` and return the backup path.

    Returns None when there is nothing to back up or the copy itself fails so
    callers can decide whether to abort. Failures are surfaced on stderr.
    """
    if not path.exists():
        return None
    if path.is_symlink():
        print(f"warning: refusing to back up symlinked file {path}", file=sys.stderr)  # noqa: T201
        return None
    bak = path.with_suffix(path.suffix + ".loghop.bak")
    try:
        shutil.copy2(path, bak)
        with suppress(OSError):
            os.chmod(bak, 0o600)
    except OSError as exc:
        print(f"warning: could not back up {path}: {exc}", file=sys.stderr)  # noqa: T201
        return None
    return bak


def _load_global_config() -> dict[str, Any]:
    path = global_config_path()
    if not path.exists():
        return {}
    try:
        data = tomllib.loads(safe_read_text(path))
    except (OSError, tomllib.TOMLDecodeError):
        _backup(path)
        return {}
    return data if isinstance(data, dict) else {}


def _save_global_config(config: dict[str, Any]) -> None:
    _backup(global_config_path())
    text = "# loghop global config\n\n" + tomli_w.dumps(config)
    atomic_write_private_text(global_config_path(), text)


def _read_json_or_empty(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        data = json.loads(safe_read_text(path))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
