from __future__ import annotations

import subprocess
from pathlib import Path

from loghop.gittools import GitRepo, GitSnapshot
from loghop.store._constants import ProjectPaths, project_paths
from loghop.store._models import ProjectConfig, SessionMeta
from loghop.store._render import (
    build_context_packet,
    build_resume_packet,
    render_handoff_markdown,
    render_memory,
    render_resume_handoff_markdown,
)


def _git_init_with_commit(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=root, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)
    (root / "a.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True, capture_output=True)


def _make_paths(root: Path) -> ProjectPaths:
    return project_paths(root)


def _make_config(**overrides: object) -> ProjectConfig:
    defaults = {
        "version": 1,
        "project_name": "test",
        "goal": "ship it",
        "handoff_counter": 0,
        "session_counter": 0,
        "handoff_patch_lines": 160,
    }
    defaults.update(overrides)
    return ProjectConfig(**defaults)  # type: ignore[arg-type]


def _clean_snapshot(root: Path) -> GitSnapshot:
    return GitSnapshot(
        git_root=str(root),
        branch="main",
        head="abc1234",
        default_branch="main",
        dirty=False,
        staged=[],
        unstaged=[],
        untracked=[],
        changed_files=[],
        diff_stat="",
    )


def _repo_for_snapshot(snap: GitSnapshot) -> GitRepo:
    """Create a GitRepo whose snapshot() returns the given snap."""
    repo = GitRepo(Path(snap.git_root or "."), cache_ttl=600.0)
    # Directly stub snapshot to return the desired snap
    repo.snapshot = lambda _s=snap: _s  # type: ignore[assignment]
    repo.diff_for_files = lambda files, **kw: ""  # type: ignore[assignment]
    return repo


class TestRenderMemory:
    def test_writes_memory_file(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        paths = _make_paths(tmp_path)
        config = _make_config()
        render_memory(paths, config, repo=_repo_for_snapshot(_clean_snapshot(tmp_path)))
        assert paths.memory.exists()
        content = paths.memory.read_text(encoding="utf-8")
        assert "# Project Memory" in content
        assert "## Goal" in content
        assert "ship it" in content
        assert "## Repository" in content
        assert "Branch: main" in content

    def test_no_goal_shows_placeholder(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        paths = _make_paths(tmp_path)
        config = _make_config(goal="")
        render_memory(paths, config, repo=_repo_for_snapshot(_clean_snapshot(tmp_path)))
        content = paths.memory.read_text(encoding="utf-8")
        assert "No goal set yet" in content

    def test_dirty_snapshot(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        paths = _make_paths(tmp_path)
        config = _make_config()
        snap = GitSnapshot(
            git_root=str(tmp_path),
            branch="main",
            head="abc1234",
            default_branch="main",
            dirty=True,
            staged=[],
            unstaged=["b.txt"],
            untracked=[],
            changed_files=["b.txt"],
            diff_stat="",
        )
        render_memory(paths, config, repo=_repo_for_snapshot(snap))
        content = paths.memory.read_text(encoding="utf-8")
        assert "Dirty: yes" in content
        assert "Changed files: 1" in content

    def test_changed_files_capped_at_10(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        paths = _make_paths(tmp_path)
        config = _make_config()
        files = [f"file_{i}.txt" for i in range(15)]
        snap = GitSnapshot(
            git_root=str(tmp_path),
            branch="main",
            head="abc",
            default_branch="main",
            dirty=True,
            staged=[],
            unstaged=[],
            untracked=[],
            changed_files=files,
            diff_stat="",
        )
        render_memory(paths, config, repo=_repo_for_snapshot(snap))
        content = paths.memory.read_text(encoding="utf-8")
        assert "5 more" in content

    def test_last_session_included(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        paths = _make_paths(tmp_path)
        config = _make_config()
        from loghop.store import init_project

        init_project(tmp_path)
        from loghop.store._session import create_session, finish_session

        create_session(tmp_path, provider="codex", goal="test")
        finish_session(tmp_path, "S-001", status="succeeded", summary="all done")
        render_memory(paths, config, repo=_repo_for_snapshot(_clean_snapshot(tmp_path)))
        content = paths.memory.read_text(encoding="utf-8")
        assert "## Latest Session" in content
        assert "S-001" in content
        assert "## Recent Sessions" in content
        assert "all done" in content

    def test_redacts_secrets(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        paths = _make_paths(tmp_path)
        config = _make_config(goal="key=sk-ant-api03-secret1234567890abcdef1234567890")
        render_memory(paths, config, repo=_repo_for_snapshot(_clean_snapshot(tmp_path)))
        content = paths.memory.read_text(encoding="utf-8")
        assert "sk-ant-api03" not in content
        assert "[redacted" in content


class TestBuildContextPacket:
    def test_basic_packet_structure(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        config = _make_config()
        snap = _clean_snapshot(tmp_path)
        packet = build_context_packet(
            tmp_path, config, "codex", "ship it", repo=_repo_for_snapshot(snap)
        )
        assert packet["provider"] == "codex"
        assert packet["goal"] == "ship it"
        assert "repo_state" in packet
        assert "patch" in packet
        assert "context" in packet
        assert "project" in packet

    def test_packet_with_changed_files(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        config = _make_config()
        snap = GitSnapshot(
            git_root=str(tmp_path),
            branch="main",
            head="abc",
            default_branch="main",
            dirty=True,
            staged=["staged.py"],
            unstaged=["dirty.py"],
            untracked=["new.py"],
            changed_files=["staged.py", "dirty.py", "new.py"],
            diff_stat="",
        )
        packet = build_context_packet(
            tmp_path, config, "codex", "goal", repo=_repo_for_snapshot(snap)
        )
        assert len(packet["repo_state"]["changed_files"]) == 3
        assert packet["context"]["changed_files_total"] == 3
        assert packet["context"]["changed_files_included"] == 3

    def test_packet_project_overview(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        config = _make_config(project_name="myapp", goal="build v2")
        snap = _clean_snapshot(tmp_path)
        packet = build_context_packet(
            tmp_path, config, "codex", "goal", repo=_repo_for_snapshot(snap)
        )
        assert packet["project"]["name"] == "myapp"
        assert packet["project"]["overview"] == "build v2"

    def test_packet_includes_project_timeline(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        from loghop.store import init_project
        from loghop.store._session import create_session, finish_session

        init_project(tmp_path)
        session = create_session(tmp_path, provider="codex", goal="first")
        finish_session(tmp_path, session.id, status="succeeded", summary="first summary")
        packet = build_context_packet(
            tmp_path,
            _make_config(),
            "claude",
            "continue",
            repo=_repo_for_snapshot(_clean_snapshot(tmp_path)),
        )

        assert packet["timeline"]
        assert packet["timeline"][-1]["summary"] == "first summary"


class TestRenderHandoffMarkdown:
    def test_basic_markdown(self) -> None:
        snap = GitSnapshot(
            git_root="/fake",
            branch="main",
            head="abc",
            default_branch="main",
            dirty=False,
            staged=[],
            unstaged=[],
            untracked=[],
            changed_files=[],
            diff_stat="",
        )
        packet = {
            "provider": "codex",
            "goal": "ship auth",
            "ts": "2025-01-01T00:00:00Z",
            "context": {
                "changed_files_total": 0,
                "changed_files_included": 0,
                "changed_files_ignored": 0,
                "patch_truncated": False,
            },
            "project": {"name": "app", "overview": "build stuff"},
            "repo_state": {
                **{k: v for k, v in snap.to_dict().items() if k != "changed_files"},
                "changed_files": [],
                "staged": [],
                "unstaged": [],
                "untracked": [],
            },
            "patch": "",
        }
        md = render_handoff_markdown("H-001", packet)
        assert "# Project Handoff" in md
        assert "ship auth" in md
        assert "H-001" in md
        assert "---" in md
        assert "provider: codex" in md

    def test_timeline_markdown(self) -> None:
        packet = {
            "provider": "claude",
            "goal": "continue",
            "ts": "2025-01-01T00:00:00Z",
            "timeline": [
                {
                    "session_id": "S-001",
                    "provider": "codex",
                    "status": "succeeded",
                    "summary": "built parser",
                    "todos_pending": ["wire TUI"],
                }
            ],
            "context": {
                "changed_files_total": 0,
                "changed_files_included": 0,
                "changed_files_ignored": 0,
                "patch_truncated": False,
            },
            "project": {"name": "app", "overview": None},
            "repo_state": {
                "branch": "main",
                "head": "abc",
                "dirty": False,
                "default_branch": "main",
                "changed_files": [],
                "staged": [],
                "unstaged": [],
                "untracked": [],
            },
            "patch": "",
        }
        md = render_handoff_markdown("H-004", packet)
        assert "## Project Timeline" in md
        assert "built parser" in md
        assert "wire TUI" in md

    def test_with_patch(self) -> None:
        snap = GitSnapshot(
            git_root="/fake",
            branch="main",
            head="abc",
            default_branch="main",
            dirty=True,
            staged=[],
            unstaged=[],
            untracked=[],
            changed_files=["app.py"],
            diff_stat="",
        )
        packet = {
            "provider": "codex",
            "goal": "fix bug",
            "ts": "2025-01-01T00:00:00Z",
            "context": {
                "changed_files_total": 1,
                "changed_files_included": 1,
                "changed_files_ignored": 0,
                "patch_truncated": False,
            },
            "project": {"name": "app", "overview": None},
            "repo_state": {
                **{k: v for k, v in snap.to_dict().items() if k != "changed_files"},
                "changed_files": ["app.py"],
                "staged": [],
                "unstaged": [],
                "untracked": [],
            },
            "patch": "diff --git a/app.py\n+new line",
        }
        md = render_handoff_markdown("H-002", packet)
        assert "## Patch" in md
        assert "```diff" in md

    def test_no_changed_files_shows_message(self) -> None:
        snap = GitSnapshot(
            git_root="/fake",
            branch="main",
            head="abc",
            default_branch="main",
            dirty=False,
            staged=[],
            unstaged=[],
            untracked=[],
            changed_files=[],
            diff_stat="",
        )
        packet = {
            "provider": "codex",
            "goal": "test",
            "ts": "2025-01-01T00:00:00Z",
            "context": {
                "changed_files_total": 0,
                "changed_files_included": 0,
                "changed_files_ignored": 0,
                "patch_truncated": False,
            },
            "project": {"name": "app", "overview": None},
            "repo_state": {
                **{k: v for k, v in snap.to_dict().items() if k != "changed_files"},
                "changed_files": [],
                "staged": [],
                "unstaged": [],
                "untracked": [],
            },
            "patch": "",
        }
        md = render_handoff_markdown("H-003", packet)
        assert "No pending file changes" in md


class TestBuildResumePacket:
    def test_without_previous_session(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        config = _make_config()
        snap = _clean_snapshot(tmp_path)
        packet = build_resume_packet(
            tmp_path, config, "codex", "resume goal", repo=_repo_for_snapshot(snap)
        )
        assert packet["provider"] == "codex"
        assert "previous_session" not in packet

    def test_with_previous_session(self, tmp_path: Path) -> None:
        _git_init_with_commit(tmp_path)
        config = _make_config()
        snap = _clean_snapshot(tmp_path)
        prev = SessionMeta(
            id="S-001",
            provider="codex",
            goal="first goal",
            status="succeeded",
            summary="did stuff",
            decisions=["chose X"],
            todos_pending=["finish Y"],
            todos_done=["did Z"],
            transcript_path="transcript.jsonl",
        )
        packet = build_resume_packet(
            tmp_path,
            config,
            "claude",
            "resume goal",
            previous_session=prev,
            repo=_repo_for_snapshot(snap),
        )
        assert "previous_session" in packet
        assert packet["previous_session"]["id"] == "S-001"
        assert packet["previous_session"]["summary"] == "did stuff"
        assert packet["previous_session"]["decisions"] == ["chose X"]
        assert packet["previous_session"]["todos_pending"] == ["finish Y"]


class TestRenderResumeHandoffMarkdown:
    def test_without_previous_session(self) -> None:
        snap = GitSnapshot(
            git_root="/fake",
            branch="main",
            head="abc",
            default_branch="main",
            dirty=False,
            staged=[],
            unstaged=[],
            untracked=[],
            changed_files=[],
            diff_stat="",
        )
        packet = {
            "provider": "codex",
            "goal": "test",
            "ts": "2025-01-01T00:00:00Z",
            "context": {
                "changed_files_total": 0,
                "changed_files_included": 0,
                "changed_files_ignored": 0,
                "patch_truncated": False,
            },
            "project": {"name": "app", "overview": None},
            "repo_state": {
                **{k: v for k, v in snap.to_dict().items() if k != "changed_files"},
                "changed_files": [],
                "staged": [],
                "unstaged": [],
                "untracked": [],
            },
            "patch": "",
        }
        md = render_resume_handoff_markdown("H-001", packet)
        assert "Previous Session" not in md

    def test_with_previous_session(self) -> None:
        snap = GitSnapshot(
            git_root="/fake",
            branch="main",
            head="abc",
            default_branch="main",
            dirty=False,
            staged=[],
            unstaged=[],
            untracked=[],
            changed_files=[],
            diff_stat="",
        )
        packet = {
            "provider": "claude",
            "goal": "resume",
            "ts": "2025-01-01T00:00:00Z",
            "context": {
                "changed_files_total": 0,
                "changed_files_included": 0,
                "changed_files_ignored": 0,
                "patch_truncated": False,
            },
            "project": {"name": "app", "overview": None},
            "repo_state": {
                **{k: v for k, v in snap.to_dict().items() if k != "changed_files"},
                "changed_files": [],
                "staged": [],
                "unstaged": [],
                "untracked": [],
            },
            "patch": "",
            "previous_session": {
                "id": "S-001",
                "provider": "codex",
                "status": "succeeded",
                "summary": "completed auth",
                "decisions": ["use JWT"],
                "todos_done": ["login page"],
                "todos_pending": ["logout"],
                "last_turns": [
                    {"role": "user", "text": "hello", "ts": ""},
                    {"role": "assistant", "text": "hi there", "ts": ""},
                ],
                "transcript_path": "t.jsonl",
            },
        }
        md = render_resume_handoff_markdown("H-002", packet)
        assert "## Previous Session" in md
        assert "S-001" in md
        assert "completed auth" in md
        assert "use JWT" in md
        assert "[x] login page" in md
        assert "[ ] logout" in md
        assert "Previous Session Excerpt" in md
        assert "hello" in md
        assert "hi there" in md

    def test_long_turn_truncated(self) -> None:
        snap = GitSnapshot(
            git_root="/fake",
            branch="main",
            head="abc",
            default_branch="main",
            dirty=False,
            staged=[],
            unstaged=[],
            untracked=[],
            changed_files=[],
            diff_stat="",
        )
        long_text = "x" * 2000
        packet = {
            "provider": "claude",
            "goal": "test",
            "ts": "2025-01-01T00:00:00Z",
            "context": {
                "changed_files_total": 0,
                "changed_files_included": 0,
                "changed_files_ignored": 0,
                "patch_truncated": False,
            },
            "project": {"name": "app", "overview": None},
            "repo_state": {
                **{k: v for k, v in snap.to_dict().items() if k != "changed_files"},
                "changed_files": [],
                "staged": [],
                "unstaged": [],
                "untracked": [],
            },
            "patch": "",
            "previous_session": {
                "id": "S-001",
                "provider": "codex",
                "status": "succeeded",
                "summary": "ok",
                "decisions": [],
                "todos_done": [],
                "todos_pending": [],
                "last_turns": [
                    {"role": "assistant", "text": long_text, "ts": ""},
                ],
                "transcript_path": "",
            },
        }
        md = render_resume_handoff_markdown("H-003", packet)
        assert "…" in md
        assert long_text not in md
