from __future__ import annotations

from pathlib import Path

from loghop.transcripts._drift import DriftObserver


class TestDriftObserver:
    def test_no_drift_no_report(self) -> None:
        obs = DriftObserver(
            provider="claude",
            path=Path("/fake"),
            known_top_types=frozenset({"message", "summary"}),
        )
        obs.observe_top("message")
        obs.observe_top("summary")
        assert not obs.unknown_top
        obs.report()

    def test_detects_unknown_top_type(self) -> None:
        obs = DriftObserver(
            provider="claude",
            path=Path("/fake"),
            known_top_types=frozenset({"message", "summary"}),
        )
        obs.observe_top("message")
        obs.observe_top("new_unknown_type")
        assert obs.unknown_top == {"new_unknown_type": 1}
        assert obs.total_entries == 2

    def test_counts_multiple_unknown_types(self) -> None:
        obs = DriftObserver(
            provider="codex",
            path=Path("/fake"),
            known_top_types=frozenset({"message"}),
        )
        obs.observe_top("alpha")
        obs.observe_top("beta")
        obs.observe_top("alpha")
        obs.observe_top("gamma")
        assert obs.unknown_top == {"alpha": 2, "beta": 1, "gamma": 1}

    def test_none_kind_ignored(self) -> None:
        obs = DriftObserver(
            provider="claude",
            path=Path("/fake"),
            known_top_types=frozenset({"message"}),
        )
        obs.observe_top(None)
        assert not obs.unknown_top
        assert obs.total_entries == 1

    def test_non_string_kind_recorded_as_type_name(self) -> None:
        obs = DriftObserver(
            provider="claude",
            path=Path("/fake"),
            known_top_types=frozenset({"message"}),
        )
        obs.observe_top(42)
        assert obs.unknown_top == {"<int>": 1}

    def test_observe_blocks_unknown(self) -> None:
        obs = DriftObserver(
            provider="claude",
            path=Path("/fake"),
            known_top_types=frozenset({"message"}),
            known_block_types=frozenset({"text", "tool_use"}),
        )
        obs.observe_blocks(["text", "tool_use", "image", "image"])
        assert obs.unknown_block == {"image": 2}

    def test_observe_blocks_none_skipped(self) -> None:
        obs = DriftObserver(
            provider="claude",
            path=Path("/fake"),
            known_top_types=frozenset({"message"}),
            known_block_types=frozenset({"text"}),
        )
        obs.observe_blocks([None, "text", None])
        assert not obs.unknown_block

    def test_observe_blocks_non_string(self) -> None:
        obs = DriftObserver(
            provider="claude",
            path=Path("/fake"),
            known_top_types=frozenset({"message"}),
            known_block_types=frozenset(),
        )
        obs.observe_blocks([123])
        assert obs.unknown_block == {"<int>": 1}

    def test_report_emits_warning(self) -> None:
        import logging

        from loghop.logging import get_logger

        obs = DriftObserver(
            provider="claude",
            path=Path("/fake/transcript.jsonl"),
            known_top_types=frozenset({"message"}),
        )
        obs.observe_top("unknown_type")

        logger = get_logger()
        records: list[logging.LogRecord] = []

        class _Handler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = _Handler()
        logger.addHandler(handler)
        original_level = logger.level
        logger.setLevel(logging.WARNING)
        try:
            obs.report()
        finally:
            logger.setLevel(original_level)
            logger.removeHandler(handler)

        assert len(records) == 1
        msg = records[0].getMessage()
        assert "drift" in msg.lower()

    def test_report_no_warning_when_no_drift(self) -> None:
        import logging

        from loghop.logging import get_logger

        obs = DriftObserver(
            provider="claude",
            path=Path("/fake"),
            known_top_types=frozenset({"message"}),
        )
        obs.observe_top("message")

        logger = get_logger()
        records: list[logging.LogRecord] = []

        class _Handler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = _Handler()
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try:
            obs.report()
        finally:
            logger.removeHandler(handler)

        assert len(records) == 0

    def test_empty_observer(self) -> None:
        obs = DriftObserver(
            provider="claude",
            path=Path("/fake"),
            known_top_types=frozenset(),
        )
        assert obs.total_entries == 0
        assert not obs.unknown_top
        assert not obs.unknown_block
