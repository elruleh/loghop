from __future__ import annotations

from datetime import UTC, datetime

import loghop.store._constants as constants


def test_utc_now_clamps_backwards_skew_without_future_drift(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        constants,
        "_LAST_UTC_NOW",
        datetime(2026, 6, 19, 12, 0, 10, tzinfo=UTC),
    )

    class _FakeDateTime:
        @staticmethod
        def now(*, tz):
            assert tz == UTC
            return datetime(2026, 6, 19, 12, 0, 5, 123456, tzinfo=UTC)

    monkeypatch.setattr(constants, "datetime", _FakeDateTime)

    assert constants.utc_now() == "2026-06-19T12:00:10Z"
