from __future__ import annotations

import pytest

from loghop.gittools import _parse_v2_status


class TestParseV2StatusBasic:
    def test_clean_repo(self) -> None:
        # v2 -z uses NUL between ALL parts (headers and entries)
        raw = "# branch.oid abc1234567\x00# branch.head main\x00"
        result = _parse_v2_status(raw)
        assert result.branch == "main"
        assert result.head == "abc1234567"
        assert result.upstream is None
        assert result.entries == []

    def test_with_upstream(self) -> None:
        raw = "# branch.oid abc1234567\x00# branch.head main\x00# branch.upstream origin/main\x00"
        result = _parse_v2_status(raw)
        assert result.upstream == "origin/main"

    def test_modified_file(self) -> None:
        raw = "# branch.oid abc1234567\x00# branch.head main\x001 .M N... 100644 100644 abc def src/app.py\x00"
        result = _parse_v2_status(raw)
        assert len(result.entries) == 1
        assert result.entries[0].xy == ".M"
        assert result.entries[0].path == "src/app.py"
        assert result.entries[0].orig_path is None

    def test_staged_and_unstaged(self) -> None:
        raw = (
            "# branch.oid abc\x00# branch.head main\x001 MM N... 100644 100644 abc def file.py\x00"
        )
        result = _parse_v2_status(raw)
        assert result.entries[0].xy == "MM"

    def test_untracked(self) -> None:
        raw = "# branch.oid abc\x00# branch.head main\x00? newfile.txt\x00"
        result = _parse_v2_status(raw)
        assert len(result.entries) == 1
        assert result.entries[0].xy == "??"
        assert result.entries[0].path == "newfile.txt"

    def test_ignored(self) -> None:
        raw = "# branch.oid abc\x00# branch.head main\x00! build/\x00"
        result = _parse_v2_status(raw)
        assert len(result.entries) == 1
        assert result.entries[0].xy == "!!"
        assert result.entries[0].path == "build/"

    def test_multiple_files(self) -> None:
        raw = (
            "# branch.oid abc\x00# branch.head main\x00"
            "1 .M N... 100644 100644 a b a.py\x00"
            "1 AM N... 100644 100644 c d b.py\x00"
            "? c.py\x00"
        )
        result = _parse_v2_status(raw)
        assert len(result.entries) == 3
        assert result.entries[0].xy == ".M"
        assert result.entries[1].xy == "AM"
        assert result.entries[2].xy == "??"


class TestParseV2StatusRenames:
    def test_rename_entry(self) -> None:
        raw = "# branch.oid abc\x00# branch.head main\x002 RM N... 100644 100644 abc def new.txt\x00old.txt\x00"
        result = _parse_v2_status(raw)
        assert len(result.entries) == 1
        assert result.entries[0].xy == "RM"
        assert result.entries[0].path == "new.txt"
        assert result.entries[0].orig_path == "old.txt"

    def test_copy_entry(self) -> None:
        raw = "# branch.oid abc\x00# branch.head main\x002 C. N... 100644 100644 abc def copy.txt\x00orig.txt\x00"
        result = _parse_v2_status(raw)
        assert len(result.entries) == 1
        assert result.entries[0].xy == "C."
        assert result.entries[0].orig_path == "orig.txt"


class TestParseV2StatusDetached:
    def test_detached_head(self) -> None:
        raw = "# branch.oid abc1234567\x00# branch.head (detached)\x00"
        result = _parse_v2_status(raw)
        assert result.branch is None
        assert result.head == "abc1234567"


class TestParseV2StatusInitial:
    def test_no_commits(self) -> None:
        raw = "# branch.oid (initial)\x00# branch.head main\x00"
        result = _parse_v2_status(raw)
        assert result.head is None
        assert result.branch == "main"


class TestParseV2StatusEmpty:
    def test_empty_string(self) -> None:
        result = _parse_v2_status("")
        assert result.branch is None
        assert result.head is None
        assert result.upstream is None
        assert result.entries == []

    def test_only_null_bytes(self) -> None:
        result = _parse_v2_status("\x00\x00")
        assert result.entries == []


class TestSanitizePath:
    def test_rejects_flag_like(self) -> None:
        from loghop.gittools import _sanitize_path

        with pytest.raises(ValueError, match="flag"):
            _sanitize_path("--something")

    def test_rejects_dash_prefix(self) -> None:
        from loghop.gittools import _sanitize_path

        with pytest.raises(ValueError, match="flag"):
            _sanitize_path("-v")

    def test_rejects_empty(self) -> None:
        from loghop.gittools import _sanitize_path

        with pytest.raises(ValueError, match="invalid"):
            _sanitize_path("")

    def test_rejects_null_byte(self) -> None:
        from loghop.gittools import _sanitize_path

        with pytest.raises(ValueError, match="invalid"):
            _sanitize_path("file\x00.txt")

    def test_accepts_normal_path(self) -> None:
        from loghop.gittools import _sanitize_path

        assert _sanitize_path("src/app.py") == "src/app.py"

    def test_accepts_path_with_spaces(self) -> None:
        from loghop.gittools import _sanitize_path

        assert _sanitize_path("my file.txt") == "my file.txt"
