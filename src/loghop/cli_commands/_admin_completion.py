import argparse

from loghop.terminal import Terminal

_COMPLETION_COMMANDS = (
    "init",
    "goal",
    "run",
    "sessions",
    "projects",
    "doctor",
    "tui",
    "handoff",
    "resume",
    "install",
    "uninstall",
    "completion",
    "providers",
    "journal",
    "wrap",
)


def handle_completion(args: argparse.Namespace, term: Terminal) -> int:
    shell = args.shell
    commands = _collect_top_level_commands()
    if shell == "bash":
        script = _bash_completion(commands)
    elif shell == "zsh":
        script = _zsh_completion(commands)
    else:
        script = _fish_completion(commands)
    print(script)  # noqa: T201
    term.capture_result({"shell": shell, "commands": commands})
    return 0


def _collect_top_level_commands() -> list[str]:
    from loghop.cli_parser import build_parser

    parser = build_parser()
    actions = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    choices = actions[0].choices if actions else {}
    return [cmd for cmd in _COMPLETION_COMMANDS if cmd in choices]


def _bash_completion(commands: list[str]) -> str:
    cmds = " ".join(commands)
    return f"""# loghop bash completion — source from ~/.bashrc
_loghop_complete() {{
  local cur prev
  COMPREPLY=()
  cur="${{COMP_WORDS[COMP_CWORD]}}"
  if [ "${{COMP_CWORD}}" -eq 1 ]; then
    COMPREPLY=( $(compgen -W "{cmds}" -- "$cur") )
    return 0
  fi
  COMPREPLY=( $(compgen -f -- "$cur") )
}}
complete -F _loghop_complete loghop
"""


def _zsh_completion(commands: list[str]) -> str:
    cmds = " ".join(commands)
    return f"""# loghop zsh completion — drop into a directory in $fpath
#compdef loghop
_loghop() {{
  local -a cmds
  cmds=({cmds})
  if (( CURRENT == 2 )); then
    _describe 'command' cmds
  else
    _files
  fi
}}
_loghop "$@"
"""


def _fish_completion(commands: list[str]) -> str:
    lines = ["# loghop fish completion — save under ~/.config/fish/completions/loghop.fish"]
    lines.extend(f"complete -c loghop -n '__fish_use_subcommand' -a {cmd}" for cmd in commands)
    return "\n".join(lines) + "\n"
