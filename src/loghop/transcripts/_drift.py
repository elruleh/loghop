"""Detect schema drift in provider transcripts.

Each parser declares the set of ``type`` values (and content-block subtypes,
where applicable) that it understands — both the ones that produce turns and
the ones it knowingly ignores. Anything outside that allowlist is treated as
a possible drift signal: a provider may have shipped a new schema and our
parser is silently dropping data.

Usage:

    obs = DriftObserver(provider="claude", path=path)
    for entry in stream:
        obs.observe_top(entry.get("type"))
        ...
    obs.report()  # logs once per parse, only if drift was seen

The report emits a single ``WARNING`` log record listing up to ``SAMPLE_LIMIT``
distinct unknown values (sorted, deduped) and the count of entries that
carried them. This is intentionally low-volume — operators get one line per
parse instead of a flood, with enough info to grep the upstream schema.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from loghop.logging import get_logger

_LOGGER = get_logger()


@dataclass
class DriftObserver:
    provider: str
    path: Path
    known_top_types: frozenset[str]
    known_block_types: frozenset[str] = frozenset()
    unknown_top: dict[str, int] = field(default_factory=dict)
    unknown_block: dict[str, int] = field(default_factory=dict)
    total_entries: int = 0

    def observe_top(self, kind: object) -> None:
        self.total_entries += 1
        if kind is None:
            return
        if not isinstance(kind, str):
            # Non-string `type` is itself drift.
            self.unknown_top[f"<{type(kind).__name__}>"] = (
                self.unknown_top.get(f"<{type(kind).__name__}>", 0) + 1
            )
            return
        if kind not in self.known_top_types:
            self.unknown_top[kind] = self.unknown_top.get(kind, 0) + 1

    def observe_blocks(self, kinds: Iterable[object]) -> None:
        for kind in kinds:
            if kind is None:
                continue
            if not isinstance(kind, str):
                key = f"<{type(kind).__name__}>"
                self.unknown_block[key] = self.unknown_block.get(key, 0) + 1
                continue
            if kind not in self.known_block_types:
                self.unknown_block[kind] = self.unknown_block.get(kind, 0) + 1

    def report(self) -> None:
        if not self.unknown_top and not self.unknown_block:
            return
        extra = {
            "component": "transcripts.drift",
            "provider": self.provider,
            "transcript_path": str(self.path),
            "total_entries": self.total_entries,
        }
        if self.unknown_top:
            extra["unknown_top_types"] = _summary(self.unknown_top)
        if self.unknown_block:
            extra["unknown_block_types"] = _summary(self.unknown_block)
        _LOGGER.warning("provider transcript schema drift detected", extra=extra)


def _summary(counts: dict[str, int]) -> list[str]:
    """Top-N samples by frequency, formatted as ``"name(count)"``."""
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [f"{name}({count})" for name, count in items[:8]]
