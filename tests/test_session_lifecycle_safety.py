"""Regression tests for session lifecycle leak fixes.

Cover the scenarios identified in the session-state audit:
- Fuga A: an exception raised between create_session and the protected
  subprocess.run call must NOT leave an orphan "running" session.
- SIGTERM handler: a SIGTERM during a wrapped provider must close the
  session cleanly via the KeyboardInterrupt path.
"""

from __future__ import annotations

import argparse
import os
import signal
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import init_repo

from loghop.cli_commands.wrap import handle_wrap
from loghop.store import project_paths
from loghop.store._session import find_session


def _install_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str = "claude"
) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    script = bin_dir / name
    script.write_text("#!/usr/bin/env bash\nsleep 60\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    return script


class TestFugaAExceptionBeforeSubprocess:
    """If anything between create_session and subprocess.run raises, the
    session must be finalized (no orphan "running" record)."""

    def test_term_info_raising_does_not_leak_session(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = init_repo(tmp_path)
        _install_provider(tmp_path, monkeypatch)
        monkeypatch.chdir(root)

        class _BoomTerm:
            json_mode = False

            def info(self, *_a: object, **_kw: object) -> None:
                raise RuntimeError("boom")

            def detail(self, *_a: object, **_kw: object) -> None:
                pass

            def line(self, *_a: object, **_kw: object) -> None:
                pass

        args = argparse.Namespace(provider="claude", passthrough=[])
        with pytest.raises(RuntimeError, match="boom"):
            handle_wrap(args, _BoomTerm())  # type: ignore[arg-type]

        # The session file exists and must NOT be in "running" state.
        sessions_dir = project_paths(root).sessions
        files = sorted(sessions_dir.glob("S-*.md"))
        assert len(files) == 1
        meta = find_session(project_paths(root), files[0].stem)
        assert meta.status != "running", (
            f"orphan session left running after pre-subprocess exception: {meta}"
        )
        assert meta.ts_end  # was finalized

    def test_launch_oserror_keeps_launch_failed_status(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = init_repo(tmp_path)
        _install_provider(tmp_path, monkeypatch)
        monkeypatch.chdir(root)

        class _Term:
            json_mode = False

            def info(self, *_a: object, **_kw: object) -> None:
                pass

            def detail(self, *_a: object, **_kw: object) -> None:
                pass

        args = argparse.Namespace(provider="claude", passthrough=[])
        with (
            patch("loghop.cli_commands.wrap.find_project_root", return_value=root),
            patch("loghop.cli_commands.wrap.subprocess.run", side_effect=OSError("boom")),
            pytest.raises(Exception, match="failed to launch provider"),
        ):
            handle_wrap(args, _Term())  # type: ignore[arg-type]

        files = sorted(project_paths(root).sessions.glob("S-*.md"))
        assert len(files) == 1
        meta = find_session(project_paths(root), files[0].stem)
        assert meta.status == "launch_failed"


class TestCodexMatchCwdTolerance:
    """Audit fix #2: a corrupted JSON line before session_meta must not
    cause the entire rollout file to be rejected."""

    def test_malformed_line_before_meta_is_skipped(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import _matches_cwd

        rollout = tmp_path / "rollout-x.jsonl"
        cwd = "/path/to/project"
        rollout.write_text(
            "this is not json\n"
            '{"type": "noise", "payload": {}}\n'
            f'{{"type": "session_meta", "payload": {{"cwd": "{cwd}"}}}}\n'
        )
        assert _matches_cwd(rollout, cwd) is True

    def test_no_meta_within_scan_limit_returns_false(self, tmp_path: Path) -> None:
        from loghop.transcripts._codex import _matches_cwd

        rollout = tmp_path / "rollout-x.jsonl"
        # 64 noise lines, far beyond the 32-line scan limit, never reach meta.
        rollout.write_text("\n".join('{"type": "noise"}' for _ in range(64)) + "\n")
        assert _matches_cwd(rollout, "/anything") is False


class TestFilesChangedRedaction:
    """Audit fix #3: file paths in `files_changed` must be redacted before
    being persisted to session frontmatter."""

    def test_secret_in_path_is_redacted(self, tmp_path: Path) -> None:
        from loghop.store._session import create_session, finish_session

        root = init_repo(tmp_path)
        s = create_session(root, provider="claude", goal="g")
        finish_session(
            root,
            s.id,
            status="succeeded",
            files_changed=["src/main.py", "AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE"],
        )
        meta = find_session(project_paths(root), s.id)
        # files_changed survives; secret-looking entries get redacted.
        files = meta.files_changed or []
        joined = " ".join(str(f) for f in files)
        assert "AKIAIOSFODNN7EXAMPLE" not in joined
        assert "src/main.py" in joined  # non-secret unaffected


class TestSigtermInstallation:
    """The CLI installs a SIGTERM handler that translates to KeyboardInterrupt
    so existing per-command Ctrl+C cleanup paths apply."""

    def test_install_sigterm_handler_idempotent(self) -> None:
        from loghop.cli import _install_sigterm_handler

        prev = signal.getsignal(signal.SIGTERM)
        try:
            _install_sigterm_handler()
            handler = signal.getsignal(signal.SIGTERM)
            assert callable(handler)
            with pytest.raises(KeyboardInterrupt):
                handler(signal.SIGTERM, None)
        finally:
            signal.signal(signal.SIGTERM, prev)
