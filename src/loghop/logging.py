import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from loghop import env

_LOGGER_NAME = "loghop"
_LOG_FILE_NAME = "loghop.log"
_MAX_LOG_BYTES = 256 * 1024
_BACKUP_COUNT = 3
_LOG_FILE_MODE = 0o600
_STANDARD_LOG_RECORD_KEYS = frozenset(logging.makeLogRecord({}).__dict__)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        from loghop.redact import redact_dict, redact_text

        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if (
                key in _STANDARD_LOG_RECORD_KEYS
                or key in {"message", "asctime"}
                or key.startswith("_")
            ):
                continue
            payload[key] = _json_safe(redact_dict(value))
        return json.dumps(payload, sort_keys=True)


def get_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    logger.propagate = False
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def configure_project_logging(root: Path | None) -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    logger.propagate = False
    logger.setLevel(_log_level())
    if root is None:
        return configure_global_logging()

    log_dir = root / ".loghop"
    return _configure_file_logging(logger, log_dir)


def configure_global_logging() -> logging.Logger:
    from loghop.store._registry import global_dir

    logger = logging.getLogger(_LOGGER_NAME)
    logger.propagate = False
    logger.setLevel(_log_level())
    return _configure_file_logging(logger, global_dir())


def _validate_log_dir(log_dir: Path) -> None:
    if log_dir.is_symlink():
        raise ValueError("refusing to write logs into a symlinked .loghop directory")
    if log_dir.exists() and not log_dir.is_dir():
        raise ValueError("refusing to write logs into a non-directory .loghop path")


def _configure_file_logging(logger: logging.Logger, log_dir: Path) -> logging.Logger:
    _validate_log_dir(log_dir)
    from loghop.store._io import _ensure_directory

    _ensure_directory(log_dir)
    log_path = log_dir / _LOG_FILE_NAME
    if log_path.exists() and log_path.is_symlink():
        raise ValueError("refusing to write logs into a symlinked log file")
    return _setup_file_handler(logger, log_path)


def _setup_file_handler(logger: logging.Logger, log_path: Path) -> logging.Logger:
    for handler in list(logger.handlers):
        if isinstance(handler, RotatingFileHandler):
            if Path(handler.baseFilename) == log_path:
                handler.setLevel(_log_level())
                return logger
            logger.removeHandler(handler)
            handler.close()
        elif isinstance(handler, logging.NullHandler):
            logger.removeHandler(handler)

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(log_path, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, _LOG_FILE_MODE)
        os.close(fd)
    except OSError:
        pass
    handler = RotatingFileHandler(
        log_path,
        maxBytes=env.log_max_bytes(_MAX_LOG_BYTES),
        backupCount=env.log_backup_count(_BACKUP_COUNT),
        encoding="utf-8",
    )
    handler.setLevel(_log_level())
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger


def _log_level() -> int:
    value = env.log_level()
    level = getattr(logging, value, None)
    if not isinstance(level, int):
        return logging.INFO
    return level


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe(item) for item in value]
    return str(value)
