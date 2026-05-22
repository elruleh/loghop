"""Unit tests for transcript parsers — edge cases in _claude.py and _codex.py."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, entries: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def _make_claude_entry(
    role: str, text: str | list[Any], ts: str = "2026-01-01T00:00:00Z"
) -> dict[str, Any]:
    content: str | list[Any] = [{"type": "text", "text": text}] if isinstance(text, str) else text
    return {
        "type": role,
        "message": {"role": role, "content": content},
        "timestamp": ts,
    }


# ---------------------------------------------------------------------------
# ClaudeTranscriptReader
# ---------------------------------------------------------------------------


class TestClaudeTranscriptReaderParse:
    def test_skips_empty_lines(self, tmp_path: Path) -> None:
        from loghop.transcripts._claude import ClaudeTranscriptReader

        p = tmp_path / "t.jsonl"
        p.write_text("\n\n" + json.dumps(_make_claude_entry("assistant", "hi")) + "\n\n")
        turns = list(ClaudeTranscriptReader().parse(p))
        assert len(turns) == 1
        assert turns[0].text == "hi"

    def test_skips_invalid_json_lines(self, tmp_path: Path) -> None:
        from loghop.transcripts._claude import ClaudeTranscriptReader

        p = tmp_path / "t.jsonl"
        p.write_text("not-json\n" + json.dumps(_make_claude_entry("assistant", "ok")) + "\n")
        turns = list(ClaudeTranscriptReader().parse(p))
        assert len(turns) == 1

    def test_skips_non_dict_entries(self, tmp_path: Path) -> None:
        from loghop.transcripts._claude import ClaudeTranscriptReader

        p = tmp_path / "t.jsonl"
        p.write_text(json.dumps([1, 2, 3]) + "\n")
        turns = list(ClaudeTranscriptReader().parse(p))
        assert turns == []

    def test_handles_oserror_on_missing_file(self, tmp_path: Path) -> None:
        from loghop.transcripts._claude import ClaudeTranscriptReader

        p = tmp_path / "nonexistent.jsonl"
        turns = list(ClaudeTranscriptReader().parse(p))
        assert turns == []

    def test_skips_non_user_assistant_type(self, tmp_path: Path) -> None:
        from loghop.transcripts._claude import ClaudeTranscriptReader

        p = tmp_path / "t.jsonl"
        entries = [
            {"type": "system", "message": {"role": "system", "content": "sys"}, "timestamp": ""},
            {"type": "summary", "message": {"role": "system", "content": "sum"}, "timestamp": ""},
        ]
        _write_jsonl(p, entries)
        turns = list(ClaudeTranscriptReader().parse(p))
        assert turns == []

    def test_skips_when_message_not_dict(self, tmp_path: Path) -> None:
        from loghop.transcripts._claude import ClaudeTranscriptReader

        p = tmp_path / "t.jsonl"
        p.write_text(json.dumps({"type": "assistant", "message": "string", "timestamp": ""}) + "\n")
        turns = list(ClaudeTranscriptReader().parse(p))
        assert turns == []

    def test_skips_when_role_not_user_or_assistant(self, tmp_path: Path) -> None:
        from loghop.transcripts._claude import ClaudeTranscriptReader

        p = tmp_path / "t.jsonl"
        entry = {"type": "user", "message": {"role": "tool", "content": "x"}, "timestamp": ""}
        p.write_text(json.dumps(entry) + "\n")
        turns = list(ClaudeTranscriptReader().parse(p))
        assert turns == []

    def test_skips_when_no_text_extracted(self, tmp_path: Path) -> None:
        from loghop.transcripts._claude import ClaudeTranscriptReader

        p = tmp_path / "t.jsonl"
        entry = {
            "type": "assistant",
            "message": {"role": "assistant", "content": []},
            "timestamp": "",
        }
        p.write_text(json.dumps(entry) + "\n")
        turns = list(ClaudeTranscriptReader().parse(p))
        assert turns == []


class TestExtractTextClaude:
    def _extract(self, content: object) -> str:
        from loghop.transcripts._claude import _extract_text

        return _extract_text(content)

    def test_none_returns_empty(self) -> None:
        assert self._extract(None) == ""

    def test_string_content_returned_as_is(self) -> None:
        assert self._extract("hello") == "hello"

    def test_list_with_string_blocks(self) -> None:
        assert self._extract(["foo", "bar"]) == "foo\nbar"

    def test_non_dict_non_string_block_skipped(self) -> None:
        assert self._extract([42, {"type": "text", "text": "real"}]) == "real"

    def test_tool_use_block(self) -> None:
        result = self._extract([{"type": "tool_use", "name": "bash"}])
        assert "[tool_use: bash]" in result

    def test_tool_result_string(self) -> None:
        result = self._extract([{"type": "tool_result", "content": "output here"}])
        assert "[tool_result] output here" in result

    def test_tool_result_list(self) -> None:
        inner = [{"type": "text", "text": "nested"}]
        result = self._extract([{"type": "tool_result", "content": inner}])
        assert "nested" in result

    def test_unsupported_block_type_skipped(self) -> None:
        result = self._extract([{"type": "image", "data": "base64..."}])
        assert result == ""

    def test_non_list_non_string_returns_empty(self) -> None:
        assert self._extract({"type": "text", "text": "not a list"}) == ""


class TestClaudeFindLatest:
    def test_returns_none_when_no_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from loghop.transcripts._claude import ClaudeTranscriptReader

        monkeypatch.setattr(
            "loghop.transcripts._claude._claude_projects_root", lambda: tmp_path / "nodir"
        )
        since = datetime.now(tz=UTC)
        result = ClaudeTranscriptReader().find_latest(tmp_path, since)
        assert result is None

    def test_skips_files_older_than_since(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from loghop.transcripts._claude import ClaudeTranscriptReader

        slug = str(tmp_path.resolve()).replace("/", "-")
        proj = tmp_path / "projects" / slug
        proj.mkdir(parents=True)
        old = proj / "old.jsonl"
        old.write_text("{}\n")

        monkeypatch.setattr(
            "loghop.transcripts._claude._claude_projects_root", lambda: tmp_path / "projects"
        )
        future = datetime.fromtimestamp(old.stat().st_mtime + 10, tz=UTC)
        result = ClaudeTranscriptReader().find_latest(tmp_path, future)
        assert result is None

    def test_returns_most_recent_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import time

        from loghop.transcripts._claude import ClaudeTranscriptReader

        slug = str(tmp_path.resolve()).replace("/", "-")
        proj = tmp_path / "projects" / slug
        proj.mkdir(parents=True)
        f1 = proj / "a.jsonl"
        f1.write_text("{}\n")
        time.sleep(0.01)
        f2 = proj / "b.jsonl"
        f2.write_text("{}\n")

        monkeypatch.setattr(
            "loghop.transcripts._claude._claude_projects_root", lambda: tmp_path / "projects"
        )
        since = datetime.fromtimestamp(f1.stat().st_mtime - 1, tz=UTC)
        result = ClaudeTranscriptReader().find_latest(tmp_path, since)
        assert result == f2


# ---------------------------------------------------------------------------
# CodexTranscriptReader
# ---------------------------------------------------------------------------


class TestCodexTranscriptReaderParse:
    def _make_codex_response(
        self, role: str, text: str, ts: str = "2026-01-01T00:00:00Z"
    ) -> dict[str, Any]:
        return {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": role,
                "content": [{"type": "output_text", "text": text}],
            },
            "timestamp": ts,
        }

    def test_skips_empty_lines(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import CodexTranscriptReader

        p = tmp_path / "r.jsonl"
        p.write_text("\n\n" + json.dumps(self._make_codex_response("assistant", "hi")) + "\n")
        turns = list(CodexTranscriptReader().parse(p))
        assert len(turns) == 1

    def test_skips_invalid_json(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import CodexTranscriptReader

        p = tmp_path / "r.jsonl"
        p.write_text("bad\n" + json.dumps(self._make_codex_response("assistant", "ok")) + "\n")
        turns = list(CodexTranscriptReader().parse(p))
        assert len(turns) == 1

    def test_handles_oserror(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import CodexTranscriptReader

        turns = list(CodexTranscriptReader().parse(tmp_path / "missing.jsonl"))
        assert turns == []

    def test_skips_non_dict_entry(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import CodexTranscriptReader

        p = tmp_path / "r.jsonl"
        p.write_text(json.dumps(["list"]) + "\n")
        turns = list(CodexTranscriptReader().parse(p))
        assert turns == []

    def test_skips_non_response_item_type(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import CodexTranscriptReader

        p = tmp_path / "r.jsonl"
        p.write_text(json.dumps({"type": "session_meta", "payload": {}}) + "\n")
        turns = list(CodexTranscriptReader().parse(p))
        assert turns == []

    def test_skips_when_payload_not_message_type(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import CodexTranscriptReader

        p = tmp_path / "r.jsonl"
        entry = {
            "type": "response_item",
            "payload": {"type": "other", "role": "assistant"},
            "timestamp": "",
        }
        p.write_text(json.dumps(entry) + "\n")
        turns = list(CodexTranscriptReader().parse(p))
        assert turns == []

    def test_skips_when_role_unknown(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import CodexTranscriptReader

        p = tmp_path / "r.jsonl"
        entry = {
            "type": "response_item",
            "payload": {"type": "message", "role": "tool"},
            "timestamp": "",
        }
        p.write_text(json.dumps(entry) + "\n")
        turns = list(CodexTranscriptReader().parse(p))
        assert turns == []

    def test_skips_when_payload_not_dict(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import CodexTranscriptReader

        p = tmp_path / "r.jsonl"
        entry = {"type": "response_item", "payload": "string", "timestamp": ""}
        p.write_text(json.dumps(entry) + "\n")
        turns = list(CodexTranscriptReader().parse(p))
        assert turns == []


class TestExtractTextCodex:
    def _extract(self, content: object) -> str:
        from loghop.transcripts._codex import _extract_text

        return _extract_text(content)

    def test_none_returns_empty(self) -> None:
        assert self._extract(None) == ""

    def test_string_content_returned_as_is(self) -> None:
        assert self._extract("direct") == "direct"

    def test_non_list_non_string_returns_empty(self) -> None:
        assert self._extract({"type": "text"}) == ""

    def test_string_blocks_in_list(self) -> None:
        assert self._extract(["hello", "world"]) == "hello\nworld"

    def test_non_dict_block_skipped(self) -> None:
        assert self._extract([99, {"type": "output_text", "text": "ok"}]) == "ok"

    def test_input_text_block(self) -> None:
        assert self._extract([{"type": "input_text", "text": "question"}]) == "question"

    def test_output_text_block(self) -> None:
        assert self._extract([{"type": "output_text", "text": "answer"}]) == "answer"

    def test_text_block(self) -> None:
        assert self._extract([{"type": "text", "text": "body"}]) == "body"

    def test_unknown_block_type_skipped(self) -> None:
        assert self._extract([{"type": "image", "data": "x"}]) == ""

    def test_block_with_non_string_text_skipped(self) -> None:
        assert self._extract([{"type": "output_text", "text": None}]) == ""


class TestMatchesCwd:
    def test_returns_true_when_cwd_matches(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import _matches_cwd

        cwd_str = str(tmp_path.resolve())
        p = tmp_path / "rollout.jsonl"
        p.write_text(json.dumps({"type": "session_meta", "payload": {"cwd": cwd_str}}) + "\n")
        assert _matches_cwd(p, cwd_str) is True

    def test_returns_false_when_cwd_differs(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import _matches_cwd

        p = tmp_path / "rollout.jsonl"
        p.write_text(json.dumps({"type": "session_meta", "payload": {"cwd": "/other/path"}}) + "\n")
        assert _matches_cwd(p, "/some/path") is False

    def test_returns_false_on_oserror(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import _matches_cwd

        assert _matches_cwd(tmp_path / "missing.jsonl", "/any") is False

    def test_skips_malformed_json_lines(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import _matches_cwd

        cwd_str = str(tmp_path.resolve())
        p = tmp_path / "rollout.jsonl"
        p.write_text(
            "bad-json\n" + json.dumps({"type": "session_meta", "payload": {"cwd": cwd_str}}) + "\n"
        )
        assert _matches_cwd(p, cwd_str) is True

    def test_returns_false_when_no_session_meta(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import _matches_cwd

        p = tmp_path / "rollout.jsonl"
        p.write_text(json.dumps({"type": "event", "payload": {}}) + "\n")
        assert _matches_cwd(p, "/any") is False

    def test_returns_false_at_scan_limit(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import _MATCH_CWD_SCAN_LIMIT, _matches_cwd

        p = tmp_path / "rollout.jsonl"
        lines = [json.dumps({"type": "event"}) for _ in range(_MATCH_CWD_SCAN_LIMIT + 5)]
        p.write_text("\n".join(lines) + "\n")
        assert _matches_cwd(p, "/any") is False

    def test_documents_session_meta_after_scan_limit_is_rejected(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import _MATCH_CWD_SCAN_LIMIT, _matches_cwd

        cwd_str = str(tmp_path.resolve())
        p = tmp_path / "rollout.jsonl"
        prefix = [json.dumps({"type": "event"}) for _ in range(_MATCH_CWD_SCAN_LIMIT)]
        session_meta = json.dumps({"type": "session_meta", "payload": {"cwd": cwd_str}})
        p.write_text("\n".join([*prefix, session_meta]) + "\n")

        assert _matches_cwd(p, cwd_str) is False
