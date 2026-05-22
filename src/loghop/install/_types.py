from dataclasses import dataclass
from pathlib import Path

GLOBAL_CONFIG_FILENAME = "config.toml"
INIT_INSTALL_KEYS = (
    "install_claude_hooks",
    "install_codex_shim",
    "install_prompt_block",
)

_LOGHOP_PROMPT_FILENAME = "loghop-prompt.md"
_LOGHOP_PROMPT_BODY = """# loghop session metadata

Before ending any conversation in this project, emit a final fenced block in
this exact format. loghop parses it to populate session summary, decisions,
and TODOs reliably (without it, loghop falls back to brittle regex heuristics).

```loghop
summary: <one-paragraph recap of what was done this session>
decisions:
  - <each load-bearing decision made, one per line>
todos_done:
  - <each task completed in this session>
todos_pending:
  - <each task left for the next session>
```

The block is read by tooling and never shown to the user, so prefer clarity
over brevity. Do not skip it even when the conversation was short. Omit
sections that are genuinely empty rather than emitting placeholder text.
"""


@dataclass(frozen=True)
class InstallReport:
    path: Path
    # "created" | "updated" | "unchanged" | "removed" | "skipped"
    # | "would-create" | "would-update" | "would-remove"  (dry-run)
    # | "error"  (precondition failed; install must abort)
    action: str
    detail: str = ""


@dataclass(frozen=True)
class InstallStatus:
    claude_hooks: bool
    codex_shim: bool
    prompt_block: bool

    @property
    def any(self) -> bool:
        return self.claude_hooks or self.codex_shim or self.prompt_block

    @property
    def all(self) -> bool:
        return self.claude_hooks and self.codex_shim and self.prompt_block


@dataclass(frozen=True)
class InitInstallChoices:
    install_claude_hooks: bool
    install_codex_shim: bool
    install_prompt_block: bool

    def as_dict(self) -> dict[str, bool]:
        return {
            "install_claude_hooks": self.install_claude_hooks,
            "install_codex_shim": self.install_codex_shim,
            "install_prompt_block": self.install_prompt_block,
        }
