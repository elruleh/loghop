from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from loghop.tui.app import create_app
from loghop.tui.i18n import set_language
from loghop.tui.screens.add_folder import (
    AddFolderModal,
    _classify,
    _FilteredDirectoryTree,
    _Recent,
    _shorten_path,
    _Validation,
)
from loghop.tui.services import TuiService


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


# ── Pure unit tests ──


class TestClassify:
    def test_empty_input(self) -> None:
        v = _classify("")
        assert v.kind == "empty"
        assert v.can_submit is False
        assert v.folder is None

    def test_whitespace_only(self) -> None:
        v = _classify("   ")
        assert v.kind == "empty"

    def test_none_input(self) -> None:
        v = _classify(None)  # type: ignore[arg-type]
        assert v.kind == "empty"

    def test_nonexistent_path(self, tmp_path: Path) -> None:
        v = _classify(str(tmp_path / "nope"))
        assert v.kind == "missing"
        assert v.can_submit is False
        assert v.folder is not None

    def test_file_not_dir(self, tmp_path: Path) -> None:
        f = tmp_path / "afile"
        f.write_text("x")
        v = _classify(str(f))
        assert v.kind == "not_dir"
        assert v.can_submit is False

    def test_existing_loghop_project(self, tmp_path: Path) -> None:
        from conftest import init_repo

        root = init_repo(tmp_path)
        v = _classify(str(root))
        assert v.kind == "existing"
        assert v.can_submit is True

    def test_new_dir_no_loghop(self, tmp_path: Path) -> None:
        d = tmp_path / "newdir"
        d.mkdir()
        _git_init(d)
        v = _classify(str(d))
        assert v.kind == "new"
        assert v.can_submit is True

    def test_tilde_expansion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        d = tmp_path / "proj"
        d.mkdir()
        _git_init(d)
        v = _classify("~/proj")
        assert v.kind == "new"
        assert v.can_submit is True

    def test_rejects_non_git_folder(self, tmp_path: Path) -> None:
        d = tmp_path / "plain"
        d.mkdir()
        v = _classify(str(d))
        assert v.kind == "not_git_root"
        assert v.can_submit is False

    def test_rejects_git_subdirectory(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        _git_init(root)
        sub = root / "nested"
        sub.mkdir()
        v = _classify(str(sub))
        assert v.kind == "not_git_root"
        assert v.can_submit is False

    def test_primary_label_existing(self, tmp_path: Path) -> None:
        from conftest import init_repo

        root = init_repo(tmp_path)
        v = _classify(str(root))
        assert v.primary_label_key == "ADD_PRIMARY_ADD"

    def test_primary_label_new(self, tmp_path: Path) -> None:
        d = tmp_path / "newdir"
        d.mkdir()
        _git_init(d)
        v = _classify(str(d))
        assert v.primary_label_key == "ADD_PRIMARY_INIT"

    def test_message_key_missing(self, tmp_path: Path) -> None:
        v = _classify(str(tmp_path / "nope"))
        assert "MISSING" in v.message_key

    def test_message_key_not_dir(self, tmp_path: Path) -> None:
        f = tmp_path / "afile"
        f.write_text("x")
        v = _classify(str(f))
        assert "NOT_DIR" in v.message_key

    def test_empty_validation_fields(self) -> None:
        v = _classify("")
        assert v.icon
        assert v.color == "muted"
        assert v.message_key == "ADD_VALIDATION_EMPTY"

    def test_new_validation_fields(self, tmp_path: Path) -> None:
        d = tmp_path / "newdir"
        d.mkdir()
        _git_init(d)
        v = _classify(str(d))
        assert v.color == "ok"
        assert "OK_INIT" in v.message_key


class TestShortenPath:
    def test_short_path_unchanged(self) -> None:
        p = Path("/tmp/x")
        assert _shorten_path(p) == str(p)

    def test_home_collapsed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        result = _shorten_path(tmp_path / "project")
        assert result.startswith("~")

    def test_long_path_truncated(self) -> None:
        long_path = Path("/a" * 100 + "/b" * 100 + "/c" * 100)
        result = _shorten_path(long_path, limit=30)
        assert len(result) <= 30

    def test_limit_respected(self) -> None:
        long_path = Path("/very/long/path/that/exceeds/the/limit/seriously")
        result = _shorten_path(long_path, limit=20)
        assert len(result) <= 20

    def test_short_with_tilde(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        result = _shorten_path(tmp_path, limit=48)
        assert result == "~"


class TestValidationDataclass:
    def test_frozen(self) -> None:
        v = _Validation(
            kind="empty",
            icon="i",
            color="muted",
            message_key="K",
            folder=None,
            can_submit=False,
            primary_label_key="P",
        )
        with pytest.raises(AttributeError):
            v.kind = "x"  # type: ignore[misc]

    def test_defaults(self) -> None:
        v = _Validation(
            kind="empty",
            icon="i",
            color="muted",
            message_key="K",
            folder=None,
            can_submit=False,
            primary_label_key="P",
        )
        assert v.folder is None
        assert v.can_submit is False


class TestRecentDataclass:
    def test_fields(self) -> None:
        r = _Recent(path=Path("/tmp/x"), exists=True)
        assert r.path == Path("/tmp/x")
        assert r.exists is True

    def test_frozen(self) -> None:
        r = _Recent(path=Path("/tmp/x"), exists=True)
        with pytest.raises(AttributeError):
            r.exists = False  # type: ignore[misc]


class TestFilteredDirectoryTree:
    def test_hides_dotfiles(self, tmp_path: Path) -> None:
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "visible").mkdir()
        tree = object.__new__(_FilteredDirectoryTree)
        paths = [Path(".hidden"), Path("visible")]
        result = list(tree.filter_paths(paths))
        assert Path("visible") in result
        assert Path(".hidden") not in result

    def test_handles_oserror(self, tmp_path: Path) -> None:
        tree = object.__new__(_FilteredDirectoryTree)
        bad = MagicMock()
        bad.name = MagicMock(side_effect=OSError("nope"))
        result = list(tree.filter_paths([bad]))
        assert result == []


class TestHumanizeError:
    def test_permission_error(self) -> None:
        result = AddFolderModal._humanize_error(Path("/tmp"), PermissionError("no"))
        assert result

    def test_file_not_found(self) -> None:
        result = AddFolderModal._humanize_error(Path("/tmp"), FileNotFoundError())
        assert result

    def test_not_a_directory(self) -> None:
        result = AddFolderModal._humanize_error(Path("/tmp"), NotADirectoryError())
        assert result

    def test_os_error(self) -> None:
        result = AddFolderModal._humanize_error(Path("/tmp"), OSError("io"))
        assert result

    def test_git_root_error(self) -> None:
        result = AddFolderModal._humanize_error(
            Path("/tmp"),
            ValueError("loghop can only be initialized at a Git repository root"),
        )
        assert "Git" in result or "Git" in result.capitalize()

    def test_generic(self) -> None:
        result = AddFolderModal._humanize_error(Path("/tmp"), RuntimeError("bad"))
        assert "bad" in result


class TestColorFor:
    def test_ok_returns_color(self) -> None:
        result = AddFolderModal._color_for("ok")
        assert result
        assert result != "dim"

    def test_err_returns_color(self) -> None:
        result = AddFolderModal._color_for("err")
        assert result
        assert result != "dim"

    def test_other_returns_dim(self) -> None:
        assert AddFolderModal._color_for("muted") == "dim"


# ── Async TUI tests ──


def _make_mock_service() -> Any:
    set_language("en")
    service = MagicMock(spec=TuiService)
    service.projects.return_value = []
    service.sessions.return_value = []
    service.timeline.return_value = []
    service.providers.return_value = []
    service.default_provider.return_value = "codex"
    service.current_project_root.return_value = None
    return service


class TestAddFolderAsync:
    def test_modal_opens_and_closes(self) -> None:
        service = _make_mock_service()

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                await pilot.press("a")
                await pilot.pause()
                modal = app.query_one(AddFolderModal)
                modal.action_close()
                await pilot.pause()

        asyncio.run(run())

    def test_cancel_button(self) -> None:
        service = _make_mock_service()

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                await pilot.press("a")
                await pilot.pause()
                from textual.widgets import Button

                cancel = app.query_one("#btn-cancel", Button)
                cancel.press()
                await pilot.pause()

        asyncio.run(run())

    def test_input_path_validation(self) -> None:
        service = _make_mock_service()

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                await pilot.press("a")
                await pilot.pause()
                from textual.widgets import Input

                path_input = app.query_one("#add-path", Input)
                path_input.value = "/nonexistent/path/xyz"
                await pilot.pause()
                from textual.widgets import Static

                status = app.query_one("#add-status", Static)
                assert status.renderable is not None

        asyncio.run(run())

    def test_toggle_browse(self) -> None:
        service = _make_mock_service()

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                await pilot.press("a")
                await pilot.pause()
                from textual.widgets import ListView

                tree = app.query_one("#add-tree")
                recent_list = app.query_one("#add-recent-list", ListView)
                assert tree.display is False
                assert recent_list.display is False

                await pilot.press("ctrl+b")
                await pilot.pause()
                assert tree.display is True

        asyncio.run(run())

    def test_path_suggester_returns_none_for_empty(self) -> None:
        from loghop.tui.screens.add_folder import _PathSuggester

        async def run() -> None:
            suggester = _PathSuggester()
            result = await suggester.get_suggestion("")
            assert result is None

        asyncio.run(run())

    def test_path_suggester_returns_none_for_nonexistent(self) -> None:
        from loghop.tui.screens.add_folder import _PathSuggester

        async def run() -> None:
            suggester = _PathSuggester()
            result = await suggester.get_suggestion("/nonexistent_path_xyz")
            assert result is None

        asyncio.run(run())

    def test_path_suggester_suggests_subdirectory(self, tmp_path: Path) -> None:
        from loghop.tui.screens.add_folder import _PathSuggester

        subdir = tmp_path / "alpha"
        subdir.mkdir()

        async def run() -> None:
            suggester = _PathSuggester()
            result = await suggester.get_suggestion(str(tmp_path) + "/")
            assert result is not None
            assert "alpha" in result

        asyncio.run(run())

    def test_pick_recent_missing_does_nothing(self) -> None:
        service = _make_mock_service()

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                await pilot.press("a")
                await pilot.pause()
                modal = app.query_one(AddFolderModal)
                modal._recent = [_Recent(path=Path("/nonexistent"), exists=False)]
                modal.action_pick_recent(0)
                await pilot.pause()

        asyncio.run(run())

    def test_pick_recent_out_of_bounds(self) -> None:
        service = _make_mock_service()

        async def run() -> None:
            app = create_app(service=service)
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                await pilot.press("a")
                await pilot.pause()
                modal = app.query_one(AddFolderModal)
                modal._recent = []
                modal.action_pick_recent(0)
                modal.action_pick_recent(5)
                await pilot.pause()

        asyncio.run(run())
