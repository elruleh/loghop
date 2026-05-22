# Command Reference

Complete reference for all loghop commands.

## Core Commands

### `loghop init`

Initialize a project for loghop.

```bash
loghop init [options]
```

**Options:**

| Flag | Description |
|------|-------------|
| `--no-prompt` | Skip interactive prompts, assume defaults |
| `--force-reinstall` | Reinstall all integration components |
| `--dry-run` | Show what would be done without doing it |

**Description:** Creates `.loghop/` directory, registers project, optionally installs hooks/shims/prompt block. Idempotent — safe to re-run.

---

### `loghop run [<project>] [--provider <provider>]`

Start or resume a session within the active topic.

```bash
loghop run [project] [options]
loghop run --provider claude
loghop run --provider codex
```

**Options:**

| Flag | Description |
|------|-------------|
| `--provider <name>` | Override auto-detected provider (claude, codex) |
| `--timeout <seconds>` | Session timeout (default: 300) |
| `--goal <text>` | Set session goal |
| `--topic <id>` | Attach this run to an existing topic |
| `--new-topic` | Start a new topic from the goal |
| `--no-topic` | Do not attach this run to a topic |
| `--interactive` | Run the provider interactively with stdin attached |

**Description:** Resolves the active work topic, builds a handoff from topic/project timeline, launches provider, captures transcript, writes handoff for next session.

---

### `loghop goal ["<text>"]`

Set, show, or clear the project goal.

```bash
loghop goal
loghop goal "Add user authentication"
loghop goal --clear
```

**Description:** Stores goal in `.loghop/config.toml`. Included in every handoff so the provider knows what you're working on.

---

### `loghop status`

Show project status.

```bash
loghop status
```

**Output:** Current project, provider, session count, goal, recent activity.

---

## Topic Management

### `loghop topics`

Manage work topics that group related sessions.

```bash
loghop topics
loghop topics show T-001
loghop topics switch T-001
loghop topics rename T-001 "Ship auth"
loghop topics close T-001
```

| Subcommand | Description |
|------------|-------------|
| `list` | List topics, marking the active one |
| `show <id>` | Show topic details and member sessions |
| `switch <id>` | Make a topic active for subsequent runs |
| `rename <id> <title>` | Rename a topic |
| `close <id>` | Close a topic and clear it if active |

---

## Session Management

### `loghop sessions`

Browse and manage recorded sessions.

```bash
loghop sessions list
loghop sessions show <id>
loghop sessions show --latest
loghop sessions annotate <id> --summary "<text>"
loghop sessions annotate <id> --decision "<text>" --todo "<text>"
loghop sessions reconcile
loghop sessions delete <id>
```

| Subcommand | Description |
|------------|-------------|
| `list` | List all sessions with status |
| `show [<id>]` | Show session details and summary (`--latest` for most recent) |
| `annotate [<id>]` | Add summary, decisions, pending todos, or completed todos |
| `reconcile` | Fix stuck sessions (running >1h) |
| `delete [<id>]` | Delete session and artifacts (`--latest` for most recent) |

---

### `loghop handoff`

Manage handoff documents.

```bash
loghop handoff list
loghop handoff show <id>
loghop handoff build
loghop handoff run
```

| Subcommand | Description |
|------------|-------------|
| `list` | List available handoffs |
| `show <id>` | Display handoff content |
| `build` | Create a new handoff from timeline |
| `run` | Build a handoff and launch the provider |

---

### `loghop resume [<project>]`

Resume from the last useful session.

```bash
loghop resume
loghop resume other-project
```

**Description:** Finds the most recent useful session in the active topic, creates a handoff from it, and starts a new session. Skips failed, interrupted, or empty sessions. If no active topic exists, loghop creates or reuses a topic from the goal.

---

## Project Management

### `loghop projects`

Manage registered projects.

```bash
loghop projects list
loghop projects show <path>
loghop projects remove <path>
loghop projects purge <path>
loghop projects cleanup
loghop projects prune
```

| Subcommand | Description |
|------------|-------------|
| `list` | List all registered projects |
| `show <path>` | Show project details |
| `remove <path>` | Unregister project (keep data) |
| `purge <path>` | Unregister and delete data |
| `cleanup` | Remove missing projects from registry |
| `prune` | Alias for `cleanup` |

---

### `loghop journal [--since <duration>] [--all]`

View session journal.

```bash
loghop journal
loghop journal --since 7d
loghop journal --all --since 30d
```

**Options:**

| Flag | Description |
|------|-------------|
| `--since <duration>` | Filter by duration (7d, 12h, etc.) |
| `--all` | Include all projects, not just current |

---

### `loghop timeline`

View shared timeline across providers.

```bash
loghop timeline
loghop timeline --since 12h
loghop timeline --provider claude
loghop timeline --all-status --limit 100
```

**Options:**

| Flag | Description |
|------|-------------|
| `--since <duration>` | Filter by time |
| `--provider <name>` | Filter by provider |
| `--all-status` | Include failed, interrupted, empty, and auth-failure events |
| `--limit <n>` | Maximum events to show (default: 50) |

---

## Provider Commands

### `loghop providers`

List available providers.

```bash
loghop providers
```

**Output:** Shows which providers (claude, codex) are detected on PATH and their status.

---

### `loghop wrap {claude,codex} [args...]`

Transparent wrapper for provider commands.

```bash
alias claude='loghop wrap claude'
alias codex='loghop wrap codex'

# Now these auto-capture
claude "fix the auth bug"
codex "add tests"
```

---

## Installation Commands

### `loghop install`

First-time global install.

```bash
loghop install
```

**Description:** Sets up global config and optional integrations. Use before `loghop init`.

---

### `loghop uninstall [-y] [--purge]`

Remove loghop artifacts.

```bash
loghop uninstall -y
loghop uninstall -y --purge
loghop uninstall --dry-run
```

**Options:**

| Flag | Description |
|------|-------------|
| `-y, --yes` | Skip confirmation |
| `--purge` | Delete the entire `~/.loghop` directory |
| `--keep-config` | Preserve `~/.loghop/config.toml` |
| `--dry-run` | Preview without writing |

---

### `loghop install-hooks [--scope project]`

Install Claude session hooks. This is an advanced command; prefer `loghop install` or `loghop init` unless you need to repair one integration.

```bash
loghop install-hooks
loghop install-hooks --scope project
loghop install-hooks --uninstall --dry-run
```

---

### `loghop install-shims --codex`

Install Codex PATH shim. This is an advanced command; prefer `loghop install` or `loghop init` unless you need to repair one integration.

```bash
loghop install-shims --codex
loghop install-shims --codex --prefix ~/.local/bin
loghop install-shims --codex --uninstall --dry-run
```

---

### `loghop install-prompt [--scope project]`

Install shared prompt block. This is an advanced command; prefer `loghop install` or `loghop init` unless you need to repair one integration.

```bash
loghop install-prompt
loghop install-prompt --scope project
loghop install-prompt --codex --claude
loghop install-prompt --uninstall --dry-run
```

---

### `loghop install-aliases`

Install loghop wrap aliases to user shell profiles.

```bash
loghop install-aliases
loghop install-aliases --uninstall
loghop install-aliases --dry-run
```

**Options:**

| Flag | Description |
|------|-------------|
| `--uninstall` | Uninstall aliases from profiles |
| `--dry-run` | Preview changes without writing |

**Description:** Automatically detects and appends or updates the loghop wrap aliases in the user's shell configuration files (`~/.bashrc`, `~/.zshrc`, `~/.config/fish/config.fish`). It creates backup files (e.g. `.bashrc.loghop.bak`) before writing any changes.

---

### `loghop uninstall-aliases`

Remove loghop wrap aliases from user shell profiles.

```bash
loghop uninstall-aliases
loghop uninstall-aliases --dry-run
```

**Options:**

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview changes without writing |

**Description:** Automatically removes the loghop wrap aliases block from the user's shell configuration files. Creates backup files before writing changes.

---

## Utility Commands

### `loghop metrics [--format <format>]`

Export local project metrics.

```bash
loghop metrics
loghop metrics --format prometheus
loghop metrics --format json
loghop metrics --format yaml
```

**Options:**

| Flag | Description |
|------|-------------|
| `--format <format>` | Output format: `summary` (default), `prometheus`, `json`, or `yaml` |

**Description:** Collects and outputs project statistics including total sessions, total handoffs, total timeline events, sessions by status, and sessions by provider.

---


### `loghop doctor [--fix]`

Check installation health.

```bash
loghop doctor
loghop doctor --fix
```

**Description:** Verifies hooks, shims, prompt blocks, and config. With `--fix`, attempts repairs.

---

### `loghop completion {bash,zsh,fish}`

Generate shell completion.

```bash
loghop completion bash > /etc/bash_completion.d/loghop
loghop completion zsh > ~/.zshrc.d/loghop.zsh
```

---

### `loghop hook <subcommand>`

Internal hook endpoints (for Claude session lifecycle).

```bash
loghop hook claude-session-start <session-id>
loghop hook claude-session-end <session-id>
```

---

## Global Flags

| Flag | Description |
|------|-------------|
| `--json` | Output as JSON |
| `--plain` | Plain text output (no colors) |
| `--quiet` | Suppress non-error output |
| `--verbose` | Verbose logging |
| `--version` | Show version |
| `--global` | Show the global projects view even inside a loghop repo |
