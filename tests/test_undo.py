from __future__ import annotations

from loghop.tui.undo import UndoStack


class TestUndoStack:
    def test_initially_empty(self) -> None:
        stack = UndoStack()
        assert not stack.has_action
        assert stack.label is None

    def test_push_and_pop(self) -> None:
        stack = UndoStack()
        called = []
        stack.push("test", lambda: called.append(1))
        assert stack.has_action
        assert stack.label == "test"
        result = stack.pop()
        assert result is not None
        assert result[0] == "test"
        result[1]()
        assert called == [1]

    def test_pop_clears_action(self) -> None:
        stack = UndoStack()
        stack.push("x", lambda: None)
        stack.pop()
        assert not stack.has_action
        assert stack.label is None

    def test_pop_empty_returns_none(self) -> None:
        stack = UndoStack()
        assert stack.pop() is None

    def test_clear(self) -> None:
        stack = UndoStack()
        stack.push("x", lambda: None)
        stack.clear()
        assert not stack.has_action
        assert stack.label is None

    def test_clear_empty_ok(self) -> None:
        stack = UndoStack()
        stack.clear()

    def test_last_push_wins(self) -> None:
        stack = UndoStack()
        stack.push("first", lambda: None)
        stack.push("second", lambda: None)
        assert stack.label == "second"
        result = stack.pop()
        assert result is not None
        assert result[0] == "second"

    def test_push_overwrites_previous_callable(self) -> None:
        stack = UndoStack()
        calls: list[str] = []
        stack.push("a", lambda: calls.append("a"))
        stack.push("b", lambda: calls.append("b"))
        action = stack.pop()
        assert action is not None
        action[1]()
        assert calls == ["b"]

    def test_has_action_after_push(self) -> None:
        stack = UndoStack()
        stack.push("x", lambda: None)
        assert stack.has_action is True

    def test_label_returns_none_after_pop(self) -> None:
        stack = UndoStack()
        stack.push("gone", lambda: None)
        stack.pop()
        assert stack.label is None

    def test_multiple_clears_safe(self) -> None:
        stack = UndoStack()
        stack.push("a", lambda: None)
        stack.clear()
        stack.clear()
        assert not stack.has_action
