import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, TextIO, cast

from rich import box
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from loghop import env
from loghop.tui.widgets.glyph import FAIL, OK, WARN
from loghop.tui.widgets.glyph import INFO as G_INFO

_THEME = Theme(
    {
        "success": "green bold",
        "info": "cyan",
        "warning": "yellow bold",
        "error": "red bold",
        "muted": "dim",
        "heading": "bold cyan",
        "border": "dim",
        "key": "cyan",
        "accent": "magenta",
    }
)
_Row = str | tuple[str, str]
_TableRow = Sequence[str]


@dataclass(frozen=True)
class TerminalOptions:
    plain: bool = False
    quiet: bool = False
    verbose: bool = False
    json_mode: bool = False
    stream: TextIO = field(default_factory=lambda: sys.stdout)
    error_stream: TextIO = field(default_factory=lambda: sys.stderr)
    input_stream: TextIO = field(default_factory=lambda: sys.stdin)
    force_terminal: bool | None = None
    width: int | None = None


class PlainRenderer:
    def __init__(self, options: TerminalOptions) -> None:
        self.options = options

    def line(self, text: str = "", *, error: bool = False, style: str | None = None) -> None:
        if self.options.quiet and not error:
            return
        target = self.options.error_stream if error else self.options.stream
        print(text, file=target)

    def detail(self, text: str) -> None:
        if self.options.verbose and not self.options.quiet:
            self.line(text)

    def section(self, title: str, rows: Sequence[_Row]) -> None:
        if self.options.quiet:
            return
        self.line(title)
        for row in rows:
            if isinstance(row, tuple):
                self.line(f"  {row[0]}: {row[1]}")
            else:
                self.line(f"  {row}")

    def table(
        self,
        rows: Sequence[_TableRow],
        *,
        headers: Sequence[str] | None = None,
        title: str | None = None,
    ) -> None:
        if self.options.quiet:
            return
        if title:
            self.line(title)
        if headers:
            self.line("  " + " | ".join(headers))
        for row in rows:
            if not row:
                continue
            first, *rest = (str(cell) for cell in row)
            if rest:
                self.line(f"  {first}: {' · '.join(rest)}")
            else:
                self.line(f"  {first}")

    def confirm(self, prompt: str, *, default: bool = True) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        self.line(f"{prompt} {suffix} ")
        answer = self.options.input_stream.readline().strip().lower()
        if answer == "":
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        return False


class RichRenderer:
    def __init__(self, options: TerminalOptions) -> None:
        self.options = options
        self.console = self._build_console(options.stream)
        self.error_console = self._build_console(options.error_stream)

    def _build_console(self, stream: TextIO) -> Console:
        return Console(
            file=stream,
            theme=_THEME,
            markup=False,
            highlight=False,
            no_color=env.no_color(),
            soft_wrap=False,
            force_terminal=self.options.force_terminal,
            width=self.options.width,
        )

    def _console(self, *, error: bool = False) -> Console:
        return self.error_console if error else self.console

    def line(self, text: str = "", *, error: bool = False, style: str | None = None) -> None:
        if self.options.quiet and not error:
            return
        renderable: str | Text = Text(text, style=style) if style else text
        self._console(error=error).print(renderable, markup=False, highlight=False)

    def detail(self, text: str) -> None:
        if self.options.verbose and not self.options.quiet:
            self.line(text, style="muted")

    def section(self, title: str, rows: Sequence[_Row]) -> None:
        if self.options.quiet:
            return
        body = self._render_rows(rows)
        panel = Panel.fit(
            body,
            title=title,
            title_align="left",
            border_style="border",
            box=box.SIMPLE,
            padding=(0, 2),
        )
        self.console.print(panel)

    def table(
        self,
        rows: Sequence[_TableRow],
        *,
        headers: Sequence[str] | None = None,
        title: str | None = None,
    ) -> None:
        if self.options.quiet:
            return
        columns = tuple(headers) if headers else ()
        table = Table(
            *columns,
            title=title,
            title_style="heading",
            title_justify="left",
            box=None,
            show_edge=False,
            pad_edge=False,
            padding=(0, 2),
            expand=False,
            header_style="heading",
            show_lines=len(rows) > 8,  # noqa: PLR2004
        )
        for row in rows:
            table.add_row(*[str(cell) for cell in row])
        self.console.print(table)

    def confirm(self, prompt: str, *, default: bool = True) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        text = Text.assemble((prompt, "heading"), (" ", ""), (suffix, "muted"), (" ", ""))
        self.console.print(text, end="")
        answer = self.options.input_stream.readline().strip().lower()
        if answer == "":
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        return False

    def _render_rows(self, rows: Sequence[_Row]) -> RenderableType:
        if not rows:
            return Text("")
        if all(isinstance(row, tuple) for row in rows):
            tuple_rows = cast(Sequence[tuple[str, str]], rows)
            max_key_len = max(len(k) for k, _ in tuple_rows)
            grid = Table.grid(padding=(0, 2), expand=False)
            grid.add_column(style="key", no_wrap=True, width=max_key_len + 1)
            grid.add_column()
            for key, value in tuple_rows:
                grid.add_row(f"{key}:", value)
            return grid
        rendered = []
        for row in rows:
            if isinstance(row, tuple):
                rendered.append(Text(f"{row[0]}: {row[1]}"))
            else:
                rendered.append(Text(str(row)))
        return Group(*rendered)


@dataclass
class Terminal:
    options: TerminalOptions = field(default_factory=TerminalOptions)

    def __post_init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._result: Any = None
        self._renderer: PlainRenderer | RichRenderer = (
            PlainRenderer(self.options) if self.options.plain else RichRenderer(self.options)
        )

    @property
    def console(self) -> Console | None:
        """Return the Rich Console if a RichRenderer is active, otherwise None."""
        if isinstance(self._renderer, RichRenderer):
            return self._renderer.console
        return None

    @property
    def plain(self) -> bool:
        return self.options.plain

    @property
    def quiet(self) -> bool:
        return self.options.quiet

    @property
    def verbose(self) -> bool:
        return self.options.verbose

    @property
    def json_mode(self) -> bool:
        return self.options.json_mode

    @property
    def stream(self) -> TextIO:
        return self.options.stream

    @property
    def error_stream(self) -> TextIO:
        return self.options.error_stream

    @property
    def input_stream(self) -> TextIO:
        return self.options.input_stream

    def line(self, text: str = "", *, error: bool = False, style: str | None = None) -> None:
        if self.json_mode:
            self._record("line", text=text, error=error, style=style)
            return
        self._renderer.line(text, error=error, style=style)

    def success(self, text: str) -> None:
        if self.json_mode:
            self._record("success", text=text)
            return
        self.line(f"{OK} {text}", style="success")

    def info(self, text: str) -> None:
        if self.json_mode:
            self._record("info", text=text)
            return
        self.line(f"{G_INFO} {text}", style="info")

    def warn(self, text: str) -> None:
        if self.json_mode:
            self._record("warning", text=text, error=True)
            return
        self.line(f"{WARN} {text}", error=True, style="warning")

    def error(self, text: str) -> None:
        if self.json_mode:
            self._record("error", text=text, error=True)
            return
        self.line(f"{FAIL} {text}", error=True, style="error")

    def detail(self, text: str) -> None:
        if self.json_mode:
            self._record("detail", text=text)
            return
        self._renderer.detail(text)

    def panel(self, title: str, lines: list[str]) -> None:
        self.section(title, lines)

    def section(self, title: str, rows: Sequence[_Row]) -> None:
        if self.json_mode:
            self._record("section", title=title, rows=self._normalize_rows(rows))
            return
        self._renderer.section(title, rows)

    def table(
        self,
        rows: Sequence[_TableRow],
        *,
        headers: Sequence[str] | None = None,
        title: str | None = None,
    ) -> None:
        if self.json_mode:
            self._record(
                "table",
                title=title,
                headers=list(headers) if headers is not None else None,
                rows=[[str(cell) for cell in row] for row in rows],
            )
            return
        self._renderer.table(rows, headers=headers, title=title)

    def confirm(self, prompt: str, *, default: bool = True) -> bool:
        if self.json_mode:
            self._record("confirm", prompt=prompt, default=default)
            return default
        return self._renderer.confirm(prompt, default=default)

    def capture_result(self, payload: Any) -> None:
        self._result = payload

    def render_json(self, *, code: int) -> None:
        from loghop.errors import sanitize_error_message

        payload: dict[str, Any] = {
            "schema": "loghop.cli.result",
            "schema_version": 1,
            "ok": code == 0,
            "code": code,
            "events": _sanitize_events(self._events),
        }
        if isinstance(self._result, dict):
            payload.update(
                {
                    k: sanitize_error_message(str(v)) if isinstance(v, str) else v
                    for k, v in self._result.items()
                }
            )
        payload["result"] = self._result
        print(json.dumps(payload, indent=2, sort_keys=True), file=self.stream)

    def _record(self, kind: str, **payload: Any) -> None:
        self._events.append({"type": kind, **payload})

    def _normalize_rows(self, rows: Sequence[_Row]) -> list[dict[str, str] | str]:
        normalized: list[dict[str, str] | str] = []
        for row in rows:
            if isinstance(row, tuple):
                normalized.append({"key": str(row[0]), "value": str(row[1])})
            else:
                normalized.append(str(row))
        return normalized


def _sanitize_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sanitize absolute paths in JSON event payloads for non-interactive output."""
    from loghop.errors import sanitize_error_message

    sanitized: list[dict[str, Any]] = []
    for event in events:
        entry: dict[str, Any] = {}
        for key, value in event.items():
            if isinstance(value, str):
                entry[key] = sanitize_error_message(value)
            else:
                entry[key] = value
        sanitized.append(entry)
    return sanitized
