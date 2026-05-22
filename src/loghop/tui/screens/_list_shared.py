from typing import Any

from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import DataTable, Input

from loghop.logging import get_logger
from loghop.tui import strings
from loghop.tui.widgets import glyph

_LOGGER = get_logger()


def _parse_search(raw: str) -> tuple[str, set[str]]:
    tokens = (raw or "").strip().lower().split()
    flags = {t[1:] for t in tokens if t.startswith("!") and len(t) > 1}
    text = " ".join(t for t in tokens if not t.startswith("!"))
    return text, flags


def _render_error_str(message: str) -> str:
    body = strings.tr("LOAD_ERROR", error=message)
    hint = strings.tr("RETRY_HINT")
    return f"[red]{glyph.FAIL} {body}[/]\n[dim]{hint}[/]"


class ListScreen(Screen[None]):
    _table_id: str
    _search_input_id: str
    _sort_cycle: tuple[str, ...]
    _sort_labels: dict[str, str]
    _empty_key: str
    _empty_filtered_key: str
    _valid_flags: frozenset[str] = frozenset()

    sort_key: reactive[str] = reactive("")

    NARROW_THRESHOLD = 80

    def __init__(self) -> None:
        super().__init__()
        self._error: str | None = None
        self._initialized = False

    def on_mount(self) -> None:
        self._apply_responsive()

    def on_resize(self, event: Any) -> None:
        self._apply_responsive()

    def _apply_responsive(self) -> None:
        try:
            width = self.size.width
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to read screen width for responsive layout", exc_info=True)
            return
        self.set_class(width < self.NARROW_THRESHOLD, "narrow")

    def watch_sort_key(self, new_key: str) -> None:
        if new_key and getattr(self, "_initialized", False):
            self._populate()

    def _search_query_parts(self) -> tuple[str, set[str]]:
        try:
            value = self.query_one(f"#{self._search_input_id}", Input).value
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to read search input value", exc_info=True)
            return "", set()
        text, flags = _parse_search(str(value))
        valid_flags: frozenset[str] = getattr(self, "_valid_flags", frozenset())
        if valid_flags:
            flags = {flag for flag in flags if flag in valid_flags}
        return text, flags

    @staticmethod
    def _render_error(message: str) -> str:
        return _render_error_str(message)

    def _render_empty(self, *, text: str, flags: set[str], total: int) -> str:
        if total == 0 and not text and not flags:
            return getattr(strings, self._empty_key, "")
        parts: list[str] = []
        if text:
            parts.append(f'q="{text}"')
        parts.extend(f"!{flag}" for flag in sorted(flags))
        if not parts:
            return f"[dim]{strings.tr('NO_MATCHES')}[/]"
        return f"[dim]{strings.tr(self._empty_filtered_key, filters=', '.join(parts))}[/]"

    _debounce_timer: Any = None

    def _debounced_populate(self) -> None:
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
        self._debounce_timer = self.set_timer(0.2, self._populate)

    def action_list_up(self) -> None:
        table = self.query_one(f"#{self._table_id}", DataTable)
        if table.display and table.row_count:
            table.action_cursor_up()

    def action_list_down(self) -> None:
        table = self.query_one(f"#{self._table_id}", DataTable)
        if table.display and table.row_count:
            table.action_cursor_down()

    def action_toggle_focus(self) -> None:
        """Switch focus between the data table and the preview pane."""
        self._toggle_focus(forward=True)

    def action_toggle_focus_reverse(self) -> None:
        """Switch focus backward between the preview pane and data table."""
        self._toggle_focus(forward=False)

    def _toggle_focus(self, *, forward: bool) -> None:
        focused = self.focused
        table_id = f"#{self._table_id}"
        if focused is None:
            self.query_one(table_id, DataTable).focus()
            return
        focused_id = focused.id or ""
        if forward and focused_id in {self._table_id, self._search_input_id}:
            try:
                preview = self.query_one("PreviewPane")
            except LookupError:
                pass
            else:
                if preview.children:
                    preview.focus()
                    return
        if not forward and focused_id not in {self._table_id, self._search_input_id}:
            try:
                search = self.query_one(f"#{self._search_input_id}", Input)
            except LookupError:
                pass
            else:
                search.focus()
                return
        self.query_one(table_id, DataTable).focus()

    def action_refresh(self) -> None:
        self._populate()

    def action_help(self) -> None:
        from loghop.tui.screens.help import HelpScreen

        self.app.push_screen(HelpScreen())

    def action_cycle_sort(self) -> None:
        current = self.sort_key or self._sort_cycle[0]
        idx = self._sort_cycle.index(current) if current in self._sort_cycle else 0
        self.sort_key = self._sort_cycle[(idx + 1) % len(self._sort_cycle)]

    def action_yank(self) -> None:
        entity = self._cursor_entity()
        if entity is None:
            return
        value = self._yank_value(entity)
        if not value:
            return
        import contextlib

        with contextlib.suppress(Exception):
            self.app.copy_to_clipboard(value)
        self.app.notify(strings.tr("YANKED", value=value))

    def _cursor_entity(self) -> Any:
        table = self.query_one(f"#{self._table_id}", DataTable)
        if not table.display or not table.row_count:
            return None
        cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
        return self._entity_for_key(cell_key.row_key)

    def _entity_for_key(self, row_key: Any) -> Any:
        raise NotImplementedError

    @staticmethod
    def _yank_value(entity: Any) -> str:
        raise NotImplementedError

    def _populate(self) -> None:
        raise NotImplementedError
