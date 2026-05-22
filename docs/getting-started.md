# Getting Started

Get loghop installed and running your first session in under 5 minutes.

## Prerequisites

- Python 3.12 or later
- Git
- Linux, macOS, or Windows (via Command Prompt/cmd shims)
- One of: [Claude Code](https://docs.anthropic.com/en/docs/claude-code) or [Codex](https://platform.openai.com/docs/guides/codex)

## Installation

### Option 1: pipx (recommended)

```bash
pipx install loghop
```

### Option 2: uv

```bash
uv tool install loghop
```

### Option 3: pip

```bash
pip install loghop
```

For the terminal UI:

```bash
pipx install 'loghop[tui]'
```

## First Setup

Navigate to any Git repository where you want to use AI coding assistants:

```bash
cd ~/projects/my-app
```

Initialize loghop:

```bash
loghop init
```

You'll be asked about optional integrations:
- **Claude hooks** — Auto-capture sessions via Claude's session lifecycle
- **Codex shim** — Wrap direct `codex` calls for auto-capture
- **Prompt block** — Add a shared context block to provider prompts

You can skip all of these and use `loghop run` directly.

## Your First Session

Start a session with your default provider:

```bash
loghop run
```

Or specify a provider:

```bash
loghop run --provider claude
loghop run --provider codex
```

Set a goal so the next session knows what you're working on:

```bash
loghop goal "Add user authentication"
```

The next time you run `loghop run`, it will build context from all previous sessions.

## What Just Happened?

```
.loghop/
├── config.toml          # Project goal and settings
├── handoffs/            # Context for next session
├── sessions/           # Captured session history
└── timeline.jsonl       # Timeline across all sessions
```

Every session is captured, redacted, and stored. The next session builds a handoff automatically.

## Next Steps

- [Switch between providers](how-to/switch-providers.md) — Learn how to use Claude and Codex interchangeably
- [Command reference](reference/commands.md) — Explore all available commands
- [Troubleshoot issues](how-to/troubleshooting.md) — Common problems and solutions
