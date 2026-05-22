"""Unit tests for session_lifecycle module.

Covers: finalize_session, capture_and_finalize_session,
_looks_like_provider_auth_failure, _effective_status_and_returncode.
"""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from conftest import init_repo

from loghop.session_lifecycle import (
    CaptureOptions,
    FinalizeOptions,
    SessionContext,
    capture_and_finalize_session,
    finalize_session,
)
from loghop.store._session import create_session


def _plain_term() -> object:
    term = MagicMock()
    term.json_mode = False
    return term


class TestLooksLikeProviderAuthFailure:
    """Verify _looks_like_provider_auth_failure detects auth failure needles."""

    @pytest.mark.parametrize(
        ("output", "expected"),
        [
            ("Error: not logged in", True),
            ("please run /login to continue", True),
            ("invalid api key provided", True),
            ("authentication failed for user", True),
            ("HTTP 401 unauthorized", True),
            ("all good, session complete", False),
            ("", False),
        ],
    )
    def test_output_detection(self, output: str, expected: bool) -> None:
        from loghop.session_lifecycle import _looks_like_provider_auth_failure

        assert _looks_like_provider_auth_failure("claude", {}, output) is expected

    def test_detection_in_capture_summary(self) -> None:
        from loghop.session_lifecycle import _looks_like_provider_auth_failure

        capture = {"summary": "Provider not logged in, please authenticate"}
        assert _looks_like_provider_auth_failure("claude", capture, "") is True

    def test_detection_combines_provider_name(self) -> None:
        from loghop.session_lifecycle import _looks_like_provider_auth_failure

        assert _looks_like_provider_auth_failure("not logged in", {}, "") is True

    def test_non_claude_provider_still_detected(self) -> None:
        from loghop.session_lifecycle import _looks_like_provider_auth_failure

        assert _looks_like_provider_auth_failure("codex", {}, "unauthorized") is True


class TestEffectiveStatusAndReturncode:
    """_effective_status_and_returncode should downgrade succeeded to failed on auth error."""

    def test_succeeded_stays_succeeded_when_no_auth_failure(self) -> None:
        from loghop.session_lifecycle import _effective_status_and_returncode

        status, rc = _effective_status_and_returncode(
            provider="codex",
            status="succeeded",
            returncode=0,
            capture={},
            output="all done",
        )
        assert status == "succeeded"
        assert rc == 0

    def test_succeeded_downgraded_on_auth_failure(self) -> None:
        from loghop.session_lifecycle import _effective_status_and_returncode

        status, rc = _effective_status_and_returncode(
            provider="claude",
            status="succeeded",
            returncode=0,
            capture={},
            output="Error: not logged in",
        )
        assert status == "failed"
        assert rc == 1

    def test_failed_stays_failed(self) -> None:
        from loghop.session_lifecycle import _effective_status_and_returncode

        status, rc = _effective_status_and_returncode(
            provider="claude",
            status="failed",
            returncode=1,
            capture={},
            output="not logged in",
        )
        assert status == "failed"
        assert rc == 1

    def test_auth_failure_with_nonzero_returncode_preserves_rc(self) -> None:
        from loghop.session_lifecycle import _effective_status_and_returncode

        status, rc = _effective_status_and_returncode(
            provider="claude",
            status="succeeded",
            returncode=42,
            capture={},
            output="unauthorized",
        )
        assert status == "failed"
        assert rc == 42


class TestFinalizeSession:
    """finalize_session should write session metadata and handle errors."""

    def test_finalize_with_explicit_files_changed(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="codex", goal="g")
        ctx = SessionContext(
            root=root,
            session_id=session.id,
            provider=session.provider,
            launch_ts=datetime.now(tz=UTC),
        )
        meta = finalize_session(
            ctx,
            FinalizeOptions(
                status="succeeded",
                returncode=0,
                files_changed=["a.py", "b.py"],
                component="test",
            ),
        )
        assert meta.status == "succeeded"
        assert str(meta.returncode) == "0"
        assert meta.files_changed == ["a.py", "b.py"]

    def test_finalize_with_capture_data(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="claude", goal="g")
        ctx = SessionContext(
            root=root,
            session_id=session.id,
            provider=session.provider,
            launch_ts=datetime.now(tz=UTC),
        )
        meta = finalize_session(
            ctx,
            FinalizeOptions(
                status="succeeded",
                returncode=0,
                capture={"summary": "completed", "turns_captured": 5},
                component="test",
            ),
        )
        assert meta.status == "succeeded"
        assert str(meta.returncode) == "0"

    def test_finalize_exception_reraises(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="claude", goal="g")
        ctx = SessionContext(
            root=root,
            session_id=session.id,
            provider=session.provider,
            launch_ts=datetime.now(tz=UTC),
        )

        with (
            patch(
                "loghop.session_lifecycle.finish_session",
                side_effect=OSError("disk full"),
            ),
            pytest.raises(OSError, match="disk full"),
        ):
            finalize_session(
                ctx,
                FinalizeOptions(status="failed", returncode=1),
            )


class TestCaptureAndFinalizeSession:
    """capture_and_finalize_session should handle capture errors gracefully."""

    def test_capture_failure_still_finalizes(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="codex", goal="g")
        ctx = SessionContext(
            root=root,
            session_id=session.id,
            provider=session.provider,
            launch_ts=datetime.now(tz=UTC),
        )
        with patch(
            "loghop.autocapture.capture_from_transcript",
            side_effect=RuntimeError("transcript corrupted"),
        ):
            meta, capture = capture_and_finalize_session(
                ctx,
                CaptureOptions(
                    status="succeeded",
                    returncode=0,
                ),
            )
        assert meta.status == "succeeded"
        assert capture == {}

    def test_base_exception_during_capture_still_finalizes(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="codex", goal="g")
        ctx = SessionContext(
            root=root,
            session_id=session.id,
            provider=session.provider,
            launch_ts=datetime.now(tz=UTC),
        )
        with patch(
            "loghop.autocapture.capture_from_transcript",
            side_effect=KeyboardInterrupt,
        ):
            meta, capture = capture_and_finalize_session(
                ctx,
                CaptureOptions(
                    status="interrupted",
                    returncode=130,
                ),
            )
        assert meta.status == "interrupted"
        assert capture == {}

    def test_auth_failure_downgrades_success(self, tmp_path: Path) -> None:
        root = init_repo(tmp_path)
        session = create_session(root, provider="claude", goal="g")
        ctx = SessionContext(
            root=root,
            session_id=session.id,
            provider=session.provider,
            launch_ts=datetime.now(tz=UTC),
        )
        with patch(
            "loghop.session_lifecycle.capture_from_transcript",
            return_value={"summary": "not logged in"},
        ):
            meta, capture = capture_and_finalize_session(
                ctx,
                CaptureOptions(
                    status="succeeded",
                    returncode=0,
                    output="completed",
                ),
            )
        assert meta.status == "failed"
        assert capture == {"summary": "not logged in"}
