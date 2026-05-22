"""Preview pane: a vertical container split into hero / scroll body / footer.

Layout:
    +--------------------------------+
    | hero (fixed)                   |   title + meta inline
    +--------------------------------+
    | scroll body                    |   sections, scrollable
    |   ...                          |
    +--------------------------------+
    | footer (fixed)                 |   primary actions
    +--------------------------------+
"""

from contextlib import suppress

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

from loghop.logging import get_logger
from loghop.tui.widgets import glyph

_LOGGER = get_logger()


class Spinner(Static):
    """Animated braille spinner — used for live "running" indicators."""

    _FRAMES = glyph.SPINNER_FRAMES
    _INTERVAL = 0.08

    def __init__(self, *, color: str | None = None) -> None:
        if color is None:
            from loghop.tui.widgets.badge import role_color

            color = role_color("warning")
        self._color = color
        self._idx = 0
        super().__init__(self._frame_markup(0))

    def _frame_markup(self, idx: int) -> str:
        return f"[bold {self._color}]{self._FRAMES[idx]}[/]"

    def on_mount(self) -> None:
        self.set_interval(self._INTERVAL, self._tick)

    def _tick(self) -> None:
        self._idx = (self._idx + 1) % len(self._FRAMES)
        self.update(self._frame_markup(self._idx))


class PreviewPane(Vertical):
    """Right-hand preview pane.

    Use ``set_sections([(title, body)])`` for a simple body, or use the
    finer-grained API: ``mount_fixed`` (hero), ``add_section`` (body),
    ``mount_footer`` (action footer).
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.can_focus = True
        self.add_class("preview-pane")
        self._empty_text = ""

    def compose(self) -> ComposeResult:
        yield Vertical(classes="preview-fixed", id="preview-fixed")
        with VerticalScroll(classes="preview-scroll", id="preview-scroll"):
            yield Static(self._empty_text, id="preview-empty")
        yield Vertical(classes="preview-footer", id="preview-footer")

    def set_empty(self, text: str) -> None:
        self._empty_text = text
        self._render_empty()

    def clear_fixed(self) -> None:
        with suppress(Exception):
            fixed = self.query_one("#preview-fixed", Vertical)
            for child in list(fixed.children):
                child.remove()

    def clear_content(self) -> None:
        with suppress(Exception):
            scroll = self.query_one("#preview-scroll", VerticalScroll)
            for child in list(scroll.children):
                if child.id == "preview-empty" and isinstance(child, Static):
                    child.update("")
                else:
                    child.remove()

    def clear_footer(self) -> None:
        with suppress(Exception):
            footer = self.query_one("#preview-footer", Vertical)
            for child in list(footer.children):
                child.remove()

    def _ensure_children(self) -> None:
        """Best-effort child lookup during recompose-sensitive updates.

        The preview pane is composed declaratively. During app startup or screen
        recomposition, helper methods may briefly run before the internal
        `VerticalScroll` subtree is fully mounted. In that window we must avoid
        imperative child creation, otherwise Textual can raise mount or
        duplicate-id errors. The preview methods already degrade gracefully when
        the subtree is temporarily unavailable, so this helper should only
        restore the empty placeholder when the scroll container definitely
        exists and is attached.
        """
        if not self.is_attached:
            return
        try:
            scroll = self.query_one("#preview-scroll", VerticalScroll)
        except Exception:  # noqa: BLE001
            return
        if not scroll.is_attached:
            return
        try:
            scroll.query_one("#preview-empty", Static)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Preview empty widget missing; recreating", exc_info=True)
            with suppress(Exception):
                scroll.mount(Static(self._empty_text, id="preview-empty"))

    def _render_empty(self) -> None:
        self._ensure_children()
        self.clear_fixed()
        self.clear_footer()
        with suppress(Exception):
            empty = self.query_one("#preview-empty", Static)
            empty.update(self._empty_text)
        with suppress(Exception):
            scroll = self.query_one("#preview-scroll", VerticalScroll)
            for child in list(scroll.children):
                if child.id != "preview-empty":
                    child.remove()

    def mount_fixed(self, *widgets: Widget) -> None:
        self._ensure_children()
        try:
            fixed = self.query_one("#preview-fixed", Vertical)
            fixed.mount(*widgets)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to mount fixed widgets", exc_info=True)

    def mount_footer(self, *widgets: Widget) -> None:
        self._ensure_children()
        try:
            footer = self.query_one("#preview-footer", Vertical)
            footer.mount(*widgets)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to mount footer widgets", exc_info=True)

    def add_section(self, title: str, body: str, *, classes: str = "") -> None:
        self._ensure_children()
        children: list[Widget] = []
        if title:
            children.append(Static(title, classes="preview-section-title"))
        children.append(Static(body or "—", classes="preview-section-body"))
        try:
            scroll = self.query_one("#preview-scroll", VerticalScroll)
            scroll.mount(Vertical(*children, classes=f"preview-section {classes}".strip()))
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to add section to scroll", exc_info=True)
