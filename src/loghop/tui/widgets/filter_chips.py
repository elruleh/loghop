"""Filter-chip strip with clickable × markers.

Each chip is its own widget that posts a ``ChipDismissed`` message when
clicked, so the parent screen can drop the right filter.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Static

from loghop.tui.i18n import tr


class ChipDismissed(Message):
    """Posted when the user clicks a chip's × marker."""

    def __init__(self, key: str) -> None:
        super().__init__()
        self.key = key


class _Chip(Static):
    BINDINGS = [  # noqa: RUF012
        Binding("enter", "dismiss", "Dismiss", show=False),
        Binding("space", "dismiss", "Dismiss", show=False),
        Binding("delete", "dismiss", "Dismiss", show=False),
        Binding("backspace", "dismiss", "Dismiss", show=False),
    ]

    def __init__(self, label: str, key: str) -> None:
        super().__init__(f"[reverse] {label} [/]")
        self._key = key
        self.can_focus = True
        self.add_class("filter-chip")

    def on_click(self) -> None:
        self.action_dismiss()

    def action_dismiss(self) -> None:
        self.post_message(ChipDismissed(self._key))


class FilterChips(Horizontal):
    """Horizontal strip of clickable filter chips + result counter."""

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.add_class("filter-chips")
        self._chips: list[tuple[str, str]] = []
        self._count: tuple[int, int] | None = None

    def compose(self) -> ComposeResult:
        for label, key in self._chips:
            yield _Chip(label, key)
        if self._count is not None:
            shown, total = self._count
            text = f"{total}" if shown == total else tr("FILTER_COUNT", shown=shown, total=total)
            yield Static(f"[dim]{text}[/]", classes="filter-count")

    def set_chips(self, chips: list[tuple[str, str]]) -> None:
        self._chips = chips
        self.refresh(recompose=True)

    def set_count(self, shown: int, total: int) -> None:
        self._count = (shown, total)
        self.refresh(recompose=True)

    def clear_count(self) -> None:
        self._count = None
        self.refresh(recompose=True)
