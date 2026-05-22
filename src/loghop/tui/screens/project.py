import asyncio
import shlex
from contextlib import suppress
from datetime import UTC
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Static,
)
from textual.worker import Worker

from loghop.logging import get_logger
from loghop.tui import strings
from loghop.tui.format import format_duration, parse_timestamp, relative_time, truncate
from loghop.tui.launcher import build_resume_command, launch_in_new_tab
from loghop.tui.models import PROVIDER_SHORTCUTS
from loghop.tui.screens._list_shared import ListScreen
from loghop.tui.screens._project_vm import (
    SORT_CYCLE,
    SORT_LABELS,
    filter_sessions,
    format_conversation_excerpt,
    format_files_block,
    format_list_block,
    format_next_block,
    format_todos_block,
    running_session_ids,
    sort_sessions,
)
from loghop.tui.widgets import badge, glyph
from loghop.tui.widgets.chrome import CommandBar, TopBar
from loghop.tui.widgets.filter_chips import ChipDismissed, FilterChips
from loghop.tui.widgets.preview_pane import PreviewPane, Spinner

_LOGGER = get_logger()
_MAX_CACHE_SIZE = 100

_SPINNER_INTERVAL = 0.12


def _build_bindings() -> list[Binding]:
    base: list[Binding] = [
        Binding("escape", "escape", "Back"),
        Binding("b", "go_back", "Back"),
        Binding("enter", "resume_default", "Resume", priority=True),
        Binding("r", "refresh", "Refresh"),
        Binding("/", "focus_search", "Search"),
        Binding("f", "cycle_provider", "Filter"),
        Binding("s", "cycle_sort", "Sort", show=False),
        Binding("y", "yank", "Copy", show=False),
        Binding("x", "clear_filters", "Clear", show=False),
        Binding("d", "delete_session", "Delete", show=False),
    ]
    for name, key in PROVIDER_SHORTCUTS.items():
        base.append(Binding(key, f"resume_named('{name}')", name, show=False))
    base += [
        Binding("tab", "toggle_focus", "", show=False),
        Binding("shift+tab", "toggle_focus_reverse", "", show=False),
        Binding("j", "list_down", "", show=False),
        Binding("k", "list_up", "", show=False),
        Binding("question_mark", "help", "Help"),
    ]
    return base


class ProjectScreen(ListScreen):
    _table_id = "session-table"
    _search_input_id = "filter-search"
    _sort_cycle = SORT_CYCLE
    _sort_labels = SORT_LABELS
    _empty_key = "SESSIONS_EMPTY"
    _empty_filtered_key = "EMPTY_FILTERED_SESSIONS"
    _valid_flags = frozenset({"running", "failed", "done", "today"})

    BINDINGS = _build_bindings()  # type: ignore[assignment]  # Textual Binding list typing is narrower than helper return
    preview_open: reactive[bool] = reactive(False)

    def __init__(self, service: Any, project_path: str) -> None:
        super().__init__()
        self._service = service
        self._project_path = Path(project_path)
        self._project: Any = None
        self._sessions_cache: list[Any] = []
        self._provider_cycle: list[str] = []
        self._spinner_idx: int = 0
        self._spinner_timer: Timer | None = None
        self._table: DataTable[object] | None = None
        self._empty_widget: Static | None = None
        self._preview: PreviewPane | None = None
        self._search_input: Input | None = None
        self._top_bar: TopBar | None = None
        self._command_bar: CommandBar | None = None
        self._filter_chips: FilterChips | None = None
        self._chrome_shown = 0
        self._chrome_total = 0
        self._chrome_query = ""
        self._chrome_flags: set[str] = set()
        self._populate_worker: Worker[None] | None = None
        self._loading_spinner = False
        self._populate_generation = 0
        self._table_layout = ""
        self._active = True
        self._default_provider: str | None = None
        self._running_session_ids: set[str] = set()
        self._preview_generation = 0
        self._preview_session_id = ""
        self._conversation_cache: dict[str, tuple[tuple[str, str], ...]] = {}
        self._conversation_loading: set[str] = set()

    filter_provider: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        project = self._project
        name = project.name if project else self._project_path.name
        yield TopBar(name, strings.SESSIONS_TITLE, id="project-top-bar")

        yield Input(placeholder=strings.SESSIONS_SEARCH_PLACEHOLDER, id="filter-search")
        yield FilterChips(id="filter-chips")

        with Horizontal(id="sessions-body"):
            with Vertical(id="sessions-list-col"):
                yield DataTable(
                    id="session-table",
                    cursor_type="row",
                    zebra_stripes=True,
                )
                yield Static("", id="sessions-empty")
            yield PreviewPane(id="session-preview")

        yield CommandBar(
            self._default_actions(),
            status=strings.tr("READY"),
            id="project-command-bar",
        )

    @work(exclusive=True)
    async def _setup_project_data(self) -> None:
        # Resolve project and providers in a background thread
        try:
            project, providers, default_provider = await asyncio.to_thread(
                self._fetch_project_dependencies
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Failed to setup project data", exc_info=True)
            self._error = str(exc)
            table = self._table or self.query_one("#session-table", DataTable)
            empty = self._empty_widget or self.query_one("#sessions-empty", Static)
            self._show_error_state(table, empty, self._error)
            return

        self._project = project
        self.sub_title = self._project.name if self._project else self._project_path.name

        self._provider_cycle = [""] + [
            getattr(p, "name", "") for p in providers if getattr(p, "name", "")
        ]
        self._default_provider = default_provider

        # Trigger the population of sessions
        self._populate()

    def _fetch_project_dependencies(self) -> tuple[Any, Any, Any]:
        project = None
        for p in self._service.projects():
            if str(p.path) == str(self._project_path):
                project = p
                break

        providers = self._service.providers(self._project_path)
        default_provider = self._service.default_provider(self._project_path)
        return project, providers, default_provider

    def on_mount(self) -> None:
        self.sub_title = self._project_path.name

        self._reconcile_async()

        self.set_reactive(ProjectScreen.sort_key, self._sort_cycle[0])
        self._table = self.query_one("#session-table", DataTable)
        self._empty_widget = self.query_one("#sessions-empty", Static)
        self._preview = self.query_one("#session-preview", PreviewPane)
        self._search_input = self.query_one("#filter-search", Input)
        self._top_bar = self.query_one("#project-top-bar", TopBar)
        self._command_bar = self.query_one("#project-command-bar", CommandBar)
        self._filter_chips = self.query_one("#filter-chips", FilterChips)

        self._apply_responsive()
        self.set_focus(self._table)
        self._spinner_timer = self.set_interval(_SPINNER_INTERVAL, self._tick_spinner)

        self._initialized = True
        # Start background setup
        self._setup_project_data()

    def on_unmount(self) -> None:
        self._active = False
        if self._populate_worker:
            self._populate_worker.cancel()
            self._populate_worker = None
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None

    def _apply_responsive(self) -> None:
        before = "compact" if self.has_class("narrow") else "full"
        super()._apply_responsive()
        after = self._desired_table_layout()
        if (
            before != after
            and self._table is not None
            and self._empty_widget is not None
            and self._table.columns
        ):
            if self._sessions_cache:
                self._populate_table(self._table, self._empty_widget, self._sessions_cache)
            else:
                self._populate()
        self._sync_preview_visibility()

    def refresh_translations(self) -> None:
        """Update translatable strings on the screen without recomposing."""
        from loghop.tui import strings

        project = self._project
        self.sub_title = project.name if project else self._project_path.name
        if self._search_input is not None:
            self._search_input.placeholder = strings.SESSIONS_SEARCH_PLACEHOLDER
        if self._table is not None and self._empty_widget is not None:
            self._table.clear(columns=True)
            if self._sessions_cache:
                self._populate_table(self._table, self._empty_widget, self._sessions_cache)
                if self._table.row_count:
                    self._render_preview(self._sessions_cache[0])
            else:
                self._populate()
        else:
            if self._table is not None:
                self._table.clear(columns=True)
            self._populate()
        self._sync_preview_visibility()

    def watch_preview_open(self, _is_open: bool) -> None:
        self._sync_preview_visibility()

    def _reconcile_async(self) -> None:
        from loghop.reconcile import auto_reconcile_silent

        path = self._project_path

        def _work() -> None:
            auto_reconcile_silent(path)

        self.run_worker(_work, thread=True, exclusive=True, group="reconcile")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter-search":
            self._debounced_populate()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "filter-search" and self._table is not None:
            self._table.focus()
            self._populate()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._render_preview(self._entity_for_key(event.row_key))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._render_preview(self._entity_for_key(event.row_key))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("resume-"):
            provider = button_id.replace("resume-", "")
            self._launch(provider)

    def on_chip_dismissed(self, event: ChipDismissed) -> None:
        key = event.key
        if key.startswith("provider:"):
            self.filter_provider = ""
        elif key.startswith("q:"):
            self._set_search_text("")
        elif key.startswith("flag:"):
            self._remove_flag(key[5:])
        self._populate()

    def _populate(self) -> None:
        if self._populate_worker:
            self._populate_worker.cancel()

        text, flags = self._search_query_parts()
        self._populate_generation += 1
        generation = self._populate_generation

        def _fetch_and_notify() -> None:
            from textual.worker import get_current_worker

            worker = get_current_worker()
            if worker.is_cancelled:
                return
            try:
                data = list(self._service.timeline(self._project_path))
                error = None
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Failed to fetch session timeline", exc_info=True)
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
                shown=len(self._sessions_cache),
                total=0,
                query=text,
                flags=flags,
            )
            self._spinner_timer = None

        self._populate_worker = self.run_worker(_fetch_and_notify, thread=True)
        self._spinner_timer = self.set_timer(0.2, _show_spinner)

    def _on_populate_data(
        self,
        all_sessions: list[Any],
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

        table = self._table or self.query_one("#session-table", DataTable)
        empty = self._empty_widget or self.query_one("#sessions-empty", Static)
        chips = self._filter_chips or self.query_one("#filter-chips", FilterChips)

        sessions = filter_sessions(
            all_sessions,
            provider=self.filter_provider,
            text=text,
            flags=flags,
        )
        sessions = sort_sessions(sessions, self.sort_key)

        self._sessions_cache = sessions
        self._running_session_ids = running_session_ids(sessions)
        self._chrome_shown = len(sessions)
        self._chrome_total = len(all_sessions)
        self._chrome_query = text
        self._chrome_flags = set(flags)
        self._update_chrome(shown=len(sessions), total=len(all_sessions), query=text, flags=flags)
        self._update_chips(chips, sessions, all_sessions, text, flags)

        if self._error is not None:
            self._show_error_state(table, empty, self._error)
            return

        if not sessions:
            self._show_empty_state(table, empty, text, flags, len(all_sessions))
            return

        self._populate_table(table, empty, sessions)
        if table.row_count:
            self._render_preview(sessions[0])
        self._sync_preview_visibility()

    def _show_error_state(self, table: DataTable[Any], empty: Static, error: str) -> None:
        table.display = False
        empty.display = True
        empty.update(self._render_error(error))
        self._render_empty_preview(show_start_actions=False)
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
        self._render_empty_preview(show_start_actions=total == 0)
        self._sync_preview_visibility()

    def _populate_table(self, table: DataTable[Any], empty: Static, sessions: list[Any]) -> None:
        """Set up columns and populate the data table with session rows."""
        table.display = True
        empty.display = False

        self._ensure_table_columns(table)
        table.clear(columns=False)

        for session in sessions:
            ts_start = getattr(session, "ts_start", "") or ""
            ts_end = getattr(session, "ts_end", "") or ""
            row_key_str = str(getattr(session, "id", ""))

            status_cell = badge.render(getattr(session, "status", ""), compact=True)
            when_cell_val = self._when_cell(ts_start, ts_end)
            title_cell_val = self._title_cell(session)

            if self._table_layout == "compact":
                provider_cell = badge.provider_badge(
                    getattr(session, "provider", "") or "", compact=True
                )
                table.add_row(
                    status_cell,
                    title_cell_val,
                    provider_cell,
                    when_cell_val,
                    key=row_key_str,
                )
            else:
                provider_cell = badge.provider_badge(
                    getattr(session, "provider", "") or "", compact=False
                )
                next_cell_val = self._next_cell(session)
                table.add_row(
                    status_cell,
                    title_cell_val,
                    provider_cell,
                    next_cell_val,
                    when_cell_val,
                    key=row_key_str,
                )

    def _tick_spinner(self) -> None:
        if self._table is None:
            return
        table = self._table

        self._spinner_idx = (self._spinner_idx + 1) % len(glyph.SPINNER_FRAMES)
        frame = glyph.SPINNER_FRAMES[self._spinner_idx]

        if self._loading_spinner:
            self._update_chrome(
                shown=self._chrome_shown,
                total=self._chrome_total,
                query=self._chrome_query,
                flags=self._chrome_flags,
            )

        if not table.display or not self._sessions_cache:
            return

        with self.app.batch_update():
            for sid in self._running_session_ids:
                if not sid:
                    continue
                frame = glyph.SPINNER_FRAMES[self._spinner_idx]
                color = badge.color_for("running")
                with suppress(Exception):
                    table.update_cell(sid, "status", f"[bold {color}]{frame}[/]")

    def _entity_for_key(self, row_key: Any) -> Any:
        target = str(row_key.value) if row_key and row_key.value else ""
        for s in self._sessions_cache:
            if str(getattr(s, "id", "")) == target:
                return s
        return None

    @staticmethod
    def _yank_value(entity: Any) -> str:
        return str(getattr(entity, "id", "") or "")

    def _render_preview(self, session: Any) -> None:
        preview = self._preview or self.query_one("#session-preview", PreviewPane)
        if session is None:
            self._render_empty_preview(show_start_actions=False)
            return

        session_id = str(getattr(session, "session_id", "") or getattr(session, "id", "") or "")
        self._preview_generation += 1
        generation = self._preview_generation
        self._preview_session_id = session_id

        preview.clear_fixed()
        preview.clear_content()
        preview.clear_footer()

        preview.mount_fixed(
            self._build_hero(
                self._entry_title(session),
                getattr(session, "status", "") or "",
            )
        )
        primary_meta, secondary_meta = self._build_meta_lines(
            provider=getattr(session, "provider", "?") or "?",
            ts_start=getattr(session, "ts_start", "") or "",
            ts_end=getattr(session, "ts_end", "") or "",
            turns=getattr(session, "turns_captured", None),
            files_count=len(getattr(session, "files_changed", ()) or ()),
            returncode=getattr(session, "returncode", None),
        )
        if primary_meta:
            preview.mount_fixed(Static(primary_meta, classes="preview-hero-meta"))
        if secondary_meta:
            preview.mount_fixed(
                Static(secondary_meta, classes="preview-hero-meta preview-hero-meta-secondary")
            )

        self._render_preview_sections(preview, session)
        self._mount_resume_actions(preview)
        self._maybe_load_conversation_excerpt(session, generation)

    def _render_empty_preview(self, *, show_start_actions: bool) -> None:
        preview = self._preview or self.query_one("#session-preview", PreviewPane)
        if not show_start_actions:
            preview.set_empty(strings.SESSIONS_PREVIEW_EMPTY)
            return
        preview.set_empty(strings.tr("SESSIONS_START_EMPTY"))
        self._mount_start_actions(preview)

    def _render_preview_sections(self, preview: PreviewPane, session: Any) -> None:
        self._add_goal_section(preview, session)
        self._add_summary_section(preview, session)
        self._add_conversation_section(preview, session)
        self._add_todos_section(preview, session)
        self._add_decisions_section(preview, session)
        self._add_files_section(preview, session)
        self._add_record_section(preview, session)

    def _maybe_load_conversation_excerpt(self, session: Any, generation: int) -> None:
        session_id = str(getattr(session, "session_id", "") or getattr(session, "id", "") or "")
        if not session_id:
            return
        if getattr(session, "conversation_excerpt", ()):
            return
        if not getattr(session, "transcript_path", ""):
            return
        if session_id in self._conversation_cache:
            self._on_conversation_excerpt(
                session_id, self._conversation_cache[session_id], generation
            )
            return
        if session_id in self._conversation_loading:
            return
        self._conversation_loading.add(session_id)
        self._fetch_conversation_excerpt(session_id, generation)

    @work(thread=True)
    def _fetch_conversation_excerpt(self, session_id: str, generation: int) -> None:
        from textual.worker import get_current_worker

        worker = get_current_worker()
        if worker.is_cancelled:
            return
        try:
            excerpt = self._service.conversation_excerpt(self._project_path, session_id)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to fetch conversation excerpt", exc_info=True)
            excerpt = ()
        if worker.is_cancelled:
            return
        self.app.call_from_thread(self._on_conversation_excerpt, session_id, excerpt, generation)

    def _on_conversation_excerpt(
        self,
        session_id: str,
        excerpt: tuple[tuple[str, str], ...],
        generation: int,
    ) -> None:
        self._conversation_loading.discard(session_id)
        if not getattr(self, "_active", False):
            return
        if session_id != self._preview_session_id:
            return
        if not excerpt:
            return
        if len(self._conversation_cache) >= _MAX_CACHE_SIZE:
            first_key = next(iter(self._conversation_cache))
            self._conversation_cache.pop(first_key, None)
        self._conversation_cache[session_id] = excerpt
        from dataclasses import replace

        updated = None
        new_cache: list[Any] = []
        for cache_item in self._sessions_cache:
            item_id = str(
                getattr(cache_item, "session_id", "") or getattr(cache_item, "id", "") or ""
            )
            if item_id == session_id:
                try:
                    cache_item = replace(cache_item, conversation_excerpt=excerpt)
                except TypeError:
                    cache_item = SimpleNamespace(
                        **{**vars(cache_item), "conversation_excerpt": excerpt}
                    )
                updated = cache_item
            new_cache.append(cache_item)
        self._sessions_cache = new_cache
        if updated is not None:
            self._render_preview(updated)

    def _add_goal_section(self, preview: PreviewPane, session: Any) -> None:
        goal = getattr(session, "goal", "") or ""
        if goal:
            preview.add_section(
                strings.tr("SESSION_GOAL"),
                self._truncate_block(goal, max_lines=3, max_chars=220),
            )

    def _add_summary_section(self, preview: PreviewPane, session: Any) -> None:
        summary = getattr(session, "summary", "") or ""
        if summary and summary.strip() != self._entry_title(session).strip():
            preview.add_section(
                strings.tr("SESSION_SUMMARY"),
                self._truncate_block(summary, max_lines=5, max_chars=420),
            )

    def _add_conversation_section(self, preview: PreviewPane, session: Any) -> None:
        conversation = self._format_conversation_excerpt(session)
        if conversation:
            preview.add_section(strings.tr("SESSION_CONVERSATION"), conversation)

    def _add_todos_section(self, preview: PreviewPane, session: Any) -> None:
        todos_pending = getattr(session, "todos_pending", ()) or ()
        todos_done = getattr(session, "todos_done", ()) or ()
        preview.add_section(
            self._next_section_title(), self._format_next_block(todos_pending, todos_done)
        )

    def _add_decisions_section(self, preview: PreviewPane, session: Any) -> None:
        decisions = getattr(session, "decisions", ()) or ()
        if decisions:
            preview.add_section(
                strings.tr("SESSION_DECISIONS", count=len(decisions)),
                self._format_list_block(decisions, limit=3),
            )

    def _add_files_section(self, preview: PreviewPane, session: Any) -> None:
        files = getattr(session, "files_changed", ()) or ()
        if files:
            preview.add_section(
                strings.tr("SESSION_FILES", count=len(files)),
                self._format_files_block(files, limit=8),
            )

    def _add_record_section(self, preview: PreviewPane, session: Any) -> None:
        handoff_id = getattr(session, "handoff_id", "") or ""
        topic_id = getattr(session, "topic_id", "") or ""
        session_path = getattr(session, "path", None)
        transcript_path = getattr(session, "transcript_path", "") or ""
        record_lines = self._build_record_lines(
            getattr(session, "session_id", "") or getattr(session, "id", ""),
            handoff_id,
            session_path,
            transcript_path,
            self._project_path,
        )
        if topic_id:
            record_lines.append(f"Topic: {topic_id}")
        if record_lines:
            preview.add_section(
                strings.tr("SESSION_RECORD"),
                "\n".join(record_lines),
                classes="preview-section-compact",
            )

    @staticmethod
    def _build_record_lines(
        session_id: str,
        handoff_id: str,
        session_path: Any,
        transcript_path: str,
        project_path: "Path | None" = None,
    ) -> list[str]:
        lines: list[str] = []
        if session_id:
            lines.append(f"[dim]{strings.tr('SESSION_ID')}[/]     {session_id}")
        if handoff_id:
            lines.append(f"[dim]{strings.tr('SESSION_HANDOFF')}[/]     {handoff_id}")
        if session_path:
            display_path = str(session_path)
            if project_path:
                try:
                    from pathlib import Path

                    display_path = str(Path(session_path).relative_to(project_path))
                except (ValueError, TypeError):
                    pass
            lines.append(f"[dim]{strings.tr('SESSION_PATH')}[/]     {display_path}")
        if transcript_path:
            lines.append(f"[dim]{strings.tr('SESSION_TRANSCRIPT_CAPTURED')}[/]     yes")
        return lines

    def _build_hero(self, title_text: str, status: str) -> Horizontal:
        title = Static(f"[b]{title_text}[/]", classes="preview-hero-title")
        if badge.is_running(status):
            return Horizontal(
                title,
                Static("  ", classes="preview-hero-spacer"),
                Spinner(color=badge.color_for(status)),
                Static(f"  [bold {badge.color_for(status)}]{strings.tr('RUNNING')}[/]"),
                classes="preview-hero-row",
            )
        return Horizontal(
            title,
            Static(f"   {badge.render(status)}"),
            classes="preview-hero-row",
        )

    @staticmethod
    def _build_meta_lines(
        *,
        provider: str,
        ts_start: str,
        ts_end: str,
        turns: int | None,
        files_count: int,
        returncode: int | None,
    ) -> tuple[str, str]:
        primary_parts: list[str] = (
            [badge.provider_badge(provider, compact=False)] if provider else []
        )
        secondary_parts: list[str] = []
        start_label = ProjectScreen._format_timestamp(ts_start)
        end_label = ProjectScreen._format_end(ts_end)
        if start_label != "—":
            primary_parts.append(f"{start_label} → {end_label}")
        duration = format_duration(ts_start, ts_end)
        if duration != "—":
            primary_parts.append(duration)
        if turns is not None:
            secondary_parts.append(strings.tr("TURNS", count=turns))
        if files_count:
            secondary_parts.append(strings.tr("FILES", count=files_count))
        if returncode is not None:
            secondary_parts.append(strings.tr("EXIT_CODE", code=returncode))
        sep = f"  {glyph.SEP_DOT}  "
        return sep.join(primary_parts), sep.join(secondary_parts)

    @staticmethod
    def _format_todos_block(pending: tuple[str, ...], done: tuple[str, ...]) -> str:
        return format_todos_block(pending, done)

    @classmethod
    def _format_next_block(cls, pending: tuple[str, ...], done: tuple[str, ...]) -> str:
        return format_next_block(pending, done)

    def _mount_resume_actions(self, preview: PreviewPane) -> None:
        installed = self._installed_providers()
        if not installed:
            preview.mount_footer(
                Static(
                    f"{glyph.WARN} {strings.tr('NO_INSTALLED_PROVIDERS')}",
                    classes="resume-empty",
                ),
                Static(
                    f"[dim]d {strings.tr('ACTION_DELETE').lower()}[/]",
                    classes="preview-hint",
                ),
            )
            return

        default = self._default_provider or installed[0]
        ordered = sorted(installed, key=lambda prov: prov != default)
        buttons = []
        for prov in ordered:
            label = strings.tr("CONTINUE_PROVIDER", provider=prov.capitalize())
            if prov == default:
                label = f"[b]{label}[/]"
            btn = Button(label, id=f"resume-{prov}", variant="default")
            buttons.append(btn)
        preview.mount_footer(
            Horizontal(*buttons, classes="resume-row"),
            Static(
                f"[dim]{self._build_resume_hint(installed)}  {glyph.SEP_DOT}  d {strings.tr('ACTION_DELETE').lower()}[/]",
                classes="preview-hint",
            ),
        )

    def _mount_start_actions(self, preview: PreviewPane) -> None:
        installed = self._installed_providers()
        if not installed:
            preview.mount_footer(
                Static(
                    f"{glyph.WARN} {strings.tr('NO_INSTALLED_PROVIDERS')}",
                    classes="resume-empty",
                )
            )
            return

        default = self._default_provider or installed[0]
        ordered = sorted(installed, key=lambda prov: prov != default)
        buttons = []
        for prov in ordered:
            label = strings.tr("START_PROVIDER", provider=prov.capitalize())
            if prov == default:
                label = f"[b]{label}[/]"
            buttons.append(Button(label, id=f"resume-{prov}", variant="default"))
        preview.mount_footer(
            Horizontal(*buttons, classes="resume-row"),
            Static(
                f"[dim]{self._build_resume_hint(installed)}[/]",
                classes="preview-hint",
            ),
        )

    def _installed_providers(self) -> list[str]:
        return [
            getattr(p, "name", "")
            for p in self._service.providers(self._project_path)
            if getattr(p, "installed", False) and getattr(p, "name", "")
        ]

    @staticmethod
    def _build_resume_hint(installed: list[str]) -> str:
        default_text = strings.tr("RESUME_HINT_DEFAULT")
        if default_text == "RESUME_HINT_DEFAULT":
            default_text = "resume default"
        named_text = strings.tr("RESUME_HINT_WITH", provider="{provider}")
        if named_text == "RESUME_HINT_WITH":
            named_text = "resume {provider}"
        default_part = f"{glyph.KEY_ENTER} {default_text}"
        parts = [default_part]
        for prov in installed:
            key = PROVIDER_SHORTCUTS.get(prov)
            if key:
                parts.append(f"{key} {named_text.format(provider=prov)}")
        return f"  {glyph.SEP_DOT}  ".join(parts)

    def _update_chips(
        self,
        chips: FilterChips,
        sessions: list[Any],
        all_sessions: list[Any],
        text: str,
        flags: set[str],
    ) -> None:
        chip_list: list[tuple[str, str]] = []
        if self.filter_provider:
            chip_list.append(
                (
                    self._chip_provider_label(self.filter_provider),
                    f"provider:{self.filter_provider}",
                )
            )
        if text:
            chip_list.append(
                (
                    self._chip_query_label(text),
                    f"q:{text}",
                )
            )
        chip_list.extend((self._chip_flag_label(flag), f"flag:{flag}") for flag in sorted(flags))
        chips.set_chips(chip_list)
        chips.display = bool(chip_list)
        if chip_list:
            chips.set_count(len(sessions), len(all_sessions))
        else:
            chips.clear_count()

    def _update_chrome(
        self,
        *,
        shown: int,
        total: int,
        query: str = "",
        flags: set[str] | None = None,
    ) -> None:
        flags = flags or set()
        project_name = self._project.name if self._project else self._project_path.name
        meta_parts = [
            strings.tr("SESSIONS_COUNT_FILTERED", shown=shown, total=total)
            if (query or self.filter_provider or flags)
            else strings.tr("SESSIONS_COUNT", total=total)
        ]
        if query:
            meta_parts.append(strings.tr("SEARCH_META", query=query))
        running = sum(1 for s in self._sessions_cache if badge.is_running(getattr(s, "status", "")))
        if running:
            meta_parts.append(strings.tr("RUNNING_META", count=running))
        if self.sort_key != self._sort_cycle[0]:
            meta_parts.append(
                strings.tr("SORT_BY", name=strings.tr(SORT_LABELS.get(self.sort_key, "SORT_TIME")))
            )
        top_bar = self._top_bar or self.query_one("#project-top-bar", TopBar)
        top_bar.set_context(
            project_name,
            strings.SESSIONS_TITLE,
            meta=f"  {glyph.SEP_DOT}  ".join(meta_parts),
        )
        status_parts = []
        if self._default_provider:
            status_parts.append(self._default_provider)

        if self._loading_spinner:
            frame = glyph.SPINNER_FRAMES[self._spinner_idx]
            status_parts.append(frame)

        actions: list[tuple[str, str]] = [
            ("enter", strings.tr("ACTION_RESUME")),
        ]
        detail_action = self._detail_toggle_action()
        if detail_action is not None:
            actions.append(detail_action)
        actions.append(("f", strings.tr("ACTION_FILTER_PROVIDER")))
        if self._sessions_cache:
            actions.append(("d", strings.tr("ACTION_DELETE")))
        actions.extend(
            [
                ("s", strings.tr("ACTION_SORT")),
                ("?", strings.tr("ACTION_HELP")),
            ]
        )
        if query or self.filter_provider or flags:
            actions.append(("x", strings.tr("ACTION_CLEAR")))
        actions.append(("esc", self._escape_context_label()))
        cmd_bar = self._command_bar or self.query_one("#project-command-bar", CommandBar)
        cmd_bar.set_actions(
            actions,
            status=f"  {glyph.SEP_DOT}  ".join(status_parts) if status_parts else "",
        )

    @staticmethod
    def _default_actions() -> list[tuple[str, str]]:
        return [
            ("enter", strings.tr("ACTION_RESUME")),
            ("f", strings.tr("ACTION_FILTER_PROVIDER")),
            ("d", strings.tr("ACTION_DELETE")),
            ("?", strings.tr("ACTION_HELP")),
            ("esc", strings.tr("ACTION_BACK")),
        ]

    def _detail_toggle_action(self) -> tuple[str, str] | None:
        if not self.has_class("narrow") or not self._sessions_cache:
            return None
        label = strings.tr("ACTION_LIST") if self.preview_open else strings.tr("ACTION_DETAILS")
        return ("tab", label)

    def _desired_table_layout(self) -> str:
        return "compact" if self.has_class("narrow") else "full"

    def _ensure_table_columns(self, table: DataTable[object]) -> None:
        desired = self._desired_table_layout()
        if table.columns and self._table_layout == desired:
            return
        table.clear(columns=True)
        self._table_layout = desired
        if desired == "compact":
            table.add_column("", key="status", width=2)
            table.add_column(strings.tr("SESSION_TABLE_SUMMARY"), key="summary")
            table.add_column("", key="provider", width=2)
            table.add_column(strings.tr("SESSION_TABLE_WHEN"), key="date", width=12)
            return
        table.add_column("", key="status", width=2)
        table.add_column(strings.tr("SESSION_TABLE_SUMMARY"), key="summary")
        table.add_column(strings.tr("SESSION_TABLE_PROVIDER"), key="provider", width=10)
        table.add_column(strings.tr("SESSION_TABLE_PENDING"), key="pending", width=8)
        table.add_column(strings.tr("SESSION_TABLE_WHEN"), key="date", width=16)

    def _sync_preview_visibility(self) -> None:
        preview = self._safe_query_preview("#session-preview")
        if preview is None:
            return
        narrow = self.has_class("narrow")
        force_visible = not self._sessions_cache
        visible = (not narrow) or self.preview_open or force_visible
        preview.display = visible
        self.set_class(narrow and visible and not force_visible, "preview-open")
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
            return self._table or self.query_one("#session-table", DataTable)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to query session table", exc_info=True)
            return None

    def _refresh_chrome_if_needed(self) -> None:
        if self._command_bar is not None:
            self._update_chrome(
                shown=self._chrome_shown,
                total=self._chrome_total,
                query=self._chrome_query,
                flags=self._chrome_flags,
            )

    @staticmethod
    def _entry_title(session: Any) -> str:
        for value in (
            getattr(session, "title", ""),
            getattr(session, "summary", ""),
            getattr(session, "goal", ""),
            getattr(session, "session_id", ""),
            getattr(session, "id", ""),
        ):
            text = str(value or "").strip()
            if text:
                return text.splitlines()[0]
        untitled = strings.tr("SESSION_UNTITLED")
        return "Untitled session" if untitled == "SESSION_UNTITLED" else untitled

    @staticmethod
    def _title_cell(session: Any) -> str:
        return truncate(ProjectScreen._entry_title(session), max_chars=58)

    @staticmethod
    def _next_cell(session: Any) -> str:
        pending = getattr(session, "todos_pending", ()) or ()
        if pending:
            return f"☐ {len(pending)}"
        return f"[dim]{strings.tr('SESSION_NEXT_CLEAR_SHORT')}[/]"

    @classmethod
    def _when_cell(cls, ts_start: str, ts_end: str) -> str:
        rel = relative_time(ts_start)
        duration = format_duration(ts_start, ts_end)
        if duration in {"—", strings.tr("TIME_RUNNING")}:
            return rel
        return f"{rel}  [dim]{duration}[/]"

    @staticmethod
    def _next_section_title() -> str:
        title = strings.tr("SESSION_NEXT")
        return strings.tr("SESSION_TABLE_PENDING") if title == "SESSION_NEXT" else title

    @staticmethod
    def _chip_provider_label(provider: str) -> str:
        return f"{provider.capitalize()} {glyph.CHIP_CLOSE}"

    @staticmethod
    def _chip_query_label(text: str) -> str:
        action = strings.tr("ACTION_SEARCH")
        return f"{action.capitalize()}: {text} {glyph.CHIP_CLOSE}"

    @staticmethod
    def _chip_flag_label(flag: str) -> str:
        mapping = {
            "running": strings.tr("STATUS_RUNNING"),
            "failed": strings.tr("STATUS_FAILED"),
            "done": strings.tr("STATUS_DONE"),
            "today": strings.tr("BUCKET_TODAY"),
        }
        return f"{mapping.get(flag, flag)} {glyph.CHIP_CLOSE}"

    @staticmethod
    def _truncate_block(text: str, *, max_lines: int, max_chars: int) -> str:
        stripped = str(text).strip()
        if not stripped:
            return ""
        lines = stripped.splitlines()
        clipped = lines[:max_lines]
        body = "\n".join(clipped)
        truncated = len(lines) > max_lines
        if len(body) > max_chars:
            body = body[: max_chars - 1].rstrip() + glyph.ELLIPSIS
            truncated = True
        if truncated:
            body = f"{body}\n[dim]{glyph.ELLIPSIS}[/]"
        return body

    @staticmethod
    def _format_list_block(items: tuple[str, ...], *, limit: int) -> str:
        return format_list_block(items, limit=limit)

    @staticmethod
    def _format_files_block(files: tuple[str, ...], *, limit: int) -> str:
        return format_files_block(files, limit=limit)

    @staticmethod
    def _format_conversation_excerpt(session: Any, *, limit: int = 4) -> str:
        return format_conversation_excerpt(session, limit=limit)

    @staticmethod
    def _format_file_entry(path_value: str) -> str:
        path = Path(path_value)
        name = path.name or path_value
        parent = str(path.parent)
        if parent in (".", ""):
            return name
        return f"{name}  [dim]{parent}[/]"

    def _relative_to_project(self, path_value: Path | str) -> str:
        path = Path(path_value)
        try:
            return str(path.relative_to(self._project_path))
        except ValueError:
            return str(path)

    @classmethod
    def _format_timestamp(cls, value: str) -> str:
        parsed = parse_timestamp(value)
        return parsed.astimezone(UTC).strftime("%Y-%m-%d %H:%M") if parsed else "—"

    @classmethod
    def _format_end(cls, value: str) -> str:
        parsed = parse_timestamp(value)
        return parsed.astimezone(UTC).strftime("%H:%M") if parsed else strings.tr("TIME_RUNNING")

    def _set_search_text(self, value: str) -> None:
        import contextlib

        with contextlib.suppress(Exception):
            search = self._search_input or self.query_one("#filter-search", Input)
            search.value = value

    def _remove_flag(self, flag: str) -> None:
        try:
            inp = self._search_input or self.query_one("#filter-search", Input)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to query search input for flag removal", exc_info=True)
            return
        token = f"!{flag}"
        kept = [t for t in inp.value.split() if t.lower() != token]
        inp.value = " ".join(kept)

    def action_delete_session(self) -> None:
        session = self._cursor_entity()
        if session is None:
            return
        session_id = str(getattr(session, "id", "") or "")
        if not session_id:
            return
        status = (getattr(session, "status", "") or "").lower()

        summary = str(getattr(session, "summary", "") or getattr(session, "goal", "") or "")
        from loghop.store import delete_session, project_paths
        from loghop.tui.screens.confirm import ConfirmModal, session_delete_spec

        def on_result(confirmed: bool | None) -> None:
            if not confirmed:
                return
            try:
                delete_session(project_paths(self._project_path), session_id)
            except (OSError, ValueError) as exc:
                self.app.notify(
                    strings.tr("ERROR_PREFIX", error=str(exc)),
                    severity="error",
                )
                return
            self.app.notify(strings.tr("DELETED_SESSION_NOTICE", id=session_id))
            self._populate()

        self.app.push_screen(
            ConfirmModal(session_delete_spec(session_id, summary, running=status == "running")),
            on_result,
        )

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def _escape_context_label(self) -> str:
        try:
            search = self._search_input or self.query_one("#filter-search", Input)
            if search.has_focus:
                return strings.tr("ACTION_CLOSE_SEARCH")
        except LookupError:
            pass
        if self.has_class("narrow") and self.preview_open and self._sessions_cache:
            return strings.tr("ACTION_CLOSE_PREVIEW")
        return strings.tr("ACTION_BACK")

    def action_escape(self) -> None:
        try:
            search = self._search_input or self.query_one("#filter-search", Input)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to query search input during escape", exc_info=True)
            self.app.pop_screen()
            return
        if search.has_focus:
            table = self._table or self.query_one("#session-table", DataTable)
            table.focus()
            self._populate()
            return
        if self.has_class("narrow") and self.preview_open and self._sessions_cache:
            self.preview_open = False
            table = self._table or self.query_one("#session-table", DataTable)
            table.focus()
            return
        self.app.pop_screen()

    def action_focus_search(self) -> None:
        if self.has_class("narrow") and self.preview_open and self._sessions_cache:
            self.preview_open = False
        search = self._search_input or self.query_one("#filter-search", Input)
        search.focus()
        self._populate()

    def action_toggle_focus(self) -> None:
        if not self.has_class("narrow") or not self._sessions_cache:
            super().action_toggle_focus()
            return
        if self.preview_open:
            self.preview_open = False
            table = self._table or self.query_one("#session-table", DataTable)
            table.focus()
            return
        self.preview_open = True
        preview = self._preview or self.query_one("#session-preview", PreviewPane)
        preview.focus()

    def action_toggle_focus_reverse(self) -> None:
        if not self.has_class("narrow") or not self._sessions_cache:
            super().action_toggle_focus_reverse()
            return
        focused_id = (self.focused.id or "") if self.focused else ""
        if focused_id == self._search_input_id:
            self.preview_open = True
            preview = self._preview or self.query_one("#session-preview", PreviewPane)
            preview.focus()
        elif self.preview_open:
            self.preview_open = False
            table = self._table or self.query_one("#session-table", DataTable)
            table.focus()
        else:
            search = self._search_input or self.query_one("#filter-search", Input)
            search.focus()

    def action_cycle_provider(self) -> None:
        if not self._provider_cycle:
            return
        try:
            idx = self._provider_cycle.index(self.filter_provider or "")
        except ValueError:
            idx = 0
        next_idx = (idx + 1) % len(self._provider_cycle)
        self.filter_provider = self._provider_cycle[next_idx] or ""
        self._populate()

    def action_clear_filters(self) -> None:
        import contextlib

        self.filter_provider = ""
        with contextlib.suppress(Exception):
            search = self._search_input or self.query_one("#filter-search", Input)
            search.value = ""
        self._populate()

    def action_resume_default(self) -> None:
        provider = self._default_provider
        installed = self._installed_providers()
        if provider not in installed and installed:
            provider = installed[0]
        if not provider:
            self.app.notify(strings.tr("NOTIFY_NO_PROVIDERS"), severity="warning")
            return
        self._launch(provider)

    def action_resume_named(self, provider: str) -> None:
        if provider not in self._installed_providers():
            self.app.notify(
                strings.tr("NOTIFY_PROVIDER_NOT_INSTALLED", provider=provider), severity="warning"
            )
            return
        self._launch(provider)

    def _launch(self, provider: str) -> None:
        if provider == "claude":
            from loghop.providers import claude_uses_api_transport

            if claude_uses_api_transport(self._project_path):
                self.app.notify(
                    strings.tr("NOTIFY_CLAUDE_CUSTOM_API_INTERACTIVE_DISABLED"),
                    severity="warning",
                    timeout=10,
                )
                return
        cmd_parts = build_resume_command(self._project_path, provider, interactive=True)
        title = f"loghop — {self._project_path.name}"
        ok = launch_in_new_tab(cmd_parts, cwd=self._project_path, title=title)
        if ok:
            self.app.notify(strings.tr("NOTIFY_OPENED_TERMINAL", provider=provider))
        else:
            cmd = shlex.join(cmd_parts)
            self.app.notify(
                strings.tr("NOTIFY_NO_TERMINAL", cmd=cmd),
                severity="error",
                timeout=10,
            )
