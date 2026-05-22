from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from loghop.tui import strings


@dataclass(frozen=True)
class ConfirmSpec:
    """All the user-facing copy needed to render a confirm modal."""

    title: str
    message: str
    confirm_label: str
    cancel_label: str
    warning: str = ""


class ConfirmModal(ModalScreen[bool]):
    """Reusable destructive-action confirmation. Returns True on confirm."""

    BINDINGS = [  # noqa: RUF012
        Binding("escape", "cancel", "Cancel"),
        Binding("n", "cancel", "No", show=True),
        Binding("y", "confirm", "Yes", show=True),
        Binding("s", "confirm", "Yes", show=False),
    ]

    def __init__(self, spec: ConfirmSpec) -> None:
        super().__init__()
        self._spec = spec

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-container"):
            yield Static(self._spec.title, id="confirm-title")
            yield Static(self._spec.message, id="confirm-message")
            if self._spec.warning:
                yield Static(self._spec.warning, id="confirm-warning")
            with Horizontal(id="confirm-buttons"):
                yield Button(
                    self._spec.cancel_label,
                    id="btn-confirm-cancel",
                    variant="default",
                )
                yield Button(
                    self._spec.confirm_label,
                    id="btn-confirm-ok",
                    variant="error",
                )

    def on_mount(self) -> None:
        # Default focus on Cancel — pressing Enter by inertia must not destroy.
        self.query_one("#btn-confirm-cancel", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-confirm-ok":
            self.dismiss(True)
        elif event.button.id == "btn-confirm-cancel":
            self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


def project_unregister_spec(name: str, path: str) -> ConfirmSpec:
    return ConfirmSpec(
        title=strings.tr("CONFIRM_UNREGISTER_TITLE"),
        message=strings.tr("CONFIRM_UNREGISTER_MSG", name=name, path=path),
        confirm_label=strings.tr("CONFIRM_UNREGISTER_BTN"),
        cancel_label=strings.tr("CONFIRM_CANCEL"),
    )


def project_purge_spec(name: str, path: str) -> ConfirmSpec:
    return ConfirmSpec(
        title=strings.tr("CONFIRM_PURGE_TITLE"),
        message=strings.tr("CONFIRM_PURGE_MSG", name=name, path=path),
        confirm_label=strings.tr("CONFIRM_PURGE_BTN"),
        cancel_label=strings.tr("CONFIRM_CANCEL"),
        warning=strings.tr("CONFIRM_PURGE_WARN"),
    )


def session_delete_spec(session_id: str, summary: str, *, running: bool = False) -> ConfirmSpec:
    return ConfirmSpec(
        title=strings.tr("CONFIRM_DELETE_SESSION_TITLE"),
        message=strings.tr("CONFIRM_DELETE_SESSION_MSG", id=session_id, summary=summary or "—"),
        confirm_label=strings.tr("CONFIRM_DELETE_SESSION_BTN"),
        cancel_label=strings.tr("CONFIRM_CANCEL"),
        warning=strings.tr("CONFIRM_DELETE_RUNNING_WARN") if running else "",
    )
