from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from conftest import init_repo

from loghop.autocapture import capture_from_transcript
from loghop.session_lifecycle import SessionContext, TranscriptOptions
from loghop.store import project_paths
from loghop.store._session import create_session


def _stage(root: Path, assistant_text: str) -> None:
    slug = str(root.resolve()).replace("/", "-")
    proj_dir = Path.home() / ".claude" / "projects" / slug
    proj_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": assistant_text}],
        },
        "timestamp": "2026-04-25T10:00:00Z",
    }
    (proj_dir / "session.jsonl").write_text(json.dumps(entry) + "\n")


def test_fast_path_uses_block_over_heuristics(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    s = create_session(root, provider="claude", goal="x")

    # The text contains BOTH a regex-friendly heuristic ("Decision: foo") AND
    # a structured block — the block must win.
    _stage(
        root,
        """Working notes: Decision: heuristic-only

```loghop
summary: precise summary from block
decisions:
  - block decision A
  - block decision B
todos_pending:
  - block todo
todos_done:
  - block done
```
""",
    )

    capture = capture_from_transcript(
        SessionContext(
            root=root,
            session_id=s.id,
            provider="claude",
            launch_ts=datetime.now(tz=UTC) - timedelta(seconds=5),
        ),
        TranscriptOptions(),
    )
    assert capture["summary"] == "precise summary from block"
    assert capture["decisions"] == ["block decision A", "block decision B"]
    assert capture["todos_pending"] == ["block todo"]
    assert capture["todos_done"] == ["block done"]


def test_falls_back_to_heuristics_when_no_block(tmp_path: Path) -> None:
    root = init_repo(tmp_path)
    s = create_session(root, provider="claude", goal="x")
    _stage(
        root,
        "Decision: ship the thing\n- [ ] write the docs\nFinal answer here.",
    )
    capture = capture_from_transcript(
        SessionContext(
            root=root,
            session_id=s.id,
            provider="claude",
            launch_ts=datetime.now(tz=UTC) - timedelta(seconds=5),
        ),
        TranscriptOptions(),
    )
    assert "ship the thing" in capture.get("decisions", [])
    assert "write the docs" in capture.get("todos_pending", [])


def test_block_wins_even_when_partial(tmp_path: Path) -> None:
    # Block has only a summary; decisions should NOT fall back to regex.
    root = init_repo(tmp_path)
    s = create_session(root, provider="claude", goal="x")
    _stage(
        root,
        """Decision: regex would catch this

```loghop
summary: only this
```
""",
    )
    capture = capture_from_transcript(
        SessionContext(
            root=root,
            session_id=s.id,
            provider="claude",
            launch_ts=datetime.now(tz=UTC) - timedelta(seconds=5),
        ),
        TranscriptOptions(),
    )
    assert capture["summary"] == "only this"
    paths = project_paths(root)
    assert (paths.sessions / f"{s.id}.transcript.jsonl").exists()
    # decisions/todos absent because block didn't include them and we don't mix.
    assert "decisions" not in capture
    assert "todos_pending" not in capture
