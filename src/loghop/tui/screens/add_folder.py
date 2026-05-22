import contextlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.suggester import Suggester
from textual.widgets import Button, DirectoryTree, Input, ListItem, ListView, Static

from loghop.gittools import GitRepo
from loghop.logging import get_logger
from loghop.store import init_project
from loghop.store._registry import load_registry, register_project
from loghop.tui import strings
from loghop.tui.widgets import badge, glyph

_LOGGER = get_logger()

_RECENT_LIMIT = 5
_RECENT_PATH_MAX = 48


def _shorten_path(path: Path, *, limit: int = _RECENT_PATH_MAX) -> str:
    """Collapse $HOME and middle-truncate so long paths fit on one line."""
    raw = str(path)
    home = str(Path.home())
    if home and raw.startswith(home):
        raw = "~" + raw[len(home) :]
    if len(raw) <= limit:
        return raw
    parts = [p for p in raw.split("/") if p]
    if len(parts) >= 3:  # noqa: PLR2004
        head = "" if raw.startswith("/") else parts[0]
        head_part = "/" + parts[0] if raw.startswith("/") else head
        tail = "/".join(parts[-2:])
        candidate = (
            f"{head_part}/{glyph.ELLIPSIS}/{tail}" if head_part else f"{glyph.ELLIPSIS}/{tail}"
        )
        if len(candidate) <= limit:
            return candidate
    if limit <= 0:
        return ""
    if limit <= len(glyph.ELLIPSIS):
        return glyph.ELLIPSIS[:limit]
    return glyph.ELLIPSIS + raw[-(limit - len(glyph.ELLIPSIS)) :]


class _FilteredDirectoryTree(DirectoryTree):
    """DirectoryTree that hides dot-entries and unreadable paths."""

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        out: list[Path] = []
        for p in paths:
            try:
                if p.name.startswith("."):
                    continue
                out.append(p)
            except OSError:
                continue
        return out


class _PathSuggester(Suggester):
    """Suggests directory completions for the current input."""

    def __init__(self) -> None:
        super().__init__(use_cache=False, case_sensitive=True)

    async def get_suggestion(self, value: str) -> str | None:
        if not value:
            return None
        try:
            expanded = Path(value).expanduser()
        except (RuntimeError, ValueError):
            return None
        if value.endswith("/"):
            base = expanded
            prefix = ""
        else:
            base = expanded.parent if expanded.parent != expanded else expanded
            prefix = expanded.name
        if not base.exists() or not base.is_dir():
            return None
        try:
            for entry in sorted(base.iterdir()):
                if entry.is_dir() and entry.name.startswith(prefix):
                    return value + entry.name[len(prefix) :]
        except OSError:
            return None
        return None


@dataclass(frozen=True)
class _Validation:
    """Pure result of classifying a raw path. Drives the modal's render."""

    kind: str  # empty | invalid | missing | not_dir | existing | new
    icon: str
    color: str  # ok | err | muted
    message_key: str
    folder: Path | None
    can_submit: bool
    primary_label_key: str


@dataclass(frozen=True)
class _Recent:
    path: Path
    exists: bool


def _classify(raw: str) -> _Validation:
    """Pure classifier — same input always yields same _Validation."""
    raw = (raw or "").strip()
    if not raw:
        return _Validation(
            kind="empty",
            icon=glyph.INFO,
            color="muted",
            message_key="ADD_VALIDATION_EMPTY",
            folder=None,
            can_submit=False,
            primary_label_key="ADD_PRIMARY_ADD",
        )
    try:
        folder = Path(raw).expanduser().resolve()
    except OSError:
        return _Validation(
            kind="invalid",
            icon=glyph.FAIL,
            color="err",
            message_key="ADD_VALIDATION_MISSING",
            folder=None,
            can_submit=False,
            primary_label_key="ADD_PRIMARY_ADD",
        )
    if not folder.exists():
        return _Validation(
            kind="missing",
            icon=glyph.FAIL,
            color="err",
            message_key="ADD_VALIDATION_MISSING",
            folder=folder,
            can_submit=False,
            primary_label_key="ADD_PRIMARY_ADD",
        )
    if not folder.is_dir():
        return _Validation(
            kind="not_dir",
            icon=glyph.FAIL,
            color="err",
            message_key="ADD_VALIDATION_NOT_DIR",
            folder=folder,
            can_submit=False,
            primary_label_key="ADD_PRIMARY_ADD",
        )
    repo = GitRepo.from_cwd(folder)
    if repo is None or repo.root.resolve() != folder:
        return _Validation(
            kind="not_git_root",
            icon=glyph.FAIL,
            color="err",
            message_key="ADD_VALIDATION_NOT_GIT_ROOT",
            folder=folder,
            can_submit=False,
            primary_label_key="ADD_PRIMARY_ADD",
        )
    if (folder / ".loghop" / "config.toml").exists():
        return _Validation(
            kind="existing",
            icon=glyph.OK,
            color="ok",
            message_key="ADD_VALIDATION_OK_EXISTING",
            folder=folder,
            can_submit=True,
            primary_label_key="ADD_PRIMARY_ADD",
        )
    return _Validation(
        kind="new",
        icon=glyph.OK,
        color="ok",
        message_key="ADD_VALIDATION_OK_INIT",
        folder=folder,
        can_submit=True,
        primary_label_key="ADD_PRIMARY_INIT",
    )


class AddFolderModal(ModalScreen[bool]):
    """Add (or initialize) a project folder, with live validation + recents."""

    BINDINGS = [  # noqa: RUF012
        Binding("escape", "close", "Close"),
        Binding("ctrl+b", "toggle_browse", "Browse", show=False, priority=True),
        Binding("ctrl+1", "pick_recent(0)", "", show=False, priority=True),
        Binding("ctrl+2", "pick_recent(1)", "", show=False, priority=True),
        Binding("ctrl+3", "pick_recent(2)", "", show=False, priority=True),
        Binding("ctrl+4", "pick_recent(3)", "", show=False, priority=True),
        Binding("ctrl+5", "pick_recent(4)", "", show=False, priority=True),
    ]

    def __init__(self, service: Any) -> None:
        super().__init__()
        self._service = service
        self._recent: list[_Recent] = []
        self._validation: _Validation = _classify("")
        self._busy = False
        self._browse_open = False

    def compose(self) -> ComposeResult:
        with Vertical(id="add-container"):
            yield Static(strings.ADD_TITLE, id="add-title")
            yield Input(
                placeholder=strings.ADD_PLACEHOLDER,
                id="add-path",
                suggester=_PathSuggester(),
            )
            yield Static("", id="add-status", classes="muted")
            yield Static("", id="add-hint", classes="muted")

            yield _FilteredDirectoryTree(str(Path.home()), id="add-tree")

            yield Static(strings.ADD_RECENT_LABEL, id="add-recent-label")
            yield ListView(id="add-recent-list")

            with Horizontal(id="add-buttons"):
                yield Button(strings.tr("ADD_CANCEL"), id="btn-cancel", variant="default")
                yield Button(
                    strings.ADD_PRIMARY_ADD,
                    id="btn-add",
                    variant="primary",
                )

    def on_mount(self) -> None:
        self._populate_recent()
        self._apply_validation(_classify(""))
        self._set_browse_open(False)

    def refresh_translations(self) -> None:
        """Update translatable strings on the screen without recomposing."""
        from loghop.tui import strings

        self.query_one("#add-title", Static).update(strings.ADD_TITLE)
        self.query_one("#add-path", Input).placeholder = strings.ADD_PLACEHOLDER
        self.query_one("#add-recent-label", Static).update(strings.ADD_RECENT_LABEL)
        self.query_one("#btn-cancel", Button).label = strings.tr("ADD_CANCEL")
        self.query_one("#btn-add", Button).label = strings.tr(self._validation.primary_label_key)

        # Update status
        self._apply_validation(self._validation)

        # Update recents if populated
        self._populate_recent()

        # Update hint
        hint = self.query_one("#add-hint", Static)
        if self._browse_open:
            hint.update(strings.tr("ADD_BROWSE_HINT"))
        else:
            hint.update(strings.tr("ADD_AUTOCOMPLETE_HINT"))

    # -------- browse tree --------

    def _set_browse_open(self, open_: bool) -> None:
        self._browse_open = open_
        tree = self.query_one("#add-tree", _FilteredDirectoryTree)
        tree.display = open_
        # Recents and browse are alternative ways to pick a path — hide one
        # when the other is in use so the modal doesn't overflow.
        recent_label = self.query_one("#add-recent-label", Static)
        recent_list = self.query_one("#add-recent-list", ListView)
        if open_:
            recent_label.display = False
            recent_list.display = False
        elif self._recent:
            recent_label.display = True
            recent_list.display = True

        hint = self.query_one("#add-hint", Static)
        if open_:
            hint.update(strings.tr("ADD_BROWSE_HINT"))
        else:
            hint.update(strings.tr("ADD_AUTOCOMPLETE_HINT"))

    def action_toggle_browse(self) -> None:
        if self._busy:
            return
        new_state = not self._browse_open
        self._set_browse_open(new_state)
        if new_state:
            tree = self.query_one("#add-tree", _FilteredDirectoryTree)
            with contextlib.suppress(Exception):
                tree.reload()
            tree.focus()
        else:
            self.query_one("#add-path", Input).focus()

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        path = Path(event.path)
        path_input = self.query_one("#add-path", Input)
        path_input.value = str(path)
        self._apply_validation(_classify(str(path)))

    # -------- recent list --------

    def _populate_recent(self) -> None:
        listview = self.query_one("#add-recent-list", ListView)
        listview.clear()
        try:
            entries = load_registry()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to load registry for recent list", exc_info=True)
            entries = []
        seen: set[Path] = set()
        recents: list[_Recent] = []
        for entry in entries:
            raw = entry.path
            if not raw:
                continue
            try:
                p = Path(str(raw)).expanduser().resolve()
            except OSError:
                continue
            if p in seen:
                continue
            seen.add(p)
            recents.append(_Recent(path=p, exists=p.is_dir()))
        self._recent = recents[:_RECENT_LIMIT]

        if not self._recent:
            self.query_one("#add-recent-label", Static).display = False
            listview.display = False
            return

        self.query_one("#add-recent-label", Static).display = True
        listview.display = True
        for idx, rec in enumerate(self._recent, start=1):
            shortened = _shorten_path(rec.path)
            num = f"[dim]{idx}[/]"
            if rec.exists:
                line = f"{num}  {shortened}"
            else:
                missing = strings.tr("ADD_RECENT_MISSING")
                err = badge.role_color("error")
                line = f"{num}  [strike]{shortened}[/]  [{err}]{glyph.FAIL} {missing}[/]"
            listview.append(ListItem(Static(line)))

    # -------- events --------

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "add-path":
            self._apply_validation(_classify(event.value))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "add-path":
            self._submit()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is None:
            return
        self._pick_recent(idx)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self._busy:
            return
        button_id = event.button.id or ""
        if button_id == "btn-cancel":
            self.dismiss(False)
        elif button_id == "btn-add":
            self._submit()

    def action_pick_recent(self, idx: int) -> None:
        self._pick_recent(idx)

    def _pick_recent(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._recent):
            return
        rec = self._recent[idx]
        if not rec.exists:
            with contextlib.suppress(Exception):
                self.app.bell()
            return
        path_input = self.query_one("#add-path", Input)
        path_input.value = str(rec.path)
        path_input.focus()
        self._apply_validation(_classify(str(rec.path)))

    # -------- validation rendering --------

    def _apply_validation(self, validation: _Validation) -> None:
        self._validation = validation
        status = self.query_one("#add-status", Static)
        primary = self.query_one("#btn-add", Button)
        primary.label = strings.tr(validation.primary_label_key)
        primary.disabled = not validation.can_submit

        body = strings.tr(validation.message_key)
        color = self._color_for(validation.color)
        line = f"[{color}]{validation.icon} {body}[/]"
        if validation.folder is not None and validation.kind in {"existing", "new", "missing"}:
            line += f"\n[dim]{validation.folder}[/]"
        status.update(line)

    @staticmethod
    def _color_for(code: str) -> str:
        if code == "ok":
            return badge.role_color("success")
        if code == "err":
            return badge.role_color("error")
        return "dim"

    # -------- submit (async init) --------

    def _submit(self) -> None:
        if self._busy:
            return
        path_input = self.query_one("#add-path", Input)
        validation = _classify(path_input.value)
        self._apply_validation(validation)
        if not validation.can_submit or validation.folder is None:
            with contextlib.suppress(Exception):
                self.app.bell()
            return

        folder = validation.folder
        if validation.kind == "existing":
            try:
                register_project(folder)
            except Exception as exc:  # noqa: BLE001
                self._on_init_error(folder, exc)
                return
            self.app.notify(strings.tr("ADD_NOTIFY_EXISTING", folder=folder))
            self.dismiss(True)
            return

        self._begin_busy(folder)
        self._run_init(folder)

    def _begin_busy(self, folder: Path) -> None:
        self._busy = True
        status = self.query_one("#add-status", Static)
        status.update(
            f"[dim]{glyph.SPINNER_FRAMES[0]} {strings.tr('ADD_INITIALIZING', folder=folder)}[/]"
        )
        for btn_id in ("btn-add", "btn-cancel"):
            with contextlib.suppress(Exception):
                self.query_one(f"#{btn_id}", Button).disabled = True

    def _end_busy(self) -> None:
        self._busy = False
        for btn_id in ("btn-add", "btn-cancel"):
            with contextlib.suppress(Exception):
                self.query_one(f"#{btn_id}", Button).disabled = False

    @work(thread=True, exclusive=True)
    def _run_init(self, folder: Path) -> None:
        try:
            init_project(folder)
        except Exception as exc:  # noqa: BLE001
            self.app.call_from_thread(self._on_init_error, folder, exc)
            return
        self.app.call_from_thread(self._on_init_success, folder)

    def _on_init_success(self, folder: Path) -> None:
        self._end_busy()
        self.app.notify(strings.tr("ADD_NOTIFY_INITIALIZED", folder=folder))
        self.dismiss(True)

    def _on_init_error(self, folder: Path, exc: BaseException) -> None:
        self._end_busy()
        status = self.query_one("#add-status", Static)
        err_color = badge.role_color("error")
        message = self._humanize_error(folder, exc)
        status.update(f"[{err_color}]{glyph.FAIL} {message}[/]")

    @staticmethod
    def _humanize_error(folder: Path, exc: BaseException) -> str:
        if isinstance(exc, PermissionError):
            return strings.tr("ADD_ERROR_PERMISSION", folder=folder)
        if isinstance(exc, FileNotFoundError):
            return strings.tr("ADD_VALIDATION_MISSING")
        if isinstance(exc, NotADirectoryError):
            return strings.tr("ADD_VALIDATION_NOT_DIR")
        if isinstance(exc, ValueError) and "git repository root" in str(exc).lower():
            return strings.tr("ADD_ERROR_NOT_GIT_ROOT")
        if isinstance(exc, OSError):
            return strings.tr("ADD_ERROR_OS", error=str(exc))
        return strings.tr("ERROR_PREFIX", error=str(exc))

    def action_close(self) -> None:
        if self._busy:
            return
        self.dismiss(False)
