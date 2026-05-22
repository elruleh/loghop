import tomllib
from typing import Any

import tomli_w

from loghop.errors import E_INVALID_INPUT, LoghopError
from loghop.logging import get_logger
from loghop.store._constants import VERSION, ProjectPaths
from loghop.store._io import atomic_write_private_text, safe_read_text
from loghop.store._models import ProjectConfig

_LOGGER = get_logger()


def default_config(project_name: str) -> ProjectConfig:
    return ProjectConfig(
        version=VERSION,
        project_name=project_name,
        goal="",
        handoff_counter=0,
        session_counter=0,
        topic_counter=0,
        active_topic_id="",
    )


def load_config(paths: ProjectPaths) -> ProjectConfig:
    if not paths.config.exists():
        return default_config(paths.root.name)
    try:
        raw = tomllib.loads(safe_read_text(paths.config))
    except tomllib.TOMLDecodeError as exc:
        raise LoghopError(
            f"invalid config file `{paths.config.relative_to(paths.root)}`: {exc}",
            code=E_INVALID_INPUT,
        ) from exc
    return _normalize(raw, paths.root.name)


def save_config(paths: ProjectPaths, config: ProjectConfig) -> None:
    import dataclasses

    data = dataclasses.asdict(config)
    atomic_write_private_text(paths.config, tomli_w.dumps(data))


def _normalize(raw: dict[str, Any], project_name: str) -> ProjectConfig:
    raw_version = raw.get("version")
    version = VERSION
    if isinstance(raw_version, int):
        version = raw_version
        if raw_version > VERSION:
            _LOGGER.warning(
                "loghop config schema is newer than this binary; unknown keys will be ignored",
                extra={
                    "component": "config",
                    "project_name": project_name,
                    "config_version": raw_version,
                    "binary_version": VERSION,
                },
            )
    elif raw_version is not None:
        _LOGGER.warning(
            "loghop config has non-integer version field; using default",
            extra={
                "component": "config",
                "project_name": project_name,
                "raw_version": repr(raw_version),
            },
        )

    config_kwargs: dict[str, Any] = {
        "version": version,
        "project_name": project_name,
    }

    if isinstance(raw.get("project_name"), str):
        config_kwargs["project_name"] = raw["project_name"]
    if isinstance(raw.get("goal"), str):
        config_kwargs["goal"] = raw.get("goal")
    if isinstance(raw.get("handoff_counter"), int):
        config_kwargs["handoff_counter"] = max(0, min(raw["handoff_counter"], 999999))
    if isinstance(raw.get("session_counter"), int):
        config_kwargs["session_counter"] = max(0, min(raw["session_counter"], 999999))
    if isinstance(raw.get("topic_counter"), int):
        config_kwargs["topic_counter"] = max(0, min(raw["topic_counter"], 999999))
    if isinstance(raw.get("active_topic_id"), str):
        config_kwargs["active_topic_id"] = raw["active_topic_id"]
    if isinstance(raw.get("handoff_patch_lines"), int):
        config_kwargs["handoff_patch_lines"] = max(10, min(raw["handoff_patch_lines"], 50000))

    return ProjectConfig(**config_kwargs)
