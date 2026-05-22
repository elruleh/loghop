from pathlib import Path
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Input, Static

from loghop.logging import get_logger
from loghop.store import delete_project_data
from loghop.store._registry import register_project, unregister_project
from loghop.tui import strings
from loghop.tui.format import relative_time, time_bucket_key
from loghop.tui.screens._home_vm import (
    SORT_CYCLE,
    SORT_LABELS,
    format_latest_update,
    format_name_cell,
    format_pending_preview,
    format_sessions_cell,
    format_when_cell,
    matches_project,
    sort_projects,
)
from loghop.tui.screens._list_shared import ListScreen
from loghop.tui.widgets import glyph
from loghop.tui.widgets.chrome import CommandBar, TopBar
from loghop.tui.widgets.preview_pane import PreviewPane

_LOGGER = get_logger()
_MAX_CACHE_SIZE = 100


class HomeScreen(ListScreen):
    _table_id = "project-table"
    _search_input_id = "project-search"
    _sort_cycle = SORT_CYCLE
    _sort_labels = SORT_LABELS
    _empty_key = "PROJECTS_EMPTY"
    _empty_filtered_key = "EMPTY_FILTERED_PROJECTS"
    _valid_flags = frozenset({"current", "missing"})
    preview_open: reactive[bool] = reactive(False)

    BINDINGS = [  # noqa: RUF012
        Binding("q", "quit", "Quit"),
        Binding("a", "add_folder", "Add"),
        Binding("d", "delete_project", "Remove"),
        Binding("D", "purge_project", "Delete data", show=False),
        Binding("u", "undo", "Undo", show=False),
        Binding("r", "refresh", "Refresh"),
        Binding("/", "focus_search", "Search"),
        Binding("s", "cycle_sort", "Sort", show=False),
        Binding("y", "yank", "Copy", show=False),
        Binding("question_mark", "help", "Help"),
        Binding("tab", "toggle_focus", "", show=False),
        Binding("shift+tab", "toggle_focus_reverse", "", show=False),
        Binding("escape", "blur_search", "", show=False),
        Binding("j", "list_down", "", show=False),
        Binding("k", "list_up", "", show=False),
    ]

    def __init__(self, service: Any) -> None:
        super().__init__()
        self._service = service
        self._projects_cache: list[Any] = []
        self._table: DataTable[object] | None = None
        self._empty_widget: Static | None = None
        self._preview: PreviewPane | None = None
        self._search_input: Input | None = None
        self._top_bar: TopBar | None = None
        self._command_bar: CommandBar | None = None
        self._populate_worker: Any = None
        self._loading_spinner = False
        self._spinner_timer: Any = None
        self._error: str | None = None
        self._spinner_idx = 0
        self._populate_generation = 0
        self._chrome_shown = 0
        self._chrome_total = 0
        self._chrome_query = ""
        self._chrome_flags: set[str] = set()
        self._latest_cache: dict[str, Any] = {}
        self._latest_loading: set[str] = set()
        self._home_table_layout = ""
        self._preview_generation = 0
        self._preview_project_key = ""
        self._active = True

    def compose(self) -> ComposeResult:
        yield TopBar(strings.PROJECTS_TITLE, id="home-top-bar")
        yield Input(placeholder=strings.PROJECTS_SEARCH_PLACEHOLDER, id="project-search")
        with Horizontal(id="projects-body"):
            with Vertical(id="projects-list-col"):
                yield DataTable(
                    id="project-table",
                    cursor_type="row",
                    zebra_stripes=True,
                )
                yield Static("", id="projects-empty")
            yield PreviewPane(id="project-preview")
        yield CommandBar(
            self._default_actions(),
            status=strings.tr("READY"),
            id="home-command-bar",
        )

    def on_mount(self) -> None:
        self.sub_title = strings.PROJECTS_TITLE
        self.set_reactive(HomeScreen.sort_key, self._sort_cycle[0])
        self._table = self.query_one("#project-table", DataTable)
        self._empty_widget = self.query_one("#projects-empty", Static)
        self._preview = self.query_one("#project-preview", PreviewPane)
        self._search_input = self.query_one("#project-search", Input)
        self._top_bar = self.query_one("#home-top-bar", TopBar)
        self._command_bar = self.query_one("#home-command-bar", CommandBar)
        self._initialized = True
        self._populate()
        self.set_focus(self._table)
        self._apply_responsive()
        self._spinner_timer_interval = self.set_interval(0.1, self._tick_spinner)

    def on_unmount(self) -> None:
        self._active = False
        if self._populate_worker:
            self._populate_worker.cancel()
            self._populate_worker = None
        if self._spinner_timer:
            self._spinner_timer.stop()
            self._spinner_timer = None
        if self._spinner_timer_interval:
            self._spinner_timer_interval.stop()

    def _tick_spinner(self) -> None:
        self._spinner_idx = (self._spinner_idx + 1) % len(glyph.SPINNER_FRAMES)
        if self._loading_spinner:
            self._update_chrome(
                shown=len(self._projects_cache),
                total=0,  # total unknown until populate finishes
            )

    def _apply_responsive(self) -> None:
        before = self._home_table_layout
        super()._apply_responsive()
        after = "compact" if self.has_class("narrow") else "full"
        if (
            before
            and before != after
            and self._table is not None
            and self._empty_widget is not None
            and self._table.columns
        ):
            if self._projects_cache:
                self._populate_table(self._table, self._empty_widget, self._projects_cache)
            else:
                self._populate()
        self._sync_preview_visibility()

    def refresh_translations(self) -> None:
        """Update translatable strings on the screen without recomposing."""
        from loghop.tui import strings

        self.sub_title = strings.PROJECTS_TITLE
        if self._search_input is not None:
            self._search_input.placeholder = strings.PROJECTS_SEARCH_PLACEHOLDER
        if self._table is not None and self._empty_widget is not None:
            self._table.clear(columns=True)
            if self._projects_cache:
                self._populate_table(self._table, self._empty_widget, self._projects_cache)
                if self._table.row_count:
                    self._render_preview(self._projects_cache[0])
            else:
                self._populate()
        else:
            if self._table is not None:
                self._table.clear(columns=True)
            self._populate()
        self._sync_preview_visibility()

    def watch_preview_open(self, _is_open: bool) -> None:
        self._sync_preview_visibility()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "project-search":
            self._debounced_populate()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "project-search" and self._table is not None:
            self._table.focus()
            self._populate()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._render_preview(self._entity_for_key(event.row_key))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        project = self._entity_for_key(event.row_key)
        if project is None:
            return
        if not getattr(project, "exists", False):
            self.app.notify(strings.tr("PROJECT_MISSING"), severity="warning")
            return
        self.app.open_project(str(project.path))  # type: ignore[attr-defined]  # LoghopApp method is dynamic from Textual base

    def _populate(self) -> None:
        if self._populate_worker:
            self._populate_worker.cancel()

        self._latest_cache.clear()
        text, flags = self._search_query_parts()
        self._populate_generation += 1
        generation = self._populate_generation

        def _fetch_and_notify() -> None:
            from textual.worker import get_current_worker

            worker = get_current_worker()
            if worker.is_cancelled:
                return
            try:
                data = list(self._service.projects())
                error = None
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Failed to fetch projects list", exc_info=True)
                data = []
                error = str(exc)

            if worker.is_cancelled:
                return
            if generation == self._populate_generation:
                self.app.call_from_thread(
                    self._on_populate_data, data, error, text, flags, generation
                )

        def _show_spinner() -> None:
            if generation != self._populate_generation:
                return
            self._loading_spinner = True
            self._update_chrome(
                shown=len(self._projects_cache),
                total=0,  # Unknown yet
                query=text,
                flags=flags,
            )
            self._spinner_timer = None

        self._populate_worker = self.run_worker(_fetch_and_notify, thread=True)
        self._spinner_timer = self.set_timer(0.2, _show_spinner)

    def _on_populate_data(
        self,
        all_projects: list[Any],
        error: str | None,
        text: str,
        flags: set[str],
        generation: int,
    ) -> None:
        """Handle data returned by the populate worker."""
        if not getattr(self, "_active", False):
            return
        if generation != self._populate_generation:
            return
        self._loading_spinner = False
        if self._spinner_timer:
            self._spinner_timer.stop()
            self._spinner_timer = None

        self._error = error
        projects = sort_projects(all_projects, self.sort_key)
        if text or flags:
            projects = [p for p in projects if matches_project(p, text, flags)]

        self._update_cache(projects, all_projects, text, flags)
        self._update_chrome(shown=len(projects), total=len(all_projects), query=text, flags=flags)

        table = self._table or self.query_one("#project-table", DataTable)
        empty = self._empty_widget or self.query_one("#projects-empty", Static)

        if self._error is not None:
            self._show_error_state(table, empty, self._error)
            return

        if not projects:
            self._show_empty_state(table, empty, text, flags, len(all_projects))
            return

        self._populate_table(table, empty, projects)
        if table.row_count:
            self._render_preview(projects[0])
        self._sync_preview_visibility()

    def _update_cache(
        self,
        projects: list[Any],
        all_projects: list[Any],
        text: str,
        flags: set[str],
    ) -> None:
        self._projects_cache = projects
        self._chrome_shown = len(projects)
        self._chrome_total = len(all_projects)
        self._chrome_query = text
        self._chrome_flags = set(flags)

    def _show_error_state(self, table: DataTable[Any], empty: Static, error: str) -> None:
        table.display = False
        empty.display = True
        empty.update(self._render_error(error))
        self._render_preview(None)
        self._sync_preview_visibility()

    def _show_empty_state(
        self,
        table: DataTable[Any],
        empty: Static,
        text: str,
        flags: set[str],
        total: int,
    ) -> None:
        table.display = False
        table.clear(columns=False)
        empty.display = True
        empty.update(self._render_empty(text=text, flags=flags, total=total))
        self._render_preview(None)
        self._sync_preview_visibility()

    def _populate_table(self, table: DataTable[Any], empty: Static, projects: list[Any]) -> None:
        """Set up columns and populate the data table with project rows."""
        table.display = True
        empty.display = False

        desired_layout = "compact" if self.has_class("narrow") else "full"
        if not table.columns or self._home_table_layout != desired_layout:
            table.clear(columns=True)
            self._home_table_layout = desired_layout
            if desired_layout == "compact":
                table.add_column("", key="cur", width=2)
                table.add_column(strings.tr("PROJECT_TABLE_PROJECT"), key="name")
                table.add_column(strings.tr("PROJECT_TABLE_LAST_USED"), key="last_used", width=12)
            else:
                table.add_column("", key="cur", width=2)
                table.add_column(strings.tr("PROJECT_TABLE_PROJECT"), key="name")
                table.add_column(strings.tr("PROJECT_TABLE_SESSIONS"), key="sessions")
                table.add_column(strings.tr("PROJECT_TABLE_LAST_USED"), key="last_used")

        table.clear(columns=False)

        previous_bucket: str | None = None
        for project in projects:
            row_key_str = str(project.path)
            bucket_key = time_bucket_key(project.last_used or "")
            is_new_bucket = bool(bucket_key and bucket_key != previous_bucket)
            previous_bucket = bucket_key or previous_bucket

            mark = glyph.CURRENT if project.current else " "
            name_cell = format_name_cell(project)
            when_cell = format_when_cell(
                relative_time(project.last_used or ""),
                bucket_key if is_new_bucket else None,
            )

            if self._home_table_layout == "compact":
                table.add_row(mark, name_cell, when_cell, key=row_key_str)
            else:
                sessions_cell = format_sessions_cell(project)
                table.add_row(mark, name_cell, sessions_cell, when_cell, key=row_key_str)

    _format_name_cell = staticmethod(format_name_cell)
    _format_when_cell = staticmethod(format_when_cell)
    _format_sessions_cell = staticmethod(format_sessions_cell)

    def _entity_for_key(self, row_key: Any) -> Any:
        target = str(row_key.value) if row_key and row_key.value else ""
        for p in self._projects_cache:
            if str(p.path) == target:
                return p
        return None

    @staticmethod
    def _yank_value(entity: Any) -> str:
        return str(entity.path)

    @work(exclusive=True, thread=True)
    def _fetch_preview_data(self, project: Any, generation: int, project_key: str) -> None:
        from textual.worker import get_current_worker

        worker = get_current_worker()
        if worker.is_cancelled:
            return
        if not getattr(project, "exists", False):
            self.app.call_from_thread(
                self._mount_preview_content, project, None, generation, project_key
            )
            return

        key = str(project.path)
        if key in self._latest_cache:
            entry = self._latest_cache[key]
        else:
            try:
                if worker.is_cancelled:
                    return
                entries = self._service.timeline(Path(key), limit=1)
                entry = entries[0] if entries else None
                if len(self._latest_cache) >= _MAX_CACHE_SIZE:
                    first_key = next(iter(self._latest_cache))
                    self._latest_cache.pop(first_key, None)
                self._latest_cache[key] = entry
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Failed to fetch timeline for preview", exc_info=True)
                entry = None

        if worker.is_cancelled:
            return
        self.app.call_from_thread(
            self._mount_preview_content, project, entry, generation, project_key
        )

    def _render_preview(self, project: Any) -> None:
        try:
            preview = self.query_one("#project-preview", PreviewPane)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to query preview pane", exc_info=True)
            return
        self._preview = preview
        if project is None:
            preview.set_empty(strings.PROJECTS_PREVIEW_EMPTY)
            return

        key = str(project.path)
        self._preview_generation += 1
        generation = self._preview_generation
        self._preview_project_key = key

        preview.clear_fixed()
        preview.clear_content()
        preview.clear_footer()

        # Mount basic info synchronously
        preview.mount_fixed(
            Static(f"[b]{project.name}[/]", classes="preview-hero-title"),
            Static(f"[dim]{project.path}[/]", classes="preview-hero-meta"),
        )

        sep = f"  {glyph.SEP_DOT}  "
        meta_parts = [
            strings.tr("PROJECT_SESSIONS", count=project.session_count),
            strings.tr("PROJECT_HANDOFFS", count=project.handoff_count),
            f"{glyph.CLOCK} {project.last_used[:10] if project.last_used else '—'}",
        ]
        preview.mount_fixed(Static(f"[dim]{sep.join(meta_parts)}[/]", classes="preview-hero-meta"))

        if key in self._latest_cache:
            self._mount_preview_content(project, self._latest_cache[key], generation, key)
            return

        # Add a loading indicator in the content area
        preview.add_section(
            strings.tr("PROJECT_PREVIEW_LOADING_TITLE"),
            strings.tr("PROJECT_PREVIEW_LOADING_BODY"),
            classes="preview-loading",
        )

        # Trigger the worker unless this project's latest event is already loading.
        if key not in self._latest_loading:
            self._latest_loading.add(key)
            self._fetch_preview_data(project, generation, key)

    def _mount_preview_content(
        self,
        project: Any,
        latest: Any,
        generation: int,
        project_key: str,
    ) -> None:
        if not getattr(self, "_active", False):
            return
        self._latest_loading.discard(project_key)
        if generation != self._preview_generation:
            return
        if project_key != self._preview_project_key:
            return
        try:
            preview = self.query_one("#project-preview", PreviewPane)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to query preview pane for content mount", exc_info=True)
            return

        preview.clear_content()
        preview.clear_footer()

        if project.goal:
            preview.add_section(strings.tr("PROJECT_GOAL"), project.goal)

        if latest is not None:
            preview.add_section(strings.tr("PROJECT_LATEST_UPDATE"), format_latest_update(latest))
            if getattr(latest, "todos_pending", ()):
                preview.add_section(
                    strings.tr("PROJECT_NEXT_UP"),
                    format_pending_preview(getattr(latest, "todos_pending", ()) or ()),
                )
        if not project.exists:
            preview.add_section(
                "",
                f"{glyph.WARN} {strings.tr('PROJECT_MISSING')}",
                classes="warning-text",
            )

        # Add the shortcuts hint back
        sep = f"  {glyph.SEP_DOT}  "
        hint = sep.join(
            [
                strings.tr("PROJECTS_SHORTCUT_OPEN"),
                strings.tr("PROJECTS_SHORTCUT_REMOVE"),
                strings.tr("PROJECTS_SHORTCUT_FORGET"),
            ]
        )
        preview.mount_footer(Static(f"[dim]{hint}[/]", classes="preview-hint"))

    def _matches(self, project: Any, text: str, flags: set[str]) -> bool:
        return matches_project(project, text, flags)

    def _update_chrome(
        self,
        *,
        shown: int,
        total: int,
        query: str = "",
        flags: set[str] | None = None,
    ) -> None:
        flags = flags or set()
        meta_parts = [
            strings.tr("PROJECTS_COUNT_FILTERED", shown=shown, total=total)
            if (query or flags)
            else strings.tr("PROJECTS_COUNT", total=total)
        ]
        if query:
            meta_parts.append(strings.tr("SEARCH_META", query=query))
        meta_parts.extend(f"!{flag}" for flag in sorted(flags))
        if self.sort_key != self._sort_cycle[0]:
            meta_parts.append(
                strings.tr(
                    "SORT_BY", name=strings.tr(SORT_LABELS.get(self.sort_key, "SORT_RECENT"))
                )
            )
        top_bar = self._top_bar or self.query_one("#home-top-bar", TopBar)
        top_bar.set_context(
            strings.PROJECTS_TITLE,
            meta=f"  {glyph.SEP_DOT}  ".join(meta_parts),
        )
        status = ""
        if self._loading_spinner:
            frame = glyph.SPINNER_FRAMES[self._spinner_idx]
            status = frame

        cmd_bar = self._command_bar or self.query_one("#home-command-bar", CommandBar)
        cmd_bar.set_actions(
            self._actions(),
            status=status,
        )

    @staticmethod
    def _default_actions() -> list[tuple[str, str]]:
        return [
            ("enter", strings.tr("ACTION_OPEN")),
            ("a", strings.tr("ACTION_ADD")),
            ("d", strings.tr("ACTION_REMOVE")),
            ("s", strings.tr("ACTION_SORT")),
            ("?", strings.tr("ACTION_HELP")),
        ]

    def _detail_toggle_action(self) -> tuple[str, str] | None:
        if not self.has_class("narrow") or not self._projects_cache:
            return None
        label = strings.tr("ACTION_LIST") if self.preview_open else strings.tr("ACTION_DETAILS")
        return ("tab", label)

    def _actions(self) -> list[tuple[str, str]]:
        actions = [
            ("enter", strings.tr("ACTION_OPEN")),
        ]
        detail_action = self._detail_toggle_action()
        if detail_action is not None:
            actions.append(detail_action)
        actions.extend(
            [
                ("a", strings.tr("ACTION_ADD")),
                ("d", strings.tr("ACTION_REMOVE")),
                ("s", strings.tr("ACTION_SORT")),
                ("?", strings.tr("ACTION_HELP")),
            ]
        )
        return actions

    def _sync_preview_visibility(self) -> None:
        preview = self._safe_query_preview("#project-preview")
        if preview is None:
            return
        narrow = self.has_class("narrow")
        visible = (not narrow) or self.preview_open
        preview.display = visible
        self.set_class(narrow and visible, "preview-open")
        self._refocus_if_hidden(narrow, visible, preview)
        self._refresh_chrome_if_needed()

    def _safe_query_preview(self, selector: str) -> PreviewPane | None:
        try:
            return self._preview or self.query_one(selector, PreviewPane)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to query preview pane", exc_info=True)
            return None

    def _refocus_if_hidden(self, narrow: bool, visible: bool, preview: PreviewPane) -> None:
        if narrow and not visible:
            table = self._safe_query_table()
            if table is not None and self.focused is preview:
                table.focus()

    def _safe_query_table(self) -> DataTable[Any] | None:
        try:
            return self._table or self.query_one("#project-table", DataTable)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to query projects table", exc_info=True)
            return None

    def _refresh_chrome_if_needed(self) -> None:
        if self._command_bar is not None:
            self._update_chrome(
                shown=self._chrome_shown,
                total=self._chrome_total,
                query=self._chrome_query,
                flags=self._chrome_flags,
            )

    _format_latest_update = staticmethod(format_latest_update)
    _format_pending_preview = staticmethod(format_pending_preview)

    def action_focus_search(self) -> None:
        search = self._search_input or self.query_one("#project-search", Input)
        search.focus()
        cmd_bar = self._command_bar or self.query_one("#home-command-bar", CommandBar)
        cmd_bar.set_status(strings.tr("SEARCH_FOCUSED"))

    def action_blur_search(self) -> None:
        search = self._search_input or self.query_one("#project-search", Input)
        if search.has_focus:
            table = self._table or self.query_one("#project-table", DataTable)
            table.focus()
            cmd_bar = self._command_bar or self.query_one("#home-command-bar", CommandBar)
            cmd_bar.set_status(strings.tr("READY"))
            return
        if self.has_class("narrow") and self.preview_open:
            self.preview_open = False
            table = self._table or self.query_one("#project-table", DataTable)
            table.focus()

    def action_toggle_focus(self) -> None:
        if not self.has_class("narrow") or not self._projects_cache:
            super().action_toggle_focus()
            return
        if self.preview_open:
            self.preview_open = False
            table = self._table or self.query_one("#project-table", DataTable)
            table.focus()
            return
        self.preview_open = True
        preview = self._preview or self.query_one("#project-preview", PreviewPane)
        preview.focus()

    def action_toggle_focus_reverse(self) -> None:
        if not self.has_class("narrow") or not self._projects_cache:
            super().action_toggle_focus_reverse()
            return
        focused_id = (self.focused.id or "") if self.focused else ""
        if focused_id == self._search_input_id:
            self.preview_open = True
            preview = self._preview or self.query_one("#project-preview", PreviewPane)
            preview.focus()
        elif self.preview_open:
            self.preview_open = False
            table = self._table or self.query_one("#project-table", DataTable)
            table.focus()
        else:
            search = self._search_input or self.query_one("#project-search", Input)
            search.focus()

    def action_add_folder(self) -> None:
        def maybe_refresh(result: Any) -> None:
            if result:
                self._populate()

        from loghop.tui.screens.add_folder import AddFolderModal

        self.app.push_screen(AddFolderModal(self._service), maybe_refresh)

    def action_delete_project(self) -> None:
        project = self._cursor_entity()
        if project is None:
            return

        path = Path(str(project.path))
        goal = project.goal
        name = project.name

        from loghop.tui.screens.confirm import ConfirmModal, project_unregister_spec

        def on_result(confirmed: bool | None) -> None:
            if not confirmed:
                return
            unregister_project(path)

            def undo() -> None:
                register_project(path, goal=goal)
                self._populate()

            self.app.undo_stack.push(name, undo)  # type: ignore[attr-defined]  # LoghopApp injects undo_stack dynamically
            self.app.notify(strings.tr("DELETED_NOTICE", name=name), timeout=6)
            self._populate()

        self.app.push_screen(
            ConfirmModal(project_unregister_spec(name, str(path))),
            on_result,
        )

    def action_purge_project(self) -> None:
        project = self._cursor_entity()
        if project is None:
            return

        path = Path(str(project.path))
        name = project.name

        from loghop.tui.screens.confirm import ConfirmModal, project_purge_spec

        def on_result(confirmed: bool | None) -> None:
            if not confirmed:
                return
            try:
                delete_project_data(path)
            except (OSError, ValueError) as exc:
                self.app.notify(strings.tr("ERROR_PREFIX", error=str(exc)), severity="error")
                return
            unregister_project(path)
            self.app.notify(strings.tr("DELETED_PURGED_NOTICE", name=name), timeout=6)
            self._populate()

        self.app.push_screen(
            ConfirmModal(project_purge_spec(name, str(path))),
            on_result,
        )

    def action_undo(self) -> None:
        action = self.app.undo_stack.pop()  # type: ignore[attr-defined]  # LoghopApp injects undo_stack dynamically
        if action is None:
            return
        label, callable_ = action
        callable_()
        self.app.notify(strings.tr("RESTORED_NOTICE", name=label))
