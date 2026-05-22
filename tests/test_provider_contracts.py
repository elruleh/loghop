from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from loghop.transcripts._claude import ClaudeTranscriptReader, _slug_for_cwd
from loghop.transcripts._codex import CodexTranscriptReader


def _fixture(path: str) -> Path:
    return Path(__file__).parent / "fixtures" / "transcripts" / path


def test_claude_contract_fixture_round_trip(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    cwd.mkdir()
    target = Path.home() / ".claude" / "projects" / _slug_for_cwd(cwd) / "session.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        _fixture("claude-session.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
    )

    reader = ClaudeTranscriptReader()
    since = datetime.now(tz=UTC) - timedelta(hours=1)
    found = reader.find_latest(cwd, since)
    assert found == target

    turns = list(reader.parse(found))
    assert [turn.role for turn in turns] == ["user", "assistant"]
    assert turns[0].text == "Resume the auth work."
    assert "Decision: keep the parser strict." in turns[1].text
    assert "[tool_use: Read]" in turns[1].text


def test_codex_contract_fixture_round_trip(tmp_path: Path) -> None:
    cwd = tmp_path / "project"
    cwd.mkdir()
    target = Path.home() / ".codex" / "sessions" / "2026" / "04" / "24" / "rollout-abc.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    body = (
        _fixture("codex-rollout.jsonl")
        .read_text(encoding="utf-8")
        .replace("__CWD__", str(cwd.resolve()))
    )
    target.write_text(body, encoding="utf-8")

    reader = CodexTranscriptReader()
    since = datetime.now(tz=UTC) - timedelta(hours=1)
    found = reader.find_latest(cwd, since)
    assert found == target

    turns = list(reader.parse(found))
    assert [turn.role for turn in turns] == ["user", "assistant"]
    assert turns[0].text == "Inspect the repository."
    assert "Decision: keep the release smoke tests." in turns[1].text
    assert "[tool_result] All checks passed." in turns[1].text
