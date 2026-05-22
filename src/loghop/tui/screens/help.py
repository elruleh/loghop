from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from loghop.tui import strings
from loghop.tui.models import PROVIDER_SHORTCUTS


def _global_rows() -> list[tuple[str, str]]:
    return [
        ("?", strings.tr("HELP_TOGGLE")),
        ("m  /  ctrl+p", strings.tr("HELP_MENU")),
        ("/", strings.tr("HELP_FOCUS_SEARCH")),
        ("q", strings.tr("HELP_QUIT")),
        ("esc", strings.tr("HELP_BACK_CLOSE")),
    ]


def _list_rows() -> list[tuple[str, str]]:
    return [
        ("↑ ↓  /  j k", strings.tr("HELP_MOVE")),
        ("home  /  end", strings.tr("HELP_TOP_BOTTOM")),
        ("tab", strings.tr("HELP_SWITCH_PANEL")),
        ("enter", strings.tr("HELP_PRIMARY")),
        ("r", strings.tr("HELP_REFRESH")),
    ]


def _project_rows() -> list[tuple[str, str]]:
    return [
        ("a", strings.tr("HELP_ADD_PROJECT")),
        ("d", strings.tr("HELP_REMOVE_PROJECT")),
    ]


def _session_rows() -> list[tuple[str, str]]:
    provider_keys = " / ".join(PROVIDER_SHORTCUTS.values())
    return [
        ("enter", strings.tr("HELP_RESUME_DEFAULT")),
        (provider_keys, strings.tr("HELP_RESUME_PROVIDER")),
        ("f", strings.tr("HELP_FILTER_PROVIDER")),
        ("x", strings.tr("HELP_CLEAR_FILTERS")),
        ("b  /  esc", strings.tr("HELP_BACK_PROJECTS")),
    ]


def _filter_rows() -> list[tuple[str, str]]:
    return [
        ("!current", strings.tr("HELP_FILTER_CURRENT")),
        ("!missing", strings.tr("HELP_FILTER_MISSING")),
        ("!running", strings.tr("HELP_FILTER_RUNNING")),
        ("!failed", strings.tr("HELP_FILTER_FAILED")),
        ("!done", strings.tr("HELP_FILTER_DONE")),
        ("!today", strings.tr("HELP_FILTER_TODAY")),
    ]


def _section(title: str, rows: list[tuple[str, str]]) -> str:
    head = f"[b]{title}[/]"
    body = "\n".join(f"  [b]{key:<14}[/] {desc}" for key, desc in rows)
    return f"{head}\n{body}"


class HelpScreen(ModalScreen[None]):
    """Help overlay listing keybindings by section."""

    BINDINGS = [  # noqa: RUF012
        Binding("escape", "close", "Close"),
        Binding("question_mark", "close", "Close"),
        Binding("q", "close", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-container"):
            yield Static(strings.HELP_TITLE, id="help-title")
            with VerticalScroll(id="help-body"):
                yield Static(
                    _section(strings.tr("HELP_GLOBAL"), _global_rows()),
                    id="help-sec-global",
                    classes="help-section",
                )
                yield Static(
                    _section(strings.tr("HELP_LISTS"), _list_rows()),
                    id="help-sec-lists",
                    classes="help-section",
                )
                yield Static(
                    _section(strings.tr("HELP_PROJECTS"), _project_rows()),
                    id="help-sec-projects",
                    classes="help-section",
                )
                yield Static(
                    _section(strings.tr("HELP_SESSIONS"), _session_rows()),
                    id="help-sec-sessions",
                    classes="help-section",
                )
                yield Static(
                    _section(strings.tr("HELP_SEARCH_FILTERS"), _filter_rows()),
                    id="help-sec-filters",
                    classes="help-section",
                )
            yield Static(f"[dim]{strings.tr('HELP_CLOSE_HINT')}[/]", id="help-hint")

    def refresh_translations(self) -> None:
        """Update translatable strings on the screen without recomposing."""
        from loghop.tui import strings

        self.query_one("#help-title", Static).update(strings.HELP_TITLE)
        self.query_one("#help-sec-global", Static).update(
            _section(strings.tr("HELP_GLOBAL"), _global_rows())
        )
        self.query_one("#help-sec-lists", Static).update(
            _section(strings.tr("HELP_LISTS"), _list_rows())
        )
        self.query_one("#help-sec-projects", Static).update(
            _section(strings.tr("HELP_PROJECTS"), _project_rows())
        )
        self.query_one("#help-sec-sessions", Static).update(
            _section(strings.tr("HELP_SESSIONS"), _session_rows())
        )
        self.query_one("#help-sec-filters", Static).update(
            _section(strings.tr("HELP_SEARCH_FILTERS"), _filter_rows())
        )
        self.query_one("#help-hint", Static).update(f"[dim]{strings.tr('HELP_CLOSE_HINT')}[/]")

    def action_close(self) -> None:
        self.dismiss(None)
