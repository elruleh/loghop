from __future__ import annotations

import pytest

from loghop.tui.screens.confirm import (
    ConfirmModal,
    ConfirmSpec,
    project_purge_spec,
    project_unregister_spec,
    session_delete_spec,
)


class TestConfirmSpec:
    def test_frozen(self) -> None:
        spec = ConfirmSpec(title="t", message="m", confirm_label="ok", cancel_label="no")
        with pytest.raises(AttributeError):
            spec.title = "x"  # type: ignore[misc]

    def test_default_warning_empty(self) -> None:
        spec = ConfirmSpec(title="t", message="m", confirm_label="ok", cancel_label="no")
        assert spec.warning == ""

    def test_warning_set(self) -> None:
        spec = ConfirmSpec(
            title="t", message="m", confirm_label="ok", cancel_label="no", warning="careful"
        )
        assert spec.warning == "careful"


class TestProjectUnregisterSpec:
    def test_has_title_and_message(self) -> None:
        spec = project_unregister_spec("myproj", "/tmp/p")
        assert "myproj" in spec.message
        assert "/tmp/p" in spec.message
        assert spec.title
        assert spec.confirm_label
        assert spec.cancel_label

    def test_no_warning(self) -> None:
        spec = project_unregister_spec("x", "/x")
        assert spec.warning == ""


class TestProjectPurgeSpec:
    def test_includes_warning(self) -> None:
        spec = project_purge_spec("myproj", "/tmp/p")
        assert spec.warning != ""
        assert "myproj" in spec.message or "/tmp/p" in spec.message

    def test_has_destructive_labels(self) -> None:
        spec = project_purge_spec("x", "/x")
        assert spec.confirm_label
        assert spec.cancel_label


class TestSessionDeleteSpec:
    def test_with_summary(self) -> None:
        spec = session_delete_spec("S-001", "did stuff")
        assert "S-001" in spec.message
        assert "did stuff" in spec.message

    def test_without_summary_shows_placeholder(self) -> None:
        spec = session_delete_spec("S-002", "")
        assert "S-002" in spec.message

    def test_running_session_includes_warning(self) -> None:
        spec = session_delete_spec("S-003", "stuck", running=True)
        assert spec.warning != ""


class TestConfirmModalInteractions:
    @pytest.mark.anyio
    async def test_dismiss_true_on_ok(self) -> None:
        from loghop.tui.app import create_app

        results: list[bool] = []
        spec = ConfirmSpec(
            title="Delete?", message="Sure?", confirm_label="Delete", cancel_label="Cancel"
        )
        app = create_app()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.push_screen(ConfirmModal(spec), results.append)
            await pilot.pause()
            await pilot.click("#btn-confirm-ok")
            await pilot.pause()
        assert results == [True]

    @pytest.mark.anyio
    async def test_dismiss_false_on_cancel(self) -> None:
        from loghop.tui.app import create_app

        results: list[bool] = []
        spec = ConfirmSpec(
            title="Delete?", message="Sure?", confirm_label="Delete", cancel_label="Cancel"
        )
        app = create_app()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.push_screen(ConfirmModal(spec), results.append)
            await pilot.pause()
            await pilot.click("#btn-confirm-cancel")
            await pilot.pause()
        assert results == [False]

    @pytest.mark.anyio
    async def test_y_key_confirms(self) -> None:
        from loghop.tui.app import create_app

        results: list[bool] = []
        spec = ConfirmSpec(
            title="Delete?", message="Sure?", confirm_label="Delete", cancel_label="Cancel"
        )
        app = create_app()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.push_screen(ConfirmModal(spec), results.append)
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
        assert results == [True]

    @pytest.mark.anyio
    async def test_n_key_cancels(self) -> None:
        from loghop.tui.app import create_app

        results: list[bool] = []
        spec = ConfirmSpec(
            title="Delete?", message="Sure?", confirm_label="Delete", cancel_label="Cancel"
        )
        app = create_app()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.push_screen(ConfirmModal(spec), results.append)
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
        assert results == [False]

    @pytest.mark.anyio
    async def test_escape_cancels(self) -> None:
        from loghop.tui.app import create_app

        results: list[bool] = []
        spec = ConfirmSpec(
            title="Delete?", message="Sure?", confirm_label="Delete", cancel_label="Cancel"
        )
        app = create_app()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.push_screen(ConfirmModal(spec), results.append)
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
        assert results == [False]

    @pytest.mark.anyio
    async def test_renders_warning(self) -> None:
        from loghop.tui.app import create_app

        spec = ConfirmSpec(
            title="Purge?",
            message="Delete all?",
            confirm_label="Purge",
            cancel_label="Cancel",
            warning="This cannot be undone",
        )
        app = create_app()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.push_screen(ConfirmModal(spec))
            await pilot.pause()
            warning = app.screen.query_one("#confirm-warning")
            assert "cannot be undone" in str(warning.renderable)

    @pytest.mark.anyio
    async def test_no_warning_widget(self) -> None:
        from loghop.tui.app import create_app

        spec = ConfirmSpec(
            title="Delete?",
            message="Sure?",
            confirm_label="Delete",
            cancel_label="Cancel",
        )
        app = create_app()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.push_screen(ConfirmModal(spec))
            await pilot.pause()
            assert len(app.screen.query("#confirm-warning")) == 0
