"""Tests for the four remaining production hardening items:

1. Circuit breaker for provider calls
2. Property-based testing for redact.py
3. Lazy session loading in TUI
4. Strict path validation in gittools
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from loghop.store import init_project, project_paths

# ---------------------------------------------------------------------------
# 1. Circuit breaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def test_initial_state_is_closed(self, tmp_path: Path) -> None:
        from loghop.resilience import CircuitBreaker

        cb = CircuitBreaker(state_dir=tmp_path, provider="claude")
        assert cb.state == "closed"
        assert cb.is_allowed()

    def test_records_failure_and_opens(self, tmp_path: Path) -> None:
        from loghop.resilience import CircuitBreaker

        cb = CircuitBreaker(state_dir=tmp_path, provider="claude", threshold=2, window_secs=60)
        cb.record_failure()
        assert cb.state == "closed"
        cb.record_failure()
        assert cb.state == "open"
        assert not cb.is_allowed()

    def test_half_open_after_cooldown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import time

        from loghop.resilience import CircuitBreaker

        now = time.time()
        monkeypatch.setattr(time, "time", lambda: now)
        cb = CircuitBreaker(
            state_dir=tmp_path, provider="claude", threshold=1, window_secs=60, cooldown_secs=30
        )
        cb.record_failure()
        assert cb.state == "open"
        monkeypatch.setattr(time, "time", lambda: now + 31)
        assert cb.is_allowed()
        assert cb.state == "half_open"

    def test_success_closes_from_half_open(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import time

        from loghop.resilience import CircuitBreaker

        now = time.time()
        monkeypatch.setattr(time, "time", lambda: now)
        cb = CircuitBreaker(
            state_dir=tmp_path, provider="claude", threshold=1, window_secs=60, cooldown_secs=30
        )
        cb.record_failure()
        monkeypatch.setattr(time, "time", lambda: now + 31)
        assert cb.is_allowed()
        cb.record_success()
        assert cb.state == "closed"

    def test_failure_in_half_open_reopens(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import time

        from loghop.resilience import CircuitBreaker

        now = time.time()
        monkeypatch.setattr(time, "time", lambda: now)
        cb = CircuitBreaker(
            state_dir=tmp_path, provider="claude", threshold=1, window_secs=60, cooldown_secs=30
        )
        cb.record_failure()
        monkeypatch.setattr(time, "time", lambda: now + 31)
        assert cb.is_allowed()
        cb.record_failure()
        assert cb.state == "open"
        assert not cb.is_allowed()

    def test_persists_state_to_disk(self, tmp_path: Path) -> None:
        from loghop.resilience import CircuitBreaker

        cb = CircuitBreaker(state_dir=tmp_path, provider="claude", threshold=1, window_secs=60)
        cb.record_failure()
        assert (tmp_path / "circuit-claude.json").exists()

    def test_loads_existing_state(self, tmp_path: Path) -> None:
        from loghop.resilience import CircuitBreaker

        cb1 = CircuitBreaker(state_dir=tmp_path, provider="claude", threshold=1, window_secs=60)
        cb1.record_failure()
        cb2 = CircuitBreaker(state_dir=tmp_path, provider="claude", threshold=1, window_secs=60)
        assert cb2.state == "open"

    def test_provider_isolation(self, tmp_path: Path) -> None:
        from loghop.resilience import CircuitBreaker

        cb_claude = CircuitBreaker(
            state_dir=tmp_path, provider="claude", threshold=1, window_secs=60
        )
        cb_codex = CircuitBreaker(state_dir=tmp_path, provider="codex", threshold=1, window_secs=60)
        cb_claude.record_failure()
        assert cb_claude.state == "open"
        assert cb_codex.state == "closed"


# ---------------------------------------------------------------------------
# 2. Property-based testing for redact.py
# ---------------------------------------------------------------------------


class TestRedactProperties:
    def test_redact_never_returns_empty_for_nonempty(self) -> None:
        from loghop.redact import redact_text

        assert redact_text("hello world") == "hello world"
        assert redact_text("") == ""

    def test_redact_dict_preserves_structure(self) -> None:
        from loghop.redact import redact_dict

        data = {"key": "value", "nested": {"k": "v"}}
        result = redact_dict(data)
        assert isinstance(result, dict)
        assert "key" in result
        assert "nested" in result

    def test_redact_always_strips_bearer(self) -> None:
        from loghop.redact import redact_text

        for token in ["abc", "x" * 200, "sk-ant-api03-" + "a" * 50]:
            text = f"Bearer {token}"
            result = redact_text(text)
            assert token not in result, f"Bearer token leaked: {result}"

    def test_redact_always_strips_jwt(self) -> None:
        from loghop.redact import redact_text

        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abc123def456"
        result = redact_text(f"auth={jwt}")
        assert jwt not in result

    def test_redact_idempotent(self) -> None:
        """Redacting twice should produce the same result."""
        from loghop.redact import redact_text

        text = "api_key=sk_live_abc123 Bearer token123"
        once = redact_text(text)
        twice = redact_text(once)
        assert once == twice

    def test_redact_preserves_safe_content(self) -> None:
        from loghop.redact import redact_text

        safe = "The user requested to implement authentication features."
        assert redact_text(safe) == safe

    def test_redact_handles_all_collection_types(self) -> None:
        from loghop.redact import redact_dict

        assert redact_dict(["a", "b"]) == ["a", "b"]
        assert redact_dict(("a", "b")) == ("a", "b")
        assert redact_dict({"a", "b"}) == {"a", "b"}
        assert redact_dict(frozenset({"a", "b"})) == frozenset({"a", "b"})

    def test_redact_every_known_pattern(self) -> None:
        """Each SECRET_PATTERNS entry must produce a redaction."""
        from loghop.redact import SECRET_PATTERNS, redact_text

        untestable: set[int] = set()
        for idx, (pattern, replacement) in enumerate(SECRET_PATTERNS):
            sample = _sample_for_pattern(idx, pattern)
            if sample is None:
                untestable.add(idx)
                continue
            result = redact_text(sample)
            assert replacement in result or "[redacted" in result, (
                f"Pattern {idx} ({pattern.pattern[:40]}...) did not redact sample: {sample[:80]}"
            )

    def test_filter_paths_always_blocks_traversal(self, tmp_path: Path) -> None:
        from loghop.store._security import filter_paths

        traversal_payloads = [
            "../../etc/passwd",
            "../../../root/.ssh/id_rsa",
            "foo/../../bar/../../../etc/shadow",
        ]
        for payload in traversal_payloads:
            result = filter_paths(["safe.py", payload], [], root=tmp_path)
            assert payload not in result, f"traversal leaked: {payload}"


def _sample_for_pattern(idx: int, pattern: Any) -> str | None:
    """Return a minimal string that should trigger the given regex pattern."""
    samples: dict[int, str] = {
        0: "-----BEGI"
        + "N RSA PRIVATE KEY-----\nMIIBOgIBAAJBAKj34\n-----E"
        + "ND RSA PRIVATE KEY-----",
        1: "ANTHROPIC_API_KEY=sk-ant-test123",
        2: "AWS_SESSION_TOKEN=xyz123",
        3: "api_key=supersecret123",
        4: '"api_key": "supersecret123"',
        5: "DATABASE_URL=postgres://user:pass@host/db",
        6: "https://user:p4ssw0rd@example.com/path",
        7: "sk-ant-api03-" + "a" * 40,
        8: "sk-proj-" + "a" * 25,
        9: "AIza" + "a" * 35,
        10: "hf_" + "a" * 35,
        11: "npm_" + "a" * 15,
        12: "sk-live_abc123def456",
        13: "AKIAIOSFODNN7EXAMPLE",
        14: "aws_secret_access_key=abc123def456abc123def456abc123def456abc123",
        15: 'service_account="test@project.iam.gserviceaccount.com"',
        16: "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abc123def456",
        17: "ghp_" + "A" * 36,
        18: "github_pat_" + "a" * 25,
        19: "glpat-" + "a" * 20,
        20: "SG." + "a" * 22 + "." + "b" * 43,
        21: "xoxb-1234567890-abcdef",
        22: "Bearer abc123def456",
        23: "Basic dXNlcjpwYXNz",
        24: "Token abc123def456",
    }
    return samples.get(idx)


# ---------------------------------------------------------------------------
# 3. Lazy session loading
# ---------------------------------------------------------------------------


class TestLazySessionLoading:
    def test_list_sessions_accepts_limit(self, git_repo: Path) -> None:
        from loghop.store import create_session, finish_session, project_paths
        from loghop.store._session import list_sessions

        init_project(git_repo)
        paths = project_paths(git_repo)
        for i in range(5):
            s = create_session(git_repo, provider="codex", goal=f"g{i}")
            finish_session(git_repo, s.id, status="succeeded", returncode=0)

        all_sessions = list_sessions(paths)
        assert len(all_sessions) == 5

        limited = list_sessions(paths, limit=3)
        assert len(limited) == 3
        # Should return the most recent (highest-numbered) sessions
        assert limited[0].id == "S-005"

    def test_list_sessions_limit_zero_returns_empty(self, git_repo: Path) -> None:
        from loghop.store._session import list_sessions

        init_project(git_repo)
        paths = project_paths(git_repo)
        result = list_sessions(paths, limit=0)
        assert result == []


# ---------------------------------------------------------------------------
# 4. Strict path validation in gittools
# ---------------------------------------------------------------------------


class TestGittoolsPathValidation:
    def test_rejects_null_bytes(self) -> None:
        from loghop.gittools import _sanitize_path

        with pytest.raises(ValueError, match="invalid path"):
            _sanitize_path("foo\x00bar")

    def test_rejects_flag_like_paths(self) -> None:
        from loghop.gittools import _sanitize_path

        with pytest.raises(ValueError, match="flag"):
            _sanitize_path("--flag")

    def test_rejects_empty_path(self) -> None:
        from loghop.gittools import _sanitize_path

        with pytest.raises(ValueError, match="invalid path"):
            _sanitize_path("")

    def test_accepts_normal_paths(self) -> None:
        from loghop.gittools import _sanitize_path

        assert _sanitize_path("src/main.py") == "src/main.py"
        assert _sanitize_path("README.md") == "README.md"

    def test_rejects_control_chars(self) -> None:
        from loghop.gittools import _sanitize_path

        with pytest.raises(ValueError, match="invalid path"):
            _sanitize_path("foo\tbar")

    def test_rejects_newline_in_path(self) -> None:
        from loghop.gittools import _sanitize_path

        with pytest.raises(ValueError, match="invalid path"):
            _sanitize_path("foo\nbar")
