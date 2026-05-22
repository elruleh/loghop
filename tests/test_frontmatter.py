from __future__ import annotations

import json
from pathlib import Path

import pytest

from loghop.store._frontmatter import (
    meta_to_dataclass,
    parse_frontmatter_text,
    parse_metadata_lines,
    rewrite_frontmatter,
)
from loghop.store._models import HandoffMeta, SessionMeta


class TestParseMetadataLines:
    def test_json_object(self) -> None:
        lines = ['{"id": "H-001", "provider": "codex"}']
        result = parse_metadata_lines(lines)
        assert result == {"id": "H-001", "provider": "codex"}

    def test_json_invalid_returns_empty(self) -> None:
        lines = ["{invalid json"]
        assert parse_metadata_lines(lines) == {}

    def test_json_non_dict_returns_empty(self) -> None:
        lines = ['["not", "a", "dict"]']
        assert parse_metadata_lines(lines) == {}

    def test_yaml_object(self) -> None:
        lines = ["id: H-001", "provider: codex", "status: built"]
        result = parse_metadata_lines(lines)
        assert result == {"id": "H-001", "provider": "codex", "status": "built"}

    def test_yaml_invalid_returns_empty(self) -> None:
        lines = ["  : [invalid : yaml : {"]
        assert parse_metadata_lines(lines) == {}

    def test_yaml_non_dict_returns_empty(self) -> None:
        lines = ["- just", "- a", "- list"]
        assert parse_metadata_lines(lines) == {}

    def test_empty_lines_returns_empty(self) -> None:
        assert parse_metadata_lines([]) == {}

    def test_whitespace_only_returns_empty(self) -> None:
        assert parse_metadata_lines(["  ", "  "]) == {}

    def test_yaml_coerces_keys_to_str(self) -> None:
        lines = ["123: value"]
        result = parse_metadata_lines(lines)
        assert "123" in result


class TestParseFrontmatterText:
    def test_yaml_frontmatter(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text(
            "---\nid: H-001\nprovider: codex\n---\n# Body\nSome text\n",
            encoding="utf-8",
        )
        meta, body = parse_frontmatter_text(md)
        assert meta["id"] == "H-001"
        assert meta["provider"] == "codex"
        assert "# Body" in "\n".join(body)

    def test_json_frontmatter(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text(
            "---\n" + json.dumps({"id": "H-002", "status": "built"}) + "\n---\nBody here\n",
            encoding="utf-8",
        )
        meta, _body = parse_frontmatter_text(md)
        assert meta["id"] == "H-002"
        assert meta["status"] == "built"

    def test_no_frontmatter(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text("# No frontmatter\nJust body\n", encoding="utf-8")
        meta, body = parse_frontmatter_text(md)
        assert meta == {}
        assert "# No frontmatter" in "\n".join(body)

    def test_empty_file(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text("", encoding="utf-8")
        meta, body = parse_frontmatter_text(md)
        assert meta == {}
        assert body == []

    def test_only_opening_delimiter(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text("---\nid: H-001\n", encoding="utf-8")
        meta, _body = parse_frontmatter_text(md)
        assert meta == {} or "id" in meta

    def test_frontmatter_with_internal_dashes(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text(
            "---\nsummary: some -- dashed text\n---\nBody\n",
            encoding="utf-8",
        )
        meta, _body = parse_frontmatter_text(md)
        assert "summary" in meta
        assert "---" not in meta.get("summary", "")


class TestSessionMarkdownFrontmatter:
    @pytest.mark.parametrize(
        "goal",
        [
            "normal goal",
            "goal with : colon",
            "goal with --- separators",
            "goal with # hash",
            "goal with\nnewline",
            "goal with 'single' and \"double\" quotes",
            "goal with [brackets] and {braces}",
        ],
    )
    def test_session_markdown_roundtrips_special_goal_values(
        self, tmp_path: Path, goal: str
    ) -> None:
        from loghop.store._session import _render_session_markdown

        md = tmp_path / "S-998.md"
        markdown = _render_session_markdown(
            {
                "id": "S-998",
                "provider": "claude",
                "goal": goal,
                "status": "succeeded",
                "ts_start": "2026-01-01T00:00:00Z",
                "ts_end": "",
            }
        )
        md.write_text(markdown, encoding="utf-8")
        meta, _body = parse_frontmatter_text(md)
        assert meta["goal"] == goal


class TestMetaToDataclass:
    def test_filters_to_known_fields(self) -> None:
        meta = {
            "id": "H-001",
            "provider": "codex",
            "goal": "ship it",
            "unknown_key": "should be dropped",
            "another_extra": 42,
        }
        kwargs = meta_to_dataclass(meta, HandoffMeta)
        assert kwargs["id"] == "H-001"
        assert kwargs["provider"] == "codex"
        assert kwargs["goal"] == "ship it"
        assert "unknown_key" not in kwargs
        assert "another_extra" not in kwargs

    def test_missing_fields_not_included(self) -> None:
        meta = {"id": "S-001"}
        kwargs = meta_to_dataclass(meta, SessionMeta)
        assert "id" in kwargs
        assert "provider" not in kwargs

    def test_empty_meta_returns_empty(self) -> None:
        kwargs = meta_to_dataclass({}, HandoffMeta)
        assert kwargs == {}

    def test_all_fields_present(self) -> None:
        meta = {
            "id": "S-001",
            "provider": "claude",
            "goal": "test",
            "handoff_id": "",
            "status": "running",
            "decisions": ["d1"],
            "todos_pending": ["t1"],
            "todos_done": [],
            "files_changed": ["f1"],
            "summary": "ok",
            "ts_start": "2025-01-01",
            "ts_end": "",
            "path": "",
            "output": "",
            "returncode": None,
            "transcript_path": "",
            "claude_session_id": "",
            "turns_captured": None,
        }
        kwargs = meta_to_dataclass(meta, SessionMeta)
        assert len(kwargs) == len(meta)


class TestRewriteFrontmatter:
    def test_updates_valid_frontmatter_and_preserves_body(self, tmp_path: Path) -> None:
        subdir = tmp_path / ".loghop" / "sessions"
        subdir.mkdir(parents=True, exist_ok=True)
        md = subdir / "test.md"
        md.write_text("---\nid: H-001\nstatus: built\n---\n# Body\nKeep me\n", encoding="utf-8")

        meta = rewrite_frontmatter(md, {"status": "launched"})

        assert meta["status"] == "launched"
        text = md.read_text(encoding="utf-8")
        assert "# Body\nKeep me" in text
        assert "status: launched" in text
        # Integrity signature is embedded for .loghop artifacts.
        assert "_signature:" in text

    def test_rejects_malformed_frontmatter_without_rewriting_body(self, tmp_path: Path) -> None:
        subdir = tmp_path / ".loghop" / "sessions"
        subdir.mkdir(parents=True, exist_ok=True)
        md = subdir / "test.md"
        original = "---\nid: [oops\n---\n# Body\nKeep me\n"
        md.write_text(original, encoding="utf-8")

        with pytest.raises(ValueError, match="malformed frontmatter"):
            rewrite_frontmatter(md, {"status": "launched"})

        assert md.read_text(encoding="utf-8") == original

    def test_rejects_unterminated_frontmatter_without_truncating_body(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        original = "---\nid: H-001\n# Body\nKeep me\n"
        md.write_text(original, encoding="utf-8")

        with pytest.raises(ValueError, match="unterminated frontmatter"):
            rewrite_frontmatter(md, {"status": "launched"})

        assert md.read_text(encoding="utf-8") == original
