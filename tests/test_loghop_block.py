from __future__ import annotations

from loghop.transcripts import Turn, find_loghop_block
from loghop.transcripts._loghop_block import parse_loghop_block


class TestParseBlock:
    def test_full_block(self) -> None:
        text = """Some prose first.

```loghop
summary: Wired up the auth module end-to-end.
decisions:
  - Use JWT instead of opaque tokens
  - Move session storage to redis
todos_done:
  - Implement /login
  - Implement /logout
todos_pending:
  - Add MFA flow
  - Document the API
```
"""
        result = parse_loghop_block(text)
        assert result is not None
        assert result["summary"] == "Wired up the auth module end-to-end."
        assert result["decisions"] == [
            "Use JWT instead of opaque tokens",
            "Move session storage to redis",
        ]
        assert result["todos_done"] == ["Implement /login", "Implement /logout"]
        assert result["todos_pending"] == ["Add MFA flow", "Document the API"]

    def test_no_block_returns_none(self) -> None:
        assert parse_loghop_block("just prose, no block") is None
        assert parse_loghop_block("") is None

    def test_partial_block(self) -> None:
        text = """```loghop
summary: just a summary
```"""
        result = parse_loghop_block(text)
        assert result == {"summary": "just a summary"}

    def test_multiline_summary(self) -> None:
        text = """```loghop
summary: First line.
  Second line continues.
  Third line still summary.
decisions:
  - real decision
```"""
        result = parse_loghop_block(text)
        assert result is not None
        assert "First line." in str(result["summary"])
        assert "Second line continues." in str(result["summary"])
        assert "Third line still summary." in str(result["summary"])
        assert result["decisions"] == ["real decision"]

    def test_only_last_block_used(self) -> None:
        text = """```loghop
summary: stale
```

later:

```loghop
summary: fresh
```"""
        result = parse_loghop_block(text)
        assert result is not None
        assert result["summary"] == "fresh"

    def test_asterisk_bullets_supported(self) -> None:
        text = """```loghop
decisions:
  * one
  * two
```"""
        result = parse_loghop_block(text)
        assert result == {"decisions": ["one", "two"]}

    def test_unknown_key_after_summary_is_continuation(self) -> None:
        """An unknown key line encountered while parsing the summary becomes prose,
        preventing silent truncation when the LLM writes 'Note: …' or 'Error: …'."""
        text = """```loghop
summary: ok
random_key: this becomes part of summary
decisions:
  - kept
```"""
        result = parse_loghop_block(text)
        assert result is not None
        assert "random_key" not in result
        assert "ok" in str(result["summary"])
        assert "random_key: this becomes part of summary" in str(result["summary"])
        assert result["decisions"] == ["kept"]

    def test_unknown_key_outside_summary_is_ignored(self) -> None:
        """Unknown keys encountered while not in summary mode are silently dropped."""
        text = """```loghop
decisions:
  - kept
random_key: ignored
```"""
        result = parse_loghop_block(text)
        assert result is not None
        assert "random_key" not in result
        assert result["decisions"] == ["kept"]


class TestFindBlockInTurns:
    def test_picks_block_from_last_assistant(self) -> None:
        turns = [
            Turn(role="user", text="please do work", ts=""),
            Turn(role="assistant", text="working...", ts=""),
            Turn(role="user", text="finish up", ts=""),
            Turn(
                role="assistant",
                text="""All done.

```loghop
summary: final summary
```
""",
                ts="",
            ),
        ]
        result = find_loghop_block(turns)
        assert result is not None
        assert result["summary"] == "final summary"

    def test_returns_none_when_no_assistant(self) -> None:
        turns = [Turn(role="user", text="```loghop\nsummary: x\n```", ts="")]
        assert find_loghop_block(turns) is None

    def test_returns_none_when_no_block(self) -> None:
        turns = [Turn(role="assistant", text="just text", ts="")]
        assert find_loghop_block(turns) is None

    def test_finds_block_in_non_last_turn(self) -> None:
        """A loghop block emitted before a trailing ACK turn is still found."""
        turns = [
            Turn(
                role="assistant",
                text="Done.\n\n```loghop\nsummary: real summary\n```\n",
                ts="",
            ),
            Turn(role="user", text="thanks", ts=""),
            Turn(role="assistant", text="You're welcome.", ts=""),
        ]
        result = find_loghop_block(turns)
        assert result is not None
        assert result["summary"] == "real summary"
