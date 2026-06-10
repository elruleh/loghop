"""Guard the redaction custom-pattern cache invalidation.

Editing ``~/.loghop/config.toml`` or ``<project>/.loghop/config.toml`` must
take effect on the very next ``loghop`` invocation -- not on the next process
restart. These tests prove the cache invalidates whenever the file's
mtime changes.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from loghop import redact
from loghop.install._config import _save_global_config


def _isolate_home(tmp_path: Path, monkeypatch) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setattr(
        Path,
        "home",
        classmethod(
            lambda cls: Path(os.environ.get("HOME") or os.environ.get("USERPROFILE") or fake_home)
        ),
    )
    redact._clear_redact_cache()


def test_global_config_edit_takes_effect(tmp_path, monkeypatch) -> None:
    """Adding a custom pattern to the global config must apply on the next call."""
    _isolate_home(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)

    text = "alpha-beta-gamma"
    baseline = redact.redact_text(text)
    assert "alpha-beta-gamma" in baseline, "no custom pattern yet; should pass through"

    config_dir = Path(os.environ["HOME"]) / ".loghop"
    config_dir.mkdir(parents=True, exist_ok=True)
    _save_global_config(
        {
            "redaction": [
                {
                    "pattern": r"alpha-beta-gamma",
                    "replacement": "[test-redacted]",
                }
            ]
        }
    )

    # First call after edit: cache is invalidated by mtime, pattern applies.
    redacted = redact.redact_text(text)
    assert "alpha-beta-gamma" not in redacted
    assert "[test-redacted]" in redacted


def test_cache_invalidates_on_mtime_change(tmp_path, monkeypatch) -> None:
    """Same file, new mtime: cache must drop the old signature."""
    _isolate_home(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    config_dir = Path(os.environ["HOME"]) / ".loghop"
    config_dir.mkdir(parents=True, exist_ok=True)
    _save_global_config(
        {
            "redaction": [
                {"pattern": r"abc-123", "replacement": "[v1]"},
            ]
        }
    )
    assert "[v1]" in redact.redact_text("abc-123")

    # Force mtime forward; some filesystems have 1s mtime resolution.
    time.sleep(1.05)
    _save_global_config(
        {
            "redaction": [
                {"pattern": r"abc-123", "replacement": "[v2]"},
            ]
        }
    )
    # New mtime -> new cache signature.
    assert "[v2]" in redact.redact_text("abc-123")


def test_invalid_pattern_in_config_does_not_crash(tmp_path, monkeypatch) -> None:
    """A bad regex in custom redaction should not break redaction for other text."""
    _isolate_home(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    config_dir = Path(os.environ["HOME"]) / ".loghop"
    config_dir.mkdir(parents=True, exist_ok=True)
    _save_global_config(
        {
            "redaction": [
                {"pattern": r"(unbalanced", "replacement": "[bad]"},
            ]
        }
    )
    # The bad pattern is silently skipped; other text still redacts.
    assert redact.redact_text("") == ""
    assert "sk-ant-api01-1234567890abcdef12345678" not in redact.redact_text(
        "sk-ant-api01-1234567890abcdef12345678"
    )


def test_clear_redact_cache_resets_state(tmp_path) -> None:
    """_clear_redact_cache is part of the public invalidation API."""
    import re

    redact._CACHE_KEY = ("fake",)  # type: ignore[assignment]
    redact._CACHED_PATTERNS = [(re.compile("x"), "y")]
    redact._clear_redact_cache()
    assert redact._CACHE_KEY is None
    assert redact._CACHED_PATTERNS == []
