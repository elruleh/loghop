from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import pytest

from loghop.env import _env_int
from loghop.logging import (
    JsonFormatter,
    _json_safe,
    _log_level,
    configure_project_logging,
    get_logger,
)

LOGGER_NAME = "loghop"


@pytest.fixture(autouse=True)
def _clean_logger() -> Any:
    yield
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.setLevel(logging.WARNING)


class TestJsonSafe:
    def test_none(self) -> None:
        assert _json_safe(None) is None

    def test_bool(self) -> None:
        assert _json_safe(True) is True

    def test_int(self) -> None:
        assert _json_safe(42) == 42

    def test_float(self) -> None:
        assert _json_safe(3.14) == 3.14

    def test_str(self) -> None:
        assert _json_safe("hello") == "hello"

    def test_path(self) -> None:
        assert _json_safe(Path("/tmp/x")) == "/tmp/x"

    def test_dict(self) -> None:
        result = _json_safe({"a": 1, "b": Path("/y")})
        assert result == {"a": 1, "b": "/y"}

    def test_list(self) -> None:
        assert _json_safe([1, "two", Path("/three")]) == [1, "two", "/three"]

    def test_tuple(self) -> None:
        assert _json_safe((1, 2)) == [1, 2]

    def test_set(self) -> None:
        result = _json_safe({1, 2})
        assert sorted(result) == [1, 2]

    def test_unknown_object(self) -> None:
        result = _json_safe(object())
        assert isinstance(result, str)

    def test_nested(self) -> None:
        result = _json_safe({"items": [Path("/a"), {"b": 2}]})
        assert result == {"items": ["/a", {"b": 2}]}


class TestEnvInt:
    def test_missing_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TEST_VAR", raising=False)
        assert _env_int("TEST_VAR", 42) == 42

    def test_valid_int(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_VAR", "100")
        assert _env_int("TEST_VAR", 42) == 100

    def test_invalid_string_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_VAR", "not-a-number")
        assert _env_int("TEST_VAR", 42) == 42

    def test_negative_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_VAR", "-5")
        assert _env_int("TEST_VAR", 42) == 42

    def test_zero_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_VAR", "0")
        assert _env_int("TEST_VAR", 42) == 42


class TestLogLevel:
    def test_default_is_info(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LOGHOP_LOG_LEVEL", raising=False)
        assert _log_level() == logging.INFO

    def test_debug(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOGHOP_LOG_LEVEL", "DEBUG")
        assert _log_level() == logging.DEBUG

    def test_warning(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOGHOP_LOG_LEVEL", "warning")
        assert _log_level() == logging.WARNING

    def test_invalid_falls_back_to_info(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOGHOP_LOG_LEVEL", "BOGUS")
        assert _log_level() == logging.INFO


class TestGetLogger:
    def test_returns_named_logger(self) -> None:
        logger = get_logger()
        assert logger.name == LOGGER_NAME

    def test_propagate_false(self) -> None:
        logger = get_logger()
        assert logger.propagate is False

    def test_has_handler(self) -> None:
        logger = get_logger()
        assert len(logger.handlers) >= 1


class TestConfigureProjectLogging:
    def test_root_none_creates_global_log(self) -> None:
        logging.getLogger(LOGGER_NAME).handlers.clear()
        logger = configure_project_logging(None)
        assert any(isinstance(h, logging.handlers.RotatingFileHandler) for h in logger.handlers)
        assert (Path.home() / ".loghop" / "loghop.log").exists()

    def test_creates_file_handler(self, tmp_path: Path) -> None:
        logging.getLogger(LOGGER_NAME).handlers.clear()
        logger = configure_project_logging(tmp_path)
        assert any(isinstance(h, logging.handlers.RotatingFileHandler) for h in logger.handlers)
        log_file = tmp_path / ".loghop" / "loghop.log"
        assert log_file.exists()

    def test_reuses_existing_handler_same_root(self, tmp_path: Path) -> None:
        logging.getLogger(LOGGER_NAME).handlers.clear()
        logger1 = configure_project_logging(tmp_path)
        file_handlers = [
            h for h in logger1.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(file_handlers) == 1

        logger2 = configure_project_logging(tmp_path)
        file_handlers2 = [
            h for h in logger2.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(file_handlers2) == 1

    def test_replaces_handler_on_different_root(self, tmp_path: Path) -> None:
        logging.getLogger(LOGGER_NAME).handlers.clear()
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()

        configure_project_logging(dir_a)
        configure_project_logging(dir_b)
        logger = logging.getLogger(LOGGER_NAME)
        file_handlers = [
            h for h in logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(file_handlers) == 1
        assert "b" in file_handlers[0].baseFilename

    def test_log_level_from_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        logging.getLogger(LOGGER_NAME).handlers.clear()
        monkeypatch.setenv("LOGHOP_LOG_LEVEL", "DEBUG")
        logger = configure_project_logging(tmp_path)
        assert logger.level == logging.DEBUG

    @pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
    def test_rejects_symlinked_log_file(self, tmp_path: Path) -> None:
        logging.getLogger(LOGGER_NAME).handlers.clear()
        log_dir = tmp_path / ".loghop"
        log_dir.mkdir(mode=0o700)
        target = tmp_path / "other.log"
        target.write_text("", encoding="utf-8")
        (log_dir / "loghop.log").symlink_to(target)
        with pytest.raises(ValueError, match="symlinked log file"):
            configure_project_logging(tmp_path)


class TestJsonFormatter:
    def test_format_basic_record(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="loghop",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        import json

        output = formatter.format(record)
        payload = json.loads(output)
        assert payload["message"] == "hello world"
        assert payload["level"] == "info"
        assert payload["logger"] == "loghop"
        assert "ts" in payload

    def test_format_includes_extra_fields(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="loghop",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )
        record.component = "store"
        record.path = Path("/tmp/x")
        import json

        output = formatter.format(record)
        payload = json.loads(output)
        assert payload["component"] == "store"
        assert payload["path"] == "/tmp/x"

    def test_format_redacts_message_and_extras(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="loghop",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="token=sk-secret-value",
            args=(),
            exc_info=None,
        )
        record.prompt = "Bearer abc123"
        import json

        output = formatter.format(record)
        payload = json.loads(output)
        assert "[redacted]" in payload["message"]
        assert payload["prompt"] == "Bearer [redacted]"
