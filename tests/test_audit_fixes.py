"""Tests for the audit-driven fixes to the conversation capture pipeline.

Covers:
- codex tool_result extraction (parity with claude),
- broader decision/TODO regex variants,
- reconcile per-session error isolation + WARN logging,
- empty-session marker (status `<x>_empty` when 0 turns + no summary),
- defensive frontmatter parse in finish_session.
"""

from __future__ import annotations

import json
from pathlib import Path

from loghop.transcripts._base import Turn, extract_decisions, extract_todos

# ---------------------------------------------------------------------------
# 1. codex tool_result extraction
# ---------------------------------------------------------------------------


class TestCodexToolBlocks:
    def test_extract_text_includes_tool_use(self) -> None:
        from loghop.transcripts._codex import _extract_text

        content = [
            {"type": "text", "text": "running:"},
            {"type": "tool_use", "name": "shell"},
        ]
        result = _extract_text(content)
        assert "running:" in result
        assert "[tool_use: shell]" in result

    def test_extract_text_includes_tool_result_string(self) -> None:
        from loghop.transcripts._codex import _extract_text

        content = [
            {"type": "tool_result", "content": "42 lines, no errors"},
        ]
        result = _extract_text(content)
        assert "[tool_result] 42 lines, no errors" in result

    def test_extract_text_recurses_into_nested_tool_result_list(self) -> None:
        from loghop.transcripts._codex import _extract_text

        content = [
            {
                "type": "tool_result",
                "content": [{"type": "text", "text": "nested"}],
            },
        ]
        result = _extract_text(content)
        assert "[tool_result]" in result
        assert "nested" in result

    def test_unknown_block_type_skipped(self) -> None:
        from loghop.transcripts._codex import _extract_text

        # image is in known set but produces no text → still parses cleanly.
        content = [
            {"type": "text", "text": "ok"},
            {"type": "image", "data": "base64..."},
        ]
        assert _extract_text(content) == "ok"


# ---------------------------------------------------------------------------
# 2. decision / TODO regex broadening
# ---------------------------------------------------------------------------


class TestBroaderDecisionRegex:
    def test_we_decided_form(self) -> None:
        turns = [Turn(role="assistant", text="We decided to use sqlite", ts="")]
        assert "use sqlite" in extract_decisions(turns)

    def test_conclusion_form(self) -> None:
        turns = [Turn(role="assistant", text="Conclusion: ship Friday", ts="")]
        assert "ship Friday" in extract_decisions(turns)

    def test_chose_to_form(self) -> None:
        turns = [Turn(role="assistant", text="Chose to skip redis", ts="")]
        assert "skip redis" in extract_decisions(turns)

    def test_agreed_to_form(self) -> None:
        turns = [Turn(role="assistant", text="Agreed to defer auth", ts="")]
        assert "defer auth" in extract_decisions(turns)


class TestBroaderTodoRegex:
    def test_todo_with_parenthetical(self) -> None:
        turns = [Turn(role="assistant", text="TODO (later): wire up CI", ts="")]
        pending, _ = extract_todos(turns)
        assert "wire up CI" in pending

    def test_pending_prefix(self) -> None:
        turns = [Turn(role="assistant", text="Pending: review PR", ts="")]
        pending, _ = extract_todos(turns)
        assert "review PR" in pending

    def test_next_alone(self) -> None:
        turns = [Turn(role="assistant", text="Next: write docs", ts="")]
        pending, _ = extract_todos(turns)
        assert "write docs" in pending


# ---------------------------------------------------------------------------
# 3. reconcile per-session error isolation
# ---------------------------------------------------------------------------


class TestReconcileIsolation:
    def test_one_failure_does_not_block_others(self, tmp_path: Path) -> None:
        from loghop.reconcile import reconcile_running_sessions
        from loghop.store._models import SessionMeta

        # Build a stranded session list where the first session id is invalid
        # so reconcile_session raises, and verify the loop continues.
        called: list[str] = []

        def fake_find(_root: Path, **_kwargs: object) -> list[SessionMeta]:
            return [
                SessionMeta(id="bogus-id", provider="claude", status="running"),
                SessionMeta(id="S-001", provider="claude", status="running"),
            ]

        def fake_reconcile(_root: Path, session: SessionMeta) -> dict[str, object]:
            called.append(str(session.id))
            if session.id == "bogus-id":
                raise ValueError("intentional")
            return {"id": session.id, "status": "interrupted"}

        from contextlib import ExitStack

        import pytest

        import loghop.reconcile as rec

        with ExitStack() as stack:
            mp = stack.enter_context(pytest.MonkeyPatch.context())
            mp.setattr(rec, "find_running_sessions", fake_find)
            mp.setattr(rec, "reconcile_session", fake_reconcile)
            reports = reconcile_running_sessions(tmp_path)

        # Both sessions were attempted; first failed, second succeeded.
        assert len(reports) == 2
        assert reports[0]["status"] == "reconcile_error"
        assert "intentional" in reports[0]["error"]
        assert reports[1]["status"] == "interrupted"
        assert called == ["bogus-id", "S-001"]


# ---------------------------------------------------------------------------
# 4. empty-session marker
# ---------------------------------------------------------------------------


class TestEmptySessionMarker:
    def _seed_session(self, root: Path) -> None:
        """Create a minimal initialized project with a single running session."""
        import subprocess

        from loghop.store import init_project
        from loghop.store._session import create_session

        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "a@b"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "x"], cwd=root, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)
        (root / "x").write_text("x")
        subprocess.run(["git", "add", "x"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "i"], cwd=root, check=True, capture_output=True)
        init_project(root)
        create_session(root, provider="claude", goal="t")

    def test_zero_turns_no_summary_marks_empty(self, tmp_path: Path) -> None:
        from loghop.store import project_paths
        from loghop.store._session import finish_session, list_sessions

        repo = tmp_path / "repo"
        repo.mkdir()
        self._seed_session(repo)
        sid = list_sessions(project_paths(repo))[0].id

        meta = finish_session(repo, sid, status="ended", turns_captured=0)
        assert meta.status == "ended_empty"

    def test_zero_turns_with_summary_keeps_status(self, tmp_path: Path) -> None:
        from loghop.store import project_paths
        from loghop.store._session import finish_session, list_sessions

        repo = tmp_path / "repo"
        repo.mkdir()
        self._seed_session(repo)
        sid = list_sessions(project_paths(repo))[0].id

        meta = finish_session(repo, sid, status="ended", turns_captured=0, summary="hand-written")
        # User-supplied summary keeps the session out of `_empty` quarantine.
        assert meta.status == "ended"


# ---------------------------------------------------------------------------
# 5. codex rollout rejection logging
# ---------------------------------------------------------------------------


class TestCodexRollout:
    def test_matches_cwd_returns_true_on_match(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import _matches_cwd

        path = tmp_path / "rollout-1.jsonl"
        path.write_text(
            json.dumps({"type": "session_meta", "payload": {"cwd": str(tmp_path)}}) + "\n",
            encoding="utf-8",
        )
        assert _matches_cwd(path, str(tmp_path)) is True

    def test_matches_cwd_returns_false_on_cwd_mismatch(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import _matches_cwd

        path = tmp_path / "rollout-1.jsonl"
        path.write_text(
            json.dumps({"type": "session_meta", "payload": {"cwd": "/other"}}) + "\n",
            encoding="utf-8",
        )
        assert _matches_cwd(path, str(tmp_path)) is False

    def test_matches_cwd_returns_false_when_meta_past_scan_limit(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import _MATCH_CWD_SCAN_LIMIT, _matches_cwd

        path = tmp_path / "rollout-1.jsonl"
        # Pad with non-meta entries past the scan limit, then put session_meta.
        lines = [json.dumps({"type": "event", "i": i}) for i in range(_MATCH_CWD_SCAN_LIMIT + 5)]
        lines.append(json.dumps({"type": "session_meta", "payload": {"cwd": str(tmp_path)}}))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert _matches_cwd(path, str(tmp_path)) is False
