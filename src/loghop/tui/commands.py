"""Product-aware command palette provider."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from textual.command import DiscoveryHit, Hit, Hits, Provider

from loghop.install._config import save_tui_preferences
from loghop.tui import strings
from loghop.tui.models import PROVIDER_SHORTCUTS
from loghop.tui.themes import HARBOR_DARK, HARBOR_LIGHT, paired_theme

if TYPE_CHECKING:
    from loghop.tui.services import TuiService


@dataclass(frozen=True)
class _CommandSpec:
    display: str
    command: Callable[[], None]
    help: str
    aliases: tuple[str, ...] = ()

    @property
    def search_text(self) -> str:
        return " ".join((self.display, self.help, *self.aliases))


class LoghopCommands(Provider):
    """Provides categorized loghop actions to Textual's command palette."""

    async def discover(self) -> Hits:
        for spec in self._build_commands(include_projects=False):
            yield DiscoveryHit(
                spec.display,
                spec.command,
                text=spec.display,
                help=spec.help,
            )

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for spec in self._build_commands(include_projects=True):
            score = matcher.match(spec.search_text)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(spec.display),
                    spec.command,
                    text=spec.search_text,
                    help=spec.help,
                )

    def _build_commands(self, *, include_projects: bool) -> list[_CommandSpec]:
        commands = [*self._static_commands(), *self._context_commands()]
        if include_projects:
            commands.extend(self._project_commands())
        return commands

    def _static_commands(self) -> list[_CommandSpec]:
        return [
            _CommandSpec(
                strings.tr("CMD_HELP"),
                self._show_help,
                strings.tr("CMD_HELP_HELP"),
                ("help", "ayuda", "shortcuts", "atajos", "?"),
            ),
            _CommandSpec(
                strings.tr("CMD_THEME_DARK"),
                self._theme("loghopclassicdark"),
                strings.tr("CMD_THEME_DARK_HELP"),
                ("theme", "tema", "dark", "oscuro", "neutral", "dark mode"),
            ),
            _CommandSpec(
                strings.tr("CMD_THEME_LIGHT"),
                self._theme("loghopclassiclight"),
                strings.tr("CMD_THEME_LIGHT_HELP"),
                ("theme", "tema", "light", "claro", "neutral", "light mode"),
            ),
            _CommandSpec(
                strings.tr("CMD_THEME_HARBOR_DARK"),
                self._theme(HARBOR_DARK.name),
                strings.tr("CMD_THEME_HARBOR_DARK_HELP"),
                ("theme", "tema", "harbor", "dark", "oscuro", "teal", "mar"),
            ),
            _CommandSpec(
                strings.tr("CMD_THEME_HARBOR_LIGHT"),
                self._theme(HARBOR_LIGHT.name),
                strings.tr("CMD_THEME_HARBOR_LIGHT_HELP"),
                ("theme", "tema", "harbor", "light", "claro", "teal", "bruma"),
            ),
            _CommandSpec(
                strings.tr("CMD_THEME_TOGGLE"),
                self._toggle_theme,
                strings.tr("CMD_THEME_TOGGLE_HELP"),
                ("theme", "tema", "toggle", "alternar", "cambiar"),
            ),
            _CommandSpec(
                strings.tr("CMD_LANG_EN"),
                self._language("en"),
                strings.tr("CMD_LANG_EN_HELP"),
                ("language", "idioma", "english", "inglés", "ingles", "en"),
            ),
            _CommandSpec(
                strings.tr("CMD_LANG_ES"),
                self._language("es"),
                strings.tr("CMD_LANG_ES_HELP"),
                ("language", "idioma", "spanish", "español", "espanol", "es"),
            ),
            _CommandSpec(
                strings.tr("CMD_SYSTEM_QUIT"),
                self._quit,
                strings.tr("CMD_SYSTEM_QUIT_HELP"),
                ("quit", "exit", "salir", "cerrar", "q"),
            ),
        ]

    def _context_commands(self) -> list[_CommandSpec]:
        screen = self.app.screen
        commands: list[_CommandSpec] = []

        self._add_if_has(
            commands,
            screen,
            "action_focus_search",
            strings.tr("CMD_VIEW_SEARCH"),
            strings.tr("CMD_VIEW_SEARCH_HELP"),
            ("search", "buscar", "filtro", "filter", "/"),
        )
        self._add_if_has(
            commands,
            screen,
            "action_refresh",
            strings.tr("CMD_VIEW_RELOAD"),
            strings.tr("CMD_VIEW_RELOAD_HELP"),
            ("refresh", "reload", "recargar", "actualizar", "r"),
        )
        self._add_if_has(
            commands,
            screen,
            "action_clear_filters",
            strings.tr("CMD_FILTER_CLEAR"),
            strings.tr("CMD_FILTER_CLEAR_HELP"),
            ("clear", "limpiar", "reset", "x"),
        )
        self._add_if_has(
            commands,
            screen,
            "action_cycle_provider",
            strings.tr("CMD_FILTER_PROVIDER"),
            strings.tr("CMD_FILTER_PROVIDER_HELP"),
            ("provider", "proveedor", "filter", "f"),
        )
        self._add_session_commands(commands, screen)
        self._add_project_commands(commands, screen)
        self._add_if_has(
            commands,
            screen,
            "action_escape",
            strings.tr("CMD_NAV_BACK"),
            strings.tr("CMD_NAV_BACK_HELP"),
            ("back", "volver", "escape", "esc", "b"),
        )
        return commands

    @staticmethod
    def _add_if_has(
        commands: list[_CommandSpec],
        target: Any,
        action_name: str,
        display: str,
        help_text: str,
        aliases: tuple[str, ...],
    ) -> None:
        action = getattr(target, action_name, None)
        if callable(action):
            commands.append(_CommandSpec(display, action, help_text, aliases))

    def _add_session_commands(self, commands: list[_CommandSpec], screen: Any) -> None:
        if not callable(getattr(screen, "action_resume_default", None)):
            return
        commands.append(
            _CommandSpec(
                strings.tr("CMD_SESSION_RESUME_DEFAULT"),
                screen.action_resume_default,
                strings.tr("CMD_SESSION_RESUME_DEFAULT_HELP"),
                ("resume", "reanudar", "continuar", "enter"),
            )
        )
        commands.extend(
            _CommandSpec(
                strings.tr("CMD_SESSION_RESUME_WITH", provider=provider),
                lambda provider=provider: screen.action_resume_named(provider),  # type: ignore[misc]  # Textual command callbacks allow provider-bound lambdas
                strings.tr("CMD_SESSION_RESUME_WITH_HELP", provider=provider),
                ("resume", "reanudar", "continuar", provider),
            )
            for provider in PROVIDER_SHORTCUTS
        )

    def _add_project_commands(self, commands: list[_CommandSpec], screen: Any) -> None:
        self._add_if_has(
            commands,
            screen,
            "action_add_folder",
            strings.tr("CMD_PROJECT_ADD"),
            strings.tr("CMD_PROJECT_ADD_HELP"),
            ("add", "project", "folder", "añadir", "agregar", "carpeta", "init", "a"),
        )
        self._add_if_has(
            commands,
            screen,
            "action_delete_project",
            strings.tr("CMD_PROJECT_REMOVE"),
            strings.tr("CMD_PROJECT_REMOVE_HELP"),
            ("remove", "delete", "borrar", "eliminar", "project", "d"),
        )
        self._add_if_has(
            commands,
            screen,
            "action_undo",
            strings.tr("CMD_PROJECT_UNDO"),
            strings.tr("CMD_PROJECT_UNDO_HELP"),
            ("undo", "deshacer", "u"),
        )

    def _project_commands(self) -> list[_CommandSpec]:
        service: TuiService = self.app.tui_service  # type: ignore[attr-defined]  # LoghopApp injects tui_service dynamically
        try:
            projects = service.projects()
        except Exception:  # noqa: BLE001
            return []
        commands: list[_CommandSpec] = []
        for project in projects:
            if not getattr(project, "exists", False):
                continue
            commands.append(
                _CommandSpec(
                    strings.tr("CMD_PROJECT_OPEN", name=project.name),
                    self._open_project(str(project.path)),
                    str(project.path),
                    (
                        "open",
                        "abrir",
                        "project",
                        "proyecto",
                        str(project.name),
                        str(project.path),
                    ),
                )
            )
        return commands

    # -- callables --

    def _show_help(self) -> None:
        self.app.open_help()  # type: ignore[attr-defined]  # LoghopApp method is dynamic from Textual base

    def _theme(self, theme: str) -> Callable[[], None]:
        def _do() -> None:
            self.app.theme = theme
            save_tui_preferences(theme=theme)

        return _do

    def _language(self, language: str) -> Callable[[], None]:
        def _do() -> None:
            self.app.set_language(language)  # type: ignore[attr-defined]  # LoghopApp method is dynamic from Textual base

        return _do

    def _toggle_theme(self) -> None:
        next_theme = paired_theme(str(self.app.theme))
        self.app.theme = next_theme
        save_tui_preferences(theme=next_theme)

    def _quit(self) -> None:
        self.app.exit()

    def _open_project(self, path: str) -> Callable[[], None]:
        def _do() -> None:
            self.app.open_project(path)  # type: ignore[attr-defined]  # LoghopApp method is dynamic from Textual base

        return _do
