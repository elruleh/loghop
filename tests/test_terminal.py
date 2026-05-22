from __future__ import annotations

import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from loghop.terminal import Terminal, TerminalOptions


def _make_terminal(**kwargs: Any) -> Terminal:
    return Terminal(TerminalOptions(**kwargs))


class TestTerminal:
    def test_plain_section_stays_plain_text(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        term = _make_terminal(plain=True, stream=stdout, error_stream=stderr)

        term.section("status", (("repo", "loghop"), ("branch", "main")))

        rendered = stdout.getvalue()
        assert "status" in rendered
        assert "repo: loghop" in rendered
        assert "branch: main" in rendered
        assert stderr.getvalue() == ""

    def test_quiet_silences_stdout_but_not_errors(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        term = _make_terminal(
            plain=False,
            quiet=True,
            stream=stdout,
            error_stream=stderr,
            force_terminal=False,
            width=80,
        )

        term.success("done")
        term.error("failed")

        assert stdout.getvalue() == ""
        assert re.search(r"(✗|x) failed", stderr.getvalue()) is not None

    def test_verbose_controls_detail_output(self) -> None:
        quiet_stdout = io.StringIO()
        verbose_stdout = io.StringIO()

        _make_terminal(plain=True, verbose=False, stream=quiet_stdout).detail("hidden detail")
        _make_terminal(plain=True, verbose=True, stream=verbose_stdout).detail("visible detail")

        assert quiet_stdout.getvalue() == ""
        assert "visible detail" in verbose_stdout.getvalue()

    def test_rich_section_prints_literal_brackets(self) -> None:
        stdout = io.StringIO()
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            term = _make_terminal(
                plain=False,
                stream=stdout,
                error_stream=io.StringIO(),
                force_terminal=False,
                width=80,
            )
            term.section("handoff", (("goal", "Keep [square] brackets literal"),))

        rendered = stdout.getvalue()
        assert "handoff" in rendered
        assert "Keep [square] brackets literal" in rendered

    def test_confirm_keeps_single_read_semantics(self) -> None:
        stdout = io.StringIO()
        term_default = _make_terminal(
            plain=False,
            stream=stdout,
            error_stream=io.StringIO(),
            input_stream=io.StringIO("\n"),
            force_terminal=False,
            width=80,
        )
        assert term_default.confirm("Enable codex", default=True) is True

        term_invalid = _make_terminal(
            plain=False,
            stream=io.StringIO(),
            error_stream=io.StringIO(),
            input_stream=io.StringIO("maybe\n"),
            force_terminal=False,
            width=80,
        )
        assert term_invalid.confirm("Enable codex", default=True) is False

    def test_json_mode_emits_versioned_schema(self) -> None:
        stdout = io.StringIO()
        term = _make_terminal(plain=True, json_mode=True, stream=stdout, error_stream=io.StringIO())

        term.section("status", (("repo", "loghop"),))
        term.capture_result({"repo": "loghop"})
        term.render_json(code=0)

        payload = json.loads(stdout.getvalue())
        assert payload["schema"] == "loghop.cli.result"
        assert payload["schema_version"] == 1
        assert payload["ok"] is True
        assert payload["repo"] == "loghop"
        assert payload["events"][0]["type"] == "section"


class TestPlainRenderer:
    def _term(self, **kwargs: Any) -> Terminal:
        defaults = {"plain": True, "stream": io.StringIO(), "error_stream": io.StringIO()}
        defaults.update(kwargs)
        return _make_terminal(**defaults)

    def test_quiet_suppresses_line(self) -> None:
        stdout = io.StringIO()
        term = self._term(quiet=True, stream=stdout)
        term.line("hidden")
        assert stdout.getvalue() == ""

    def test_quiet_allows_error_line(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        term = self._term(quiet=True, stream=stdout, error_stream=stderr)
        term.line("boom", error=True)
        assert "boom" in stderr.getvalue()

    def test_section_with_string_rows(self) -> None:
        stdout = io.StringIO()
        term = self._term(stream=stdout)
        term.section("items", ["alpha", "beta"])
        rendered = stdout.getvalue()
        assert "items" in rendered
        assert "  alpha" in rendered
        assert "  beta" in rendered

    def test_quiet_suppresses_section(self) -> None:
        stdout = io.StringIO()
        term = self._term(quiet=True, stream=stdout)
        term.section("gone", (("k", "v"),))
        assert stdout.getvalue() == ""

    def test_table_with_headers(self) -> None:
        stdout = io.StringIO()
        term = self._term(stream=stdout)
        term.table([("row1", "val1")], headers=["Name", "Value"])
        rendered = stdout.getvalue()
        assert "Name" in rendered
        assert "row1" in rendered

    def test_table_with_title(self) -> None:
        stdout = io.StringIO()
        term = self._term(stream=stdout)
        term.table([("x",)], title="My Table")
        assert "My Table" in stdout.getvalue()

    def test_table_skips_empty_rows(self) -> None:
        stdout = io.StringIO()
        term = self._term(stream=stdout)
        term.table([(), ("visible",)])
        assert "visible" in stdout.getvalue()

    def test_table_single_cell(self) -> None:
        stdout = io.StringIO()
        term = self._term(stream=stdout)
        term.table([("solo",)])
        assert "solo" in stdout.getvalue()

    def test_quiet_suppresses_table(self) -> None:
        stdout = io.StringIO()
        term = self._term(quiet=True, stream=stdout)
        term.table([("x",)], headers=["H"])
        assert stdout.getvalue() == ""

    def test_confirm_default_true(self) -> None:
        term = self._term(input_stream=io.StringIO("\n"))
        assert term.confirm("ok?", default=True) is True

    def test_confirm_yes(self) -> None:
        term = self._term(input_stream=io.StringIO("y\n"))
        assert term.confirm("ok?") is True

    def test_confirm_no(self) -> None:
        term = self._term(input_stream=io.StringIO("n\n"))
        assert term.confirm("ok?") is False

    def test_confirm_default_false_on_empty(self) -> None:
        term = self._term(input_stream=io.StringIO("\n"))
        assert term.confirm("ok?", default=False) is False


class TestRichRenderer:
    def _term(self, **kwargs: Any) -> Terminal:
        defaults = {
            "plain": False,
            "stream": io.StringIO(),
            "error_stream": io.StringIO(),
            "force_terminal": False,
            "width": 80,
        }
        defaults.update(kwargs)
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            return _make_terminal(**defaults)

    def test_detail_verbose_and_not_quiet(self) -> None:
        stdout = io.StringIO()
        term = self._term(verbose=True, quiet=False, stream=stdout)
        term.detail("verbose info")
        assert "verbose info" in stdout.getvalue()

    def test_detail_quiet_suppressed(self) -> None:
        stdout = io.StringIO()
        term = self._term(verbose=True, quiet=True, stream=stdout)
        term.detail("hidden")
        assert stdout.getvalue() == ""

    def test_section_quiet_suppressed(self) -> None:
        stdout = io.StringIO()
        term = self._term(quiet=True, stream=stdout)
        term.section("gone", (("k", "v"),))
        assert stdout.getvalue() == ""

    def test_table_renders_rows(self) -> None:
        stdout = io.StringIO()
        term = self._term(stream=stdout)
        term.table([("a", "b"), ("c", "d")], headers=["H1", "H2"], title="Title")
        rendered = stdout.getvalue()
        assert "Title" in rendered
        assert "H1" in rendered

    def test_confirm_yes(self) -> None:
        term = self._term(input_stream=io.StringIO("yes\n"))
        assert term.confirm("go?") is True

    def test_confirm_no(self) -> None:
        term = self._term(input_stream=io.StringIO("no\n"))
        assert term.confirm("go?") is False

    def test_confirm_empty_uses_default_true(self) -> None:
        term = self._term(input_stream=io.StringIO("\n"))
        assert term.confirm("go?", default=True) is True

    def test_confirm_empty_uses_default_false(self) -> None:
        term = self._term(input_stream=io.StringIO("\n"))
        assert term.confirm("go?", default=False) is False

    def test_render_rows_empty(self) -> None:
        stdout = io.StringIO()
        term = self._term(stream=stdout)
        term.section("empty", [])
        assert "empty" in stdout.getvalue()

    def test_render_rows_mixed_types(self) -> None:
        stdout = io.StringIO()
        term = self._term(stream=stdout)
        term.section("mixed", [("key", "val"), "plain-string"])
        rendered = stdout.getvalue()
        assert "key" in rendered
        assert "plain-string" in rendered


class TestJsonMode:
    def _term(self, **kwargs: Any) -> Terminal:
        defaults = {
            "plain": True,
            "json_mode": True,
            "stream": io.StringIO(),
            "error_stream": io.StringIO(),
        }
        defaults.update(kwargs)
        return _make_terminal(**defaults)

    def test_line_records_event(self) -> None:
        term = self._term()
        term.line("hello")
        assert term._events[-1] == {"type": "line", "text": "hello", "error": False, "style": None}

    def test_success_records_event(self) -> None:
        term = self._term()
        term.success("done")
        assert term._events[-1] == {"type": "success", "text": "done"}

    def test_info_records_event(self) -> None:
        term = self._term()
        term.info("note")
        assert term._events[-1] == {"type": "info", "text": "note"}

    def test_warn_records_event(self) -> None:
        term = self._term()
        term.warn("careful")
        assert term._events[-1] == {"type": "warning", "text": "careful", "error": True}

    def test_error_records_event(self) -> None:
        term = self._term()
        term.error("fail")
        assert term._events[-1] == {"type": "error", "text": "fail", "error": True}

    def test_detail_records_event(self) -> None:
        term = self._term()
        term.detail("extra")
        assert term._events[-1] == {"type": "detail", "text": "extra"}

    def test_panel_records_as_section(self) -> None:
        term = self._term()
        term.panel("title", ["line1"])
        assert term._events[-1]["type"] == "section"
        assert term._events[-1]["title"] == "title"

    def test_table_records_event(self) -> None:
        term = self._term()
        term.table([("a", "b")], headers=["H1", "H2"], title="T")
        event = term._events[-1]
        assert event["type"] == "table"
        assert event["title"] == "T"
        assert event["headers"] == ["H1", "H2"]

    def test_confirm_returns_default(self) -> None:
        term = self._term()
        assert term.confirm("go?", default=True) is True
        assert term._events[-1]["type"] == "confirm"

    def test_section_normalizes_string_rows(self) -> None:
        term = self._term()
        term.section("s", ["alpha", ("key", "val")])
        rows = term._events[-1]["rows"]
        assert rows[0] == "alpha"
        assert rows[1] == {"key": "key", "value": "val"}

    def test_render_json_with_non_dict_result(self) -> None:
        stdout = io.StringIO()
        term = self._term(stream=stdout)
        term.capture_result("string_result")
        term.render_json(code=1)
        payload = json.loads(stdout.getvalue())
        assert payload["ok"] is False
        assert payload["code"] == 1
        assert payload["result"] == "string_result"
