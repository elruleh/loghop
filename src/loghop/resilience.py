"""Circuit breaker for provider auth and launch calls.

Prevents repeated attempts to contact a provider that has recently failed
consecutively. State is persisted to ``<state_dir>/circuit-<provider>.json``
so that multiple loghop invocations share the same breaker.

States:
- **closed**: normal operation, calls pass through. Failures are counted.
- **open**: threshold exceeded, calls are rejected immediately.
- **half_open**: cooldown elapsed, one probe call is allowed. Success closes
  the breaker; failure reopens it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Literal

from loghop.store._io import atomic_write_text, safe_read_text

_State = Literal["closed", "open", "half_open"]


class CircuitBreaker:
    """Simple fixed-window circuit breaker persisted to disk."""

    def __init__(
        self,
        *,
        state_dir: Path,
        provider: str,
        threshold: int = 3,
        window_secs: float = 300,
        cooldown_secs: float = 60,
    ) -> None:
        self._path = state_dir / f"circuit-{provider}.json"
        self._threshold = threshold
        self._window_secs = window_secs
        self._cooldown_secs = cooldown_secs
        self._provider = provider
        self._failures: list[float] = []
        self._state: _State = "closed"
        self._opened_at: float | None = None
        self._load()

    @property
    def state(self) -> _State:
        return self._state

    def is_allowed(self) -> bool:
        if self._state == "closed":
            return True
        if self._state == "open":
            if self._opened_at is not None and time.time() - self._opened_at >= self._cooldown_secs:
                self._state = "half_open"
                self._persist()
                return True
            return False
        # half_open: allow one probe
        return True

    def record_success(self) -> None:
        self._failures.clear()
        self._state = "closed"
        self._opened_at = None
        self._persist()

    def record_failure(self) -> None:
        now = time.time()
        self._failures = [t for t in self._failures if now - t < self._window_secs]
        self._failures.append(now)
        if self._state == "half_open" or len(self._failures) >= self._threshold:
            self._state = "open"
            self._opened_at = now
        self._persist()

    def _persist(self) -> None:
        data: dict[str, Any] = {
            "provider": self._provider,
            "state": self._state,
            "failures": self._failures,
            "opened_at": self._opened_at,
        }
        atomic_write_text(self._path, json.dumps(data) + "\n")

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = safe_read_text(self._path)
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        self._state = data.get("state", "closed")
        self._failures = data.get("failures", [])
        self._opened_at = data.get("opened_at")
        if self._state not in ("closed", "open", "half_open"):
            self._state = "closed"
