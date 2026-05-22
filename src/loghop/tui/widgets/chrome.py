"""Shared top and command bars for the TUI chrome."""

import contextlib

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from loghop.tui.widgets import glyph

_Action = tuple[str, str]


class TopBar(Horizontal):
    """Single-line app bar with breadcrumb and contextual meta."""

    def __init__(
        self,
        *parts: str,
        meta: str = "",
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._parts = parts
        self._meta = meta
        self.add_class("top-bar")

    def compose(self) -> ComposeResult:
        yield Static(self._format_path(), classes="top-bar-path")
        yield Static(self._format_meta(), classes="top-bar-meta")

    def set_context(self, *parts: str, meta: str = "") -> None:
        self._parts = parts
        self._meta = meta
        with contextlib.suppress(Exception):
            self.query_one(".top-bar-path", Static).update(self._format_path())
            self.query_one(".top-bar-meta", Static).update(self._format_meta())

    def _format_path(self) -> str:
        if not self._parts:
            return ""
        from loghop.tui import strings

        sep = f" [dim]{glyph.SEP_CRUMB}[/] "
        parts_joined = sep.join(self._parts)
        return f"[b]{glyph.BRAND_MARK} {strings.tr('APP_TITLE')}[/] {sep}{parts_joined}"

    def _format_meta(self) -> str:
        return f"[dim]{self._meta}[/]" if self._meta else ""


class CommandBar(Horizontal):
    """Context-aware bottom command bar with neutral keycaps."""

    def __init__(
        self,
        actions: list[_Action] | None = None,
        *,
        status: str = "",
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._actions = actions or []
        self._status = status
        self.add_class("command-bar")

    def compose(self) -> ComposeResult:
        yield Static(self._format_actions(), classes="command-bar-actions")
        yield Static(self._format_status(), classes="command-bar-status")

    def set_actions(self, actions: list[_Action], *, status: str = "") -> None:
        self._actions = actions
        self._status = status
        with contextlib.suppress(Exception):
            self.query_one(".command-bar-actions", Static).update(self._format_actions())
            self.query_one(".command-bar-status", Static).update(self._format_status())

    def set_status(self, status: str) -> None:
        self._status = status
        with contextlib.suppress(Exception):
            self.query_one(".command-bar-status", Static).update(self._format_status())

    def _format_actions(self) -> str:
        return "  ".join(
            f"[reverse bold] {key} [/][dim] {label}[/]" for key, label in self._actions
        )

    def _format_status(self) -> str:
        return f"[dim]{self._status}[/]" if self._status else ""
