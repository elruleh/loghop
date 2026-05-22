"""Audit fix #12: detect provider transcript schema drift.

When Anthropic or OpenAI ship a new event type / block type that our
parser doesn't recognize, we must surface a single warning per parse so
operators can update the allowlist — instead of silently dropping data.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from loghop.transcripts._claude import ClaudeTranscriptReader
from loghop.transcripts._codex import CodexTranscriptReader


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _capture_logs() -> _ListHandler:
    from loghop.logging import get_logger

    handler = _ListHandler()
    handler.setLevel(logging.WARNING)
    logger = get_logger()
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    return handler


def _detach(handler: logging.Handler) -> None:
    from loghop.logging import get_logger

    get_logger().removeHandler(handler)


def _write_jsonl(path: Path, entries: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


class TestClaudeDriftDetection:
    def test_known_only_does_not_warn(self, tmp_path: Path) -> None:
        path = tmp_path / "claude.jsonl"
        _write_jsonl(
            path,
            [
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": "hi"}],
                    },
                },
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "hello"}],
                    },
                },
                {"type": "system"},
                {"type": "summary"},
            ],
        )
        cap = _capture_logs()
        try:
            list(ClaudeTranscriptReader().parse(path))
        finally:
            _detach(cap)
        # No drift records — every type is in the allowlist.
        assert not any("schema drift" in r.getMessage() for r in cap.records), [
            r.getMessage() for r in cap.records
        ]

    def test_current_metadata_types_do_not_warn(self, tmp_path: Path) -> None:
        path = tmp_path / "claude-current.jsonl"
        _write_jsonl(
            path,
            [
                {"type": "permission-mode", "permissionMode": "default"},
                {"type": "attachment", "filePath": "README.md"},
                {"type": "last-prompt", "prompt": "resume"},
                {"type": "ai-title", "title": "Work summary"},
            ],
        )
        cap = _capture_logs()
        try:
            list(ClaudeTranscriptReader().parse(path))
        finally:
            _detach(cap)

        assert not any("schema drift" in r.getMessage() for r in cap.records)

    def test_unknown_top_type_emits_warning(self, tmp_path: Path) -> None:
        path = tmp_path / "claude.jsonl"
        _write_jsonl(
            path,
            [
                {"type": "assistant", "message": {"role": "assistant", "content": []}},
                {"type": "fancy_new_event", "payload": {}},
                {"type": "fancy_new_event", "payload": {}},
                {"type": "another_new_one"},
            ],
        )
        cap = _capture_logs()
        try:
            list(ClaudeTranscriptReader().parse(path))
        finally:
            _detach(cap)
        drift_records = [r for r in cap.records if "schema drift" in r.getMessage()]
        assert len(drift_records) == 1, "should emit exactly one drift record per parse"
        rec = drift_records[0]
        unknown = getattr(rec, "unknown_top_types", [])
        assert any("fancy_new_event" in s for s in unknown)
        assert any("another_new_one" in s for s in unknown)
        # Counts are encoded as ``name(N)``.
        assert any("fancy_new_event(2)" in s for s in unknown)

    def test_unknown_content_block_type_emits_warning(self, tmp_path: Path) -> None:
        path = tmp_path / "claude.jsonl"
        _write_jsonl(
            path,
            [
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "hi"},
                            {"type": "video", "url": "..."},
                        ],
                    },
                },
            ],
        )
        cap = _capture_logs()
        try:
            list(ClaudeTranscriptReader().parse(path))
        finally:
            _detach(cap)
        drift = [r for r in cap.records if "schema drift" in r.getMessage()]
        assert drift
        unknown = getattr(drift[0], "unknown_block_types", [])
        assert any("video" in s for s in unknown)


class TestCodexDriftDetection:
    def test_known_only_does_not_warn(self, tmp_path: Path) -> None:
        path = tmp_path / "rollout.jsonl"
        _write_jsonl(
            path,
            [
                {"type": "session_meta", "payload": {"cwd": "/x"}},
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "ok"}],
                    },
                },
                {"type": "event"},
            ],
        )
        cap = _capture_logs()
        try:
            list(CodexTranscriptReader().parse(path))
        finally:
            _detach(cap)
        assert not any("schema drift" in r.getMessage() for r in cap.records)

    def test_current_metadata_types_do_not_warn(self, tmp_path: Path) -> None:
        path = tmp_path / "rollout-current.jsonl"
        _write_jsonl(
            path,
            [
                {"type": "event_msg", "payload": {"type": "task_started"}},
                {"type": "turn_context", "payload": {"cwd": str(tmp_path)}},
            ],
        )
        cap = _capture_logs()
        try:
            list(CodexTranscriptReader().parse(path))
        finally:
            _detach(cap)

        assert not any("schema drift" in r.getMessage() for r in cap.records)

    def test_unknown_top_type_emits_warning(self, tmp_path: Path) -> None:
        path = tmp_path / "rollout.jsonl"
        _write_jsonl(
            path,
            [
                {"type": "response_item", "payload": {"type": "message", "role": "assistant"}},
                {"type": "brand_new_codex_event", "payload": {}},
            ],
        )
        cap = _capture_logs()
        try:
            list(CodexTranscriptReader().parse(path))
        finally:
            _detach(cap)
        drift = [r for r in cap.records if "schema drift" in r.getMessage()]
        assert drift
        unknown = getattr(drift[0], "unknown_top_types", [])
        assert any("brand_new_codex_event" in s for s in unknown)

    def test_non_string_type_is_treated_as_drift(self, tmp_path: Path) -> None:
        # A null or non-string `type` is itself a drift signal.
        path = tmp_path / "rollout.jsonl"
        _write_jsonl(
            path,
            [
                {"type": "session_meta", "payload": {"cwd": "/x"}},
                {"type": 42, "payload": {}},
            ],
        )
        cap = _capture_logs()
        try:
            list(CodexTranscriptReader().parse(path))
        finally:
            _detach(cap)
        drift = [r for r in cap.records if "schema drift" in r.getMessage()]
        assert drift
        unknown = getattr(drift[0], "unknown_top_types", [])
        assert any("<int>" in s for s in unknown)
