from typing import Any, ClassVar

from loghop import __version__
from loghop.install._config import load_tui_preferences, save_tui_preferences
from loghop.tui.services import TuiService
from loghop.tui.undo import UndoStack

try:
    from textual.app import App
    from textual.binding import Binding

    HAS_TEXTUAL = True
except ModuleNotFoundError:
    HAS_TEXTUAL = False

    class App:  # type: ignore[no-redef]
        COMMANDS: ClassVar[set[Any]] = set()

        def __class_getitem__(cls, item: Any) -> type:
            return cls

    class Binding:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass


if HAS_TEXTUAL:
    from loghop.tui.commands import LoghopCommands
    from loghop.tui.screens.add_folder import AddFolderModal
    from loghop.tui.screens.help import HelpScreen
    from loghop.tui.screens.home import HomeScreen
    from loghop.tui.screens.project import ProjectScreen
    from loghop.tui.themes import THEME_REGISTRY, css_vars_for
else:
    LoghopCommands = None  # type: ignore
    THEME_REGISTRY = {}
    css_vars_for = None  # type: ignore
    HomeScreen = None  # type: ignore
    ProjectScreen = None  # type: ignore
    AddFolderModal = None  # type: ignore
    HelpScreen = None  # type: ignore


class LoghopApp(App[None]):  # Static class with optional Textual dependency stubs
    CSS_PATH = "styles/loghop.tcss"
    TITLE = "loghop"
    SUB_TITLE = ""

    BINDINGS = [  # noqa: RUF012
        Binding("m", "command_palette", "Menu", show=True),
    ]

    COMMANDS = App.COMMANDS | {LoghopCommands} if HAS_TEXTUAL else set()

    def __init__(self, service: TuiService | None = None, *, global_view: bool = True) -> None:
        super().__init__()
        self.tui_service = service or TuiService()
        self.global_view = global_view
        self.undo_stack = UndoStack()
        for theme, _ in THEME_REGISTRY.values():
            self.register_theme(theme)

    def get_css_variables(self) -> dict[str, str]:
        css_vars: dict[str, str] = super().get_css_variables()
        if css_vars_for is not None:
            theme_vars = css_vars_for(str(self.theme))
            for key, value in theme_vars.items():
                css_vars[key.lstrip("$")] = value
        return css_vars

    def get_system_commands(self, screen: Any) -> Any:
        for command in super().get_system_commands(screen):
            if command.title == "Change theme":
                continue
            yield command

    def set_language(self, language: str) -> None:
        from loghop.tui.i18n import set_language

        set_language(language)
        save_tui_preferences(language=language)
        for screen in self.screen_stack:
            if hasattr(screen, "refresh_translations"):
                screen.refresh_translations()
            else:
                screen.refresh(recompose=True)
                refresh = getattr(screen, "action_refresh", None)
                if callable(refresh):
                    refresh()

    def on_mount(self) -> None:
        for name in list(self.available_themes):
            if name not in THEME_REGISTRY:
                self.unregister_theme(name)
        from loghop.tui import strings
        from loghop.tui.i18n import set_language

        prefs = load_tui_preferences()
        saved_theme = prefs.get("theme", "")
        self.theme = saved_theme if saved_theme in THEME_REGISTRY else "loghopclassicdark"
        saved_language = prefs.get("language", "")
        if saved_language:
            set_language(saved_language)

        self.notify(
            strings.tr("APP_INTRO", version=__version__),
            timeout=2,
        )
        current_root = self.tui_service.current_project_root()
        if self.global_view or current_root is None:
            self.push_screen(HomeScreen(self.tui_service))
        else:
            self.push_screen(ProjectScreen(self.tui_service, str(current_root)))

    def open_project(self, project_path: str) -> None:
        self.push_screen(ProjectScreen(self.tui_service, project_path))

    def open_add_folder(self) -> None:
        self.push_screen(AddFolderModal(self.tui_service))

    def open_help(self) -> None:
        self.push_screen(HelpScreen())


def run(
    *,
    global_view: bool = False,
    service: TuiService | None = None,
    tui_debug: bool = False,
) -> int:
    if tui_debug:
        import os
        from pathlib import Path

        debug_log = Path(".loghop/tui-debug.log")
        try:
            debug_log.parent.mkdir(parents=True, exist_ok=True)
            os.environ["TEXTUAL_LOG"] = str(debug_log)
        except OSError:
            pass

    app = _create_app(service=service, global_view=global_view)
    app.run()
    return 0


def _create_app(service: TuiService | None = None, *, global_view: bool = True) -> Any:
    if not HAS_TEXTUAL:
        raise RuntimeError("The loghop Textual app requires the optional `textual` package.")
    return LoghopApp(service=service, global_view=global_view)


def create_app(service: TuiService | None = None, *, global_view: bool = True) -> Any:
    return _create_app(service=service, global_view=global_view)
