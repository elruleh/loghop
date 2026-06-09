"""Guard the TTL-bounded shell env probe cache for the Claude provider.

The shell probe is a subprocess call (``bash -c 'env -0'``) that we don't
want to spawn on every loghop invocation. The cache bounds repeated calls
to a 30-second window and is invalidated whenever the user explicitly asks
for a refresh.
"""

from __future__ import annotations

import pytest

from loghop.providers import claude


@pytest.fixture(autouse=True)
def _reset_claude_caches() -> None:
    claude.invalidate_shell_env_cache()
    yield  # noqa: PT201
    claude.invalidate_shell_env_cache()


def test_cache_returns_same_value_across_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second call within the TTL must not re-spawn the probe."""
    from subprocess import CompletedProcess

    spawns: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        spawns.append(list(cmd))
        return CompletedProcess(
            cmd,
            returncode=0,
            stdout=b"ANTHROPIC_API_KEY=sk-from-shell\x00",
            stderr=b"",
        )

    monkeypatch.setattr(claude.subprocess, "run", fake_run)
    monkeypatch.setenv("LOGHOP_DISABLE_CLAUDE_SHELL_ENV_PROBE", "0")

    env_a = claude._interactive_shell_claude_environment()
    env_b = claude._interactive_shell_claude_environment()
    assert env_a == env_b == {"ANTHROPIC_API_KEY": "sk-from-shell"}
    # Second call must hit the cache: only one subprocess spawn.
    assert len(spawns) == 1


def test_invalidate_forces_reprobe(monkeypatch: pytest.MonkeyPatch) -> None:
    """invalidate_shell_env_cache() must drop the cache and re-spawn on next call."""
    from subprocess import CompletedProcess

    counter = {"n": 0}

    def fake_run(cmd, **kwargs):
        counter["n"] += 1
        return CompletedProcess(
            cmd,
            returncode=0,
            stdout=f"ANTHROPIC_API_KEY=sk-v{counter['n']}\x00".encode(),
            stderr=b"",
        )

    monkeypatch.setattr(claude.subprocess, "run", fake_run)
    monkeypatch.setenv("LOGHOP_DISABLE_CLAUDE_SHELL_ENV_PROBE", "0")

    claude._interactive_shell_claude_environment()
    assert counter["n"] == 1
    claude.invalidate_shell_env_cache()
    claude._interactive_shell_claude_environment()
    assert counter["n"] == 2


def test_ttl_expiry_reprobes(monkeypatch: pytest.MonkeyPatch) -> None:
    """After the TTL elapses, the next call must re-spawn the probe."""
    from subprocess import CompletedProcess

    counter = {"n": 0}

    def fake_run(cmd, **kwargs):
        counter["n"] += 1
        return CompletedProcess(
            cmd,
            returncode=0,
            stdout=b"ANTHROPIC_API_KEY=sk-stable\x00",
            stderr=b"",
        )

    monkeypatch.setattr(claude.subprocess, "run", fake_run)
    monkeypatch.setenv("LOGHOP_DISABLE_CLAUDE_SHELL_ENV_PROBE", "0")
    # Make the TTL effectively zero for this test.
    monkeypatch.setattr(claude, "_CLAUDE_SHELL_ENV_CACHE_TTL_SECONDS", 0)

    claude._interactive_shell_claude_environment()
    claude._interactive_shell_claude_environment()
    assert counter["n"] >= 2


def test_probe_disabled_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """The kill switch must short-circuit and not spawn bash."""
    from subprocess import CompletedProcess

    spawns: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        spawns.append(list(cmd))
        return CompletedProcess(cmd, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(claude.subprocess, "run", fake_run)
    monkeypatch.setenv("LOGHOP_DISABLE_CLAUDE_SHELL_ENV_PROBE", "1")

    env = claude._interactive_shell_claude_environment()
    assert env == {}
    assert spawns == []
