"""Tiny undo manager: stack of zero-arg callables."""

from collections.abc import Callable


class UndoStack:
    """Holds a single undo callable per slot. Last push wins."""

    def __init__(self) -> None:
        self._action: tuple[str, Callable[[], None]] | None = None

    def push(self, label: str, action: Callable[[], None]) -> None:
        self._action = (label, action)

    def pop(self) -> tuple[str, Callable[[], None]] | None:
        action = self._action
        self._action = None
        return action

    def clear(self) -> None:
        self._action = None

    @property
    def has_action(self) -> bool:
        return self._action is not None

    @property
    def label(self) -> str | None:
        return self._action[0] if self._action else None
