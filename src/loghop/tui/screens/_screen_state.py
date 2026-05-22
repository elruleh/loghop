from __future__ import annotations

from dataclasses import dataclass

SPINNER_DELAY_SECONDS = 0.2


@dataclass(frozen=True)
class ChromeMeta:
    shown: int
    total: int
    query: str = ""
    flags: set[str] | None = None
    sort_label: str = ""

    @property
    def is_filtered(self) -> bool:
        return bool(self.query or self.flags)

    @property
    def flag_labels(self) -> list[str]:
        return format_flags(self.flags or set())


def is_stale_generation(*, current: int, incoming: int) -> bool:
    return incoming != current


def should_show_loading_spinner(*, current: int, incoming: int, elapsed_seconds: float) -> bool:
    if is_stale_generation(current=current, incoming=incoming):
        return False
    return elapsed_seconds >= SPINNER_DELAY_SECONDS


def format_flags(flags: set[str]) -> list[str]:
    return [f"!{flag}" for flag in sorted(flags)]
