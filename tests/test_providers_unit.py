from __future__ import annotations

import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

from loghop import providers
from loghop.errors import LoghopError


@pytest.fixture(autouse=True)
def _disable_interactive_shell_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(providers, "_interactive_shell_claude_environment", lambda: {})


@pytest.mark.parametrize(
    ("name", "interactive", "expected"),
    [
        (
            "codex",
            False,
            ["/usr/bin/codex", "exec", "--cd", "/tmp/project", "--color", "never", "goal"],
        ),
        ("codex", True, ["/usr/bin/codex", "--", "goal"]),
        ("claude", False, ["/usr/bin/claude", "--print", "goal"]),
        ("claude", True, ["/usr/bin/claude", "goal"]),
    ],
)
def test_build_launch_command_variants(
    name: str, interactive: bool, expected: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(v, raising=False)
    command = providers.build_launch_command(
        name, f"/usr/bin/{name}", "goal", Path("/tmp/project"), interactive=interactive
    )
    assert command == expected


def test_build_launch_command_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="unsupported provider"):
        providers.build_launch_command("bogus", "/usr/bin/bogus", "goal", Path("/tmp/project"))


def test_build_launch_command_rejects_relative_executable() -> None:
    with pytest.raises(ValueError, match="absolute path"):
        providers.build_launch_command("codex", "codex", "goal", Path("/tmp/project"))


def test_build_launch_command_rejects_empty_executable() -> None:
    with pytest.raises(ValueError, match="absolute path"):
        providers.build_launch_command("claude", "", "goal", Path("/tmp/project"))


def test_claude_api_key_auth_uses_bare_for_non_interactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    command = providers.build_launch_command(
        "claude", "/usr/bin/claude", "goal", Path("/tmp/project"), interactive=False
    )

    assert command == ["/usr/bin/claude", "--bare", "--print", "goal"]


def test_claude_api_key_auth_skips_bare_for_interactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    command = providers.build_launch_command(
        "claude", "/usr/bin/claude", "goal", Path("/tmp/project"), interactive=True
    )

    assert command == ["/usr/bin/claude", "goal"]


def test_claude_auth_token_uses_bare_for_non_interactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-provider-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.example.com/anthropic")

    command = providers.build_launch_command(
        "claude", "/usr/bin/claude", "goal", Path("/tmp/project"), interactive=False
    )

    assert command == ["/usr/bin/claude", "--bare", "--print", "goal"]


def test_claude_uses_api_transport_detects_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.example.com/anthropic")

    assert providers.claude_uses_api_transport(Path("/tmp/project")) is True


def test_claude_interactive_shell_auth_token_uses_bare_for_non_interactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.setattr(
        providers,
        "_interactive_shell_claude_environment",
        lambda: {
            "ANTHROPIC_AUTH_TOKEN": "sk-provider-test",
            "ANTHROPIC_BASE_URL": "https://api.example.com/anthropic",
        },
    )

    command = providers.build_launch_command(
        "claude", "/usr/bin/claude", "goal", Path("/tmp/project"), interactive=False
    )

    assert command == ["/usr/bin/claude", "--bare", "--print", "goal"]


def test_claude_base_url_without_credential_does_not_use_bare(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.example.com/anthropic")

    command = providers.build_launch_command(
        "claude", "/usr/bin/claude", "goal", Path("/tmp/project"), interactive=True
    )

    assert command == ["/usr/bin/claude", "goal"]


def test_ensure_provider_ready_accepts_claude_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    providers.ensure_provider_ready("claude", "/usr/bin/claude", Path("/tmp/project"))


def test_claude_auth_check_retries_transient_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(v, raising=False)
    calls = {"count": 0}

    def fake_run(*_args: object, **_kwargs: object) -> object:
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("temporary spawn failure")
        return subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout='{"loggedIn":true}', stderr=""
        )

    monkeypatch.setattr("loghop.providers.subprocess.run", fake_run)
    monkeypatch.setattr("loghop.providers.time.sleep", lambda _seconds: None)

    providers.ensure_provider_ready("claude", "/usr/bin/claude", Path("/tmp/project"))

    assert calls["count"] == 2


def test_ensure_provider_ready_rejects_missing_claude_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(v, raising=False)

    def fake_run(*_args: object, **_kwargs: object) -> object:
        return subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout='{"loggedIn":false}'
        )

    monkeypatch.setattr("loghop.providers.subprocess.run", fake_run)

    with pytest.raises(LoghopError, match="loggedIn: false"):
        providers.ensure_provider_ready("claude", "/usr/bin/claude", Path("/tmp/project"))


def test_ensure_provider_ready_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(v, raising=False)

    def fake_run(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd=["claude", "auth", "status"], timeout=5)

    monkeypatch.setattr("loghop.providers.subprocess.run", fake_run)

    with pytest.raises(LoghopError, match="timed out"):
        providers.ensure_provider_ready("claude", "/usr/bin/claude", Path("/tmp/project"))


def test_ensure_provider_ready_reports_non_auth_preflight_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(v, raising=False)

    def fake_run(*_args: object, **_kwargs: object) -> object:
        return subprocess.CompletedProcess(
            args=["claude"],
            returncode=2,
            stdout="",
            stderr="network socket failed",
        )

    monkeypatch.setattr("loghop.providers.subprocess.run", fake_run)

    with pytest.raises(LoghopError, match="preflight failed"):
        providers.ensure_provider_ready("claude", "/usr/bin/claude", Path("/tmp/project"))


def test_ensure_provider_ready_redacts_preflight_failure_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(v, raising=False)

    def fake_run(*_args: object, **_kwargs: object) -> object:
        return subprocess.CompletedProcess(
            args=["claude"],
            returncode=2,
            stdout="",
            stderr="Authorization: Bearer secret-token",
        )

    monkeypatch.setattr("loghop.providers.subprocess.run", fake_run)

    with pytest.raises(LoghopError) as excinfo:
        providers.ensure_provider_ready("claude", "/usr/bin/claude", Path("/tmp/project"))

    message = str(excinfo.value)
    assert "secret-token" not in message
    assert "Bearer [redacted]" in message


def test_detect_provider_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    detection = providers.detect_provider("codex")
    assert detection.name == "codex"
    assert detection.path == ""
    assert detection.installed is False


def test_detect_provider_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/codex")
    detection = providers.detect_provider("codex")
    assert detection.path == "/usr/bin/codex"
    assert detection.installed is True


def test_detect_provider_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unsupported provider"):
        providers.detect_provider("gemini")


def test_detect_all_covers_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: f"/bin/{name}")
    result = providers.detect_all()
    assert sorted(result) == sorted(providers.SUPPORTED_PROVIDER_NAMES)
    assert result["codex"].installed
    assert result["claude"].installed


def test_module_main_calls_cli_main(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    def fake_cli_main() -> None:
        called.append("called")

    monkeypatch.setattr("loghop.cli.cli_main", fake_cli_main)
    runpy.run_module("loghop.__main__", run_name="__main__")
    assert called == ["called"]


# ----- Additional coverage tests for providers.py -----


def test_interactive_shell_cache_invalidation(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    module = importlib.reload(providers)

    def first_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"ANTHROPIC_API_KEY=sk-first\0", stderr=b""
        )

    def second_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"ANTHROPIC_API_KEY=sk-second\0", stderr=b""
        )

    module.invalidate_shell_env_cache()
    monkeypatch.setattr("loghop.providers.subprocess.run", first_run)
    assert module._interactive_shell_claude_environment()["ANTHROPIC_API_KEY"] == "sk-first"

    module.invalidate_shell_env_cache()
    monkeypatch.setattr("loghop.providers.subprocess.run", second_run)
    assert module._interactive_shell_claude_environment()["ANTHROPIC_API_KEY"] == "sk-second"


def test_interactive_shell_probe_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    module = importlib.reload(providers)

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess:
        raise AssertionError("shell probe should not run")

    monkeypatch.setenv("LOGHOP_DISABLE_CLAUDE_SHELL_ENV_PROBE", "1")
    monkeypatch.setattr("loghop.providers.subprocess.run", fake_run)
    module.invalidate_shell_env_cache()

    assert module._interactive_shell_claude_environment() == {}
    module.invalidate_shell_env_cache()


def test_interactive_shell_claude_environment_handles_oserror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    module = importlib.reload(providers)

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess:
        raise OSError("exec format error")

    monkeypatch.setattr("loghop.providers.subprocess.run", fake_run)
    module.invalidate_shell_env_cache()
    result = module._interactive_shell_claude_environment()
    assert result == {}


def test_interactive_shell_claude_environment_handles_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    module = importlib.reload(providers)

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")

    monkeypatch.setattr("loghop.providers.subprocess.run", fake_run)
    module.invalidate_shell_env_cache()
    result = module._interactive_shell_claude_environment()
    assert result == {}


def test_claude_auth_check_logged_in_text(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(v, raising=False)

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=["claude", "auth", "status"],
            returncode=1,
            stdout="",
            stderr="You are logged in as user@example.com",
        )

    monkeypatch.setattr("loghop.providers.subprocess.run", fake_run)
    check = providers._claude_auth_check("/usr/bin/claude", Path("/tmp"))
    assert check.available is True


def test_claude_auth_check_json_logged_in_true(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(v, raising=False)

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=["claude", "auth", "status"],
            returncode=0,
            stdout='{"loggedIn": true, "user": "test@example.com"}',
            stderr="",
        )

    monkeypatch.setattr("loghop.providers.subprocess.run", fake_run)
    check = providers._claude_auth_check("/usr/bin/claude", Path("/tmp"))
    assert check.available is True


def test_claude_auth_check_json_logged_in_false(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(v, raising=False)

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=["claude", "auth", "status"],
            returncode=1,
            stdout='{"loggedIn": false}',
            stderr="",
        )

    monkeypatch.setattr("loghop.providers.subprocess.run", fake_run)
    check = providers._claude_auth_check("/usr/bin/claude", Path("/tmp"))
    assert check.available is False
    assert "loggedIn: false" in check.message


def test_read_json_object_handles_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_safe_read(_path: Path) -> str:
        return "not valid json {"

    monkeypatch.setattr("loghop.store._io.safe_read_text", fake_safe_read)
    result = providers._read_json_object(Path("/tmp/settings.json"))
    assert result == {}


def test_read_json_object_handles_non_dict_root(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_safe_read(_path: Path) -> str:
        return '"just a string"'

    monkeypatch.setattr("loghop.store._io.safe_read_text", fake_safe_read)
    result = providers._read_json_object(Path("/tmp/settings.json"))
    assert result == {}


def test_settings_claude_environment_missing_env() -> None:
    settings = {"otherKey": "value"}
    result = providers._settings_claude_environment(settings)
    assert result == {}


def test_settings_claude_environment_filters_non_strings() -> None:
    settings = {
        "env": {
            "ANTHROPIC_API_KEY": "valid-key",
            "OTHER_KEY": 123,
        }
    }
    result = providers._settings_claude_environment(settings)
    assert "ANTHROPIC_API_KEY" in result
    assert "OTHER_KEY" not in result


def test_detect_provider_codex_with_exclude_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_detect(_name: str, exclude_dir: Path | None = None) -> str:
        return "/custom/path/codex"

    monkeypatch.setattr("loghop.install._shim.detect_real_binary", fake_detect)
    monkeypatch.setattr(shutil, "which", lambda _n: None)

    detection = providers.detect_provider("codex", exclude_dir=Path("/tmp/exclude"))
    assert detection.path == "/custom/path/codex"
    assert detection.installed is True


def test_one_line_detail_truncates_long_text() -> None:
    long_text = " ".join(["word"] * 100)
    result = providers._one_line_detail(long_text)
    assert len(result) <= 220
    assert result.endswith("…")


def test_one_line_detail_preserves_short_text() -> None:
    short = "short message"
    result = providers._one_line_detail(short)
    assert result == short


def test_claude_uses_api_transport_via_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(v, raising=False)

    def fake_safe_read(_path: Path) -> str:
        return '{"apiKeyHelper": "key-helper-script"}'

    monkeypatch.setattr("loghop.store._io.safe_read_text", fake_safe_read)
    result = providers.claude_uses_api_transport(Path("/tmp/project"))
    assert result is True


def test_combined_output_both_streams() -> None:
    result = providers._combined_output("stdout text", "stderr text")
    assert "stdout text" in result
    assert "stderr text" in result


def test_looks_like_auth_failure_matches_needles() -> None:
    from loghop.errors import AUTH_FAILURE_NEEDLES

    # Test that needles match
    for needle in AUTH_FAILURE_NEEDLES:
        assert providers._looks_like_auth_failure(f"text {needle} text") is True
    # Test clean output doesn't match
    assert providers._looks_like_auth_failure("clean output without issues") is False


def test_settings_enable_api_transport_with_api_key_helper() -> None:
    settings = {"apiKeyHelper": "/usr/local/bin/key-helper"}
    result = providers._settings_enable_api_transport(settings)
    assert result is True


def test_settings_enable_api_transport_without_creds() -> None:
    settings = {"env": {"OTHER_VAR": "value"}}
    result = providers._settings_enable_api_transport(settings)
    assert result is False


def test_claude_auth_check_json_without_loggedin_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test JSON response without loggedIn key falls through to keyword heuristics."""
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(v, raising=False)

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=["claude", "auth", "status"],
            returncode=0,
            stdout='{"status": "ok", "version": "1.0.0"}',
            stderr="",
        )

    monkeypatch.setattr("loghop.providers.subprocess.run", fake_run)
    check = providers._claude_auth_check("/usr/bin/claude", Path("/tmp"))
    # No loggedIn key, no "logged in" text, returncode=0 -> unexpected response
    assert check.available is False
    assert "unexpected response" in check.message


def test_claude_auth_check_falls_to_unexpected_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test all fallbacks exhausted - should hit unexpected response branch."""
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(v, raising=False)

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=["claude", "auth", "status"],
            returncode=0,
            stdout='{"someKey": "someValue"}',
            stderr="",
        )

    monkeypatch.setattr("loghop.providers.subprocess.run", fake_run)
    check = providers._claude_auth_check("/usr/bin/claude", Path("/tmp"))
    # Should reach final return (unexpected response)
    assert check.available is False


def test_claude_auth_check_non_zero_exit_with_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test non-zero exit includes detail in message."""
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(v, raising=False)

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=["claude", "auth", "status"],
            returncode=3,
            stdout="",
            stderr="connection refused error code 503",
        )

    monkeypatch.setattr("loghop.providers.subprocess.run", fake_run)
    check = providers._claude_auth_check("/usr/bin/claude", Path("/tmp"))
    assert check.available is False
    assert "exit 3" in check.message
    assert "Detail:" in check.message
