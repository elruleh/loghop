"""Edge-case tests for the redaction pipeline.

These tests focus on the small-but-tricky cases that simple substring
matching misses: short tokens (must NOT match), real-shaped tokens (must
match), pattern precedence, and idempotence.
"""

from __future__ import annotations

import pytest

from loghop.redact import redact_text


@pytest.mark.parametrize(
    "text,should_be_redacted",
    [
        # Short slack/web tokens are too short to be real -- must NOT match.
        ("xoxa-", False),
        ("xoxa-12", False),
        ("xoxb-1234567", False),
        # 8+ chars after the prefix -- MUST match.
        ("xoxb-12345678", True),
        ("xoxp-1234567890-abcdef", True),
        # OpenAI modern formats.
        ("sk-proj-12345678901234567890", True),
        ("sk-svcacct-1234567890ABCDEFGHIJ", True),
        # Anthropic.
        ("sk-ant-api01-1234567890abcdef12345678", True),
        # GitHub.
        ("ghp_abcdefghijklmnopqrstuvwxyz0123456789", True),
        ("github_pat_11ABCDEFG0_aBcDeFgHiJkLmNoPqRsTuVwXyZ", True),
        # GitLab.
        ("glpat-AbCdEfGhIjKlMnOpQrStUv", True),
        # Slack webhook URL.
        (
            "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX",
            True,
        ),
        # Discord webhook.
        (
            "https://discord.com/api/webhooks/123456789012345678/aBcDeFgHiJkLmNoPqRsTuVwXyZ",
            True,
        ),
        # URL with embedded credentials.
        ("https://user:pass@host.example.com/path", True),
        # AWS access key.
        ("AKIAIOSFODNN7EXAMPLE", True),
        # JWT (header.payload.signature).
        (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
            True,
        ),
        # Bearer / Basic / Token auth.
        ("Bearer abcdefghijklmnopqrstuvwxyz0123456789-_=+/.", True),
        ("Basic dXNlcjpwYXNz", True),
        ("Token abcdef1234567890", True),
        # private key block.
        (
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA....\n-----END RSA PRIVATE KEY-----",
            True,
        ),
    ],
)
def test_redaction_recognises_realistic_secrets(text: str, should_be_redacted: bool) -> None:
    out = redact_text(text)
    if should_be_redacted:
        assert text not in out, f"expected to redact {text!r}, got {out!r}"
        assert "[redacted" in out, f"expected a [redacted…] marker, got {out!r}"
    else:
        assert out == text, f"expected to keep {text!r}, got {out!r}"


def test_redaction_is_idempotent() -> None:
    """Running redaction twice on the same text must not change the result."""
    text = "Bearer sk-ant-api01-1234567890abcdef12345678"
    once = redact_text(text)
    twice = redact_text(once)
    assert once == twice


def test_redaction_handles_empty_and_none() -> None:
    assert redact_text("") == ""
    assert redact_text(None) == ""


def test_redaction_preserves_safe_text() -> None:
    safe = "Hello world. Today is 2026-06-09. My repo is /home/user/project."
    assert redact_text(safe) == safe


def test_redaction_does_not_double_redact() -> None:
    """Already-redacted text must not be re-redacted (no nested markers)."""
    already = "[redacted anthropic api key]"
    out = redact_text(already)
    assert out == already


def test_slack_token_min_length_protects_against_substring() -> None:
    """The slack min-length guard prevents over-redacting short placeholders.

    Before the guard, ``xoxa-`` (4 chars after prefix) would match because
    the regex ``\\w+`` accepts any length. With the ``{8,}`` minimum, the
    literal placeholder survives.
    """
    assert "xoxa-" in redact_text("the placeholder is xoxa-")
    assert "xoxb-12" in redact_text("marker: xoxb-12")
