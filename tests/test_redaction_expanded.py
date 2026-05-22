from __future__ import annotations

from loghop.store._redact import SECRET_PATTERNS, redact_dict, redact_text


class TestRedactText:
    def test_private_key_block(self) -> None:
        text = (
            "key=-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAKj34\n-----END RSA PRIVATE KEY-----"
        )
        assert "[redacted private key block]" in redact_text(text)
        assert "MIIBOgIBAAJBAKj34" not in redact_text(text)

    def test_generic_api_key_assignment(self) -> None:
        text = "api_key=sk_live_abc123def456"
        assert "[redacted]" in redact_text(text)
        assert "sk_live_abc123" not in redact_text(text)

    def test_json_style_key(self) -> None:
        text = '"api_key": "supersecret123"'
        assert "[redacted]" in redact_text(text)
        assert "supersecret123" not in redact_text(text)

    def test_database_url(self) -> None:
        text = "DATABASE_URL=postgres://user:pass@host/db"
        assert "[redacted]" in redact_text(text)
        assert "postgres://user:pass" not in redact_text(text)

    def test_credential_url(self) -> None:
        text = "https://user:p4ssw0rd@example.com/path"
        assert "[redacted credential url]" in redact_text(text)
        assert "p4ssw0rd" not in redact_text(text)

    def test_stripe_style_key(self) -> None:
        text = "found sk-abc123def456ghi789 in config"
        assert "[redacted api key]" in redact_text(text)
        assert "sk-abc123" not in redact_text(text)

    def test_aws_access_key(self) -> None:
        text = "found key AKIAIOSFODNN7EXAMPLE in config"
        assert "[redacted aws access key]" in redact_text(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in redact_text(text)

    def test_jwt_token(self) -> None:
        text = "auth=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        assert "[redacted jwt]" in redact_text(text)
        assert "eyJhbGciOiJIUzI1NiJ9" not in redact_text(text)

    def test_github_pat(self) -> None:
        text = "found ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij in log"
        assert "[redacted github token]" in redact_text(text)
        assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in redact_text(text)

    def test_github_oauth(self) -> None:
        text = "found gho_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij in log"
        assert "[redacted github token]" in redact_text(text)
        assert "gho_ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in redact_text(text)

    def test_gitlab_pat(self) -> None:
        text = "found glpat-abcdefghijklmnopqrstuvwx in log"
        assert "[redacted gitlab token]" in redact_text(text)
        assert "glpat-abcdefghijklmnopqrstuvwx" not in redact_text(text)

    def test_sendgrid_key(self) -> None:
        key = "SG." + "a" * 22 + "." + "b" * 43
        text = f"found {key} in log"
        assert "[redacted sendgrid key]" in redact_text(text)
        assert key not in redact_text(text)

    def test_bearer_token(self) -> None:
        text = "Authorization: Bearer abc123def456"
        assert "Bearer [redacted]" in redact_text(text)
        assert "abc123def456" not in redact_text(text)

    def test_basic_auth_header(self) -> None:
        text = "Authorization: Basic dXNlcjpwYXNz"
        assert "Basic [redacted]" in redact_text(text)
        assert "dXNlcjpwYXNz" not in redact_text(text)

    def test_aws_session_token(self) -> None:
        text = "AWS_SESSION_TOKEN=abc123secret456"
        assert "[redacted]" in redact_text(text)
        assert "abc123secret456" not in redact_text(text)

    def test_secret_key_base(self) -> None:
        text = "SECRET_KEY_BASE=abc123secret456"
        assert "[redacted]" in redact_text(text)
        assert "abc123secret456" not in redact_text(text)

    def test_named_provider_keys(self) -> None:
        for provider in ("ANTHROPIC", "OPENAI", "GOOGLE", "AWS", "AZURE", "STRIPE"):
            text = f"{provider}_API_KEY=sk-test-12345"
            assert "[redacted]" in redact_text(text)
            assert "sk-test-12345" not in redact_text(text)

    def test_empty_text(self) -> None:
        assert redact_text("") == ""
        assert redact_text(None) == ""

    def test_clean_text_unchanged(self) -> None:
        text = "Hello world, this is safe"
        assert redact_text(text) == text


class TestRedactDict:
    def test_redacts_string_values(self) -> None:
        data = {"key": "api_key=secret123"}
        result = redact_dict(data)
        assert "[redacted]" in result["key"]
        assert "secret123" not in result["key"]

    def test_redacts_nested_dicts(self) -> None:
        data = {"outer": {"inner": "password=mypass"}}
        result = redact_dict(data)
        assert "[redacted]" in result["outer"]["inner"]

    def test_redacts_lists(self) -> None:
        data = ["api_key=secret", "safe text"]
        result = redact_dict(data)
        assert isinstance(result, list)
        assert "[redacted]" in result[0]
        assert result[1] == "safe text"

    def test_redacts_tuples(self) -> None:
        data = ("api_key=secret", "safe")
        result = redact_dict(data)
        assert isinstance(result, tuple)
        assert "[redacted]" in result[0]

    def test_redacts_sets(self) -> None:
        data = {"api_key=secret", "safe"}
        result = redact_dict(data)
        assert isinstance(result, set)
        assert any("[redacted]" in item for item in result if isinstance(item, str))

    def test_redacts_frozensets(self) -> None:
        data = frozenset({"api_key=secret", "safe"})
        result = redact_dict(data)
        assert isinstance(result, frozenset)

    def test_redacts_dict_keys_containing_secrets(self) -> None:
        data = {"password=mypass": "value"}
        result = redact_dict(data)
        keys = list(result.keys())
        assert any("[redacted]" in str(k) for k in keys)

    def test_preserves_non_string_keys(self) -> None:
        data = {42: "api_key=secret"}
        result = redact_dict(data)
        assert 42 in result
        assert "[redacted]" in result[42]

    def test_preserves_int_values(self) -> None:
        data = {"count": 42, "ratio": 3.14}
        result = redact_dict(data)
        assert result["count"] == 42
        assert result["ratio"] == 3.14

    def test_preserves_none(self) -> None:
        assert redact_dict(None) is None

    def test_preserves_bool(self) -> None:
        assert redact_dict(True) is True

    def test_deeply_nested(self) -> None:
        data = {"a": {"b": {"c": [{"d": "Bearer secret123"}]}}}
        result = redact_dict(data)
        inner = result["a"]["b"]["c"][0]["d"]
        assert "[redacted]" in inner
        assert "secret123" not in inner


class TestSecretPatternsCount:
    def test_has_expected_patterns(self) -> None:
        assert len(SECRET_PATTERNS) >= 14


class TestModernTokenFormats:
    """Audit fix #9: redaction must catch current LLM/cloud token formats."""

    def test_anthropic_api_key(self) -> None:
        from loghop.store._redact import redact_text

        text = "key=sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCDEF go"
        out = redact_text(text)
        assert "AbCdEfGhIjKlMnOpQrSt" not in out
        assert "anthropic" in out.lower()

    def test_anthropic_admin_key(self) -> None:
        from loghop.store._redact import redact_text

        text = "ADMIN=sk-ant-admin01-ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ"
        out = redact_text(text)
        assert "ZZZZZZZZZZZZ" not in out

    def test_openai_project_token(self) -> None:
        from loghop.store._redact import redact_text

        text = "OPENAI_API_KEY=sk-proj-AbCdEfGhIjKlMnOpQrStUvWx"
        out = redact_text(text)
        assert "AbCdEfGhIjKlMnOpQr" not in out

    def test_openai_service_account_token(self) -> None:
        from loghop.store._redact import redact_text

        text = "tok=sk-svcacct-1234567890abcdefghij"
        out = redact_text(text)
        assert "1234567890abcdefghij" not in out

    def test_google_api_key(self) -> None:
        from loghop.store._redact import redact_text

        text = "MAPS_KEY=AIzaSyA-Abcdef1234567890ghijklmnopqrstuvw"
        out = redact_text(text)
        assert "AIzaSyA" not in out
        assert "google" in out.lower()

    def test_huggingface_token(self) -> None:
        from loghop.store._redact import redact_text

        text = "HF_TOKEN=hf_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
        out = redact_text(text)
        assert "AbCdEfGhIjKlMnOp" not in out

    def test_npm_token(self) -> None:
        from loghop.store._redact import redact_text

        text = "//registry.npmjs.org/:_authToken=npm_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AB"
        out = redact_text(text)
        assert "AbCdEfGhIjKl" not in out

    def test_shorter_npm_token(self) -> None:
        from loghop.store._redact import redact_text

        text = "NPM_TOKEN=npm_abc123ABC"
        out = redact_text(text)
        assert "npm_abc123ABC" not in out
        assert "npm token" in out.lower()

    def test_github_server_to_server_token(self) -> None:
        from loghop.store._redact import redact_text

        # ghs_ (server-to-server) was not covered by the old patterns; only
        # ghp_ and gho_ were. The broadened gh[posru]_ pattern should now match.
        text = "X-GitHub-Token: ghs_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        out = redact_text(text)
        assert "ghs_aaaaaaa" not in out

    def test_github_user_to_server_token(self) -> None:
        from loghop.store._redact import redact_text

        text = "tok=ghu_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        out = redact_text(text)
        assert "ghu_bbbb" not in out

    def test_slack_webhook(self) -> None:
        from loghop.store._redact import redact_text

        text = "Webhook is https://hooks.slack.com/services/T12345678/B12345678/ABCDEFGHIJKLMNOPQRSTUVWX in my config"
        out = redact_text(text)
        assert "T12345678" not in out
        assert "slack webhook" in out.lower()

    def test_discord_webhook(self) -> None:
        from loghop.store._redact import redact_text

        text = "Discord: https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz0123456789"
        out = redact_text(text)
        assert "abcdefghijklmnopqrstuvwxyz" not in out
        assert "discord webhook" in out.lower()

        # Check subdomains too
        text_canary = "Discord canary: https://canary.discord.com/api/webhooks/987654321098765432/XYZ123abc456"
        out_canary = redact_text(text_canary)
        assert "XYZ123abc456" not in out_canary
        assert "discord webhook" in out_canary.lower()

    def test_discord_token(self) -> None:
        from loghop.store._redact import redact_text

        text = "Bot token is ODc2NTQzMjEwOTg3NjU0MzIx.Y1z2a3.XyZ_123-abc456_def789-ghi012"
        out = redact_text(text)
        assert "ODc2NTQz" not in out
        assert "discord token" in out.lower()

    def test_safe_strings_unchanged(self) -> None:
        # Defense against false-positives: legitimate strings that vaguely
        # look like tokens but lack the prefix should be untouched.
        from loghop.store._redact import redact_text

        text = "Just a normal sentence with sk- prefix nope and AIzaTooShort"
        out = redact_text(text)
        # `sk- prefix` (with space) shouldn't match the api key regex.
        assert "sk- prefix" in out
        assert "AIzaTooShort" in out  # not 35 chars after AIza
