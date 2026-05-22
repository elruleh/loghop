# How It Works

Understanding loghop's architecture and design decisions.

## Overview

loghop bridges the gap between AI coding assistants by capturing session context and making it available to the next provider — even if it's a different one.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  loghop run  │────▶│   Provider   │────▶│   Capture   │
│  build handoff│    │ Claude/Codex │    │  transcript  │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                                │
                          ┌─────────────────────▼──────────────────────┐
                          │              .loghop/                       │
                          │  timeline.jsonl  ← shared across providers │
                          │  sessions/S-*.md ← redacted metadata       │
                          │  handoffs/H-*.md ← context for next run    │
                          └────────────────────────────────────────────┘
```

## Key Concepts

### Session

A **session** is one invocation of a provider (Claude Code or Codex). Each session produces:
- **Metadata** (`.loghop/sessions/S-NNN.md`) — goal, topic, status, summary
- **Transcript** (`.loghop/sessions/S-NNN.transcript.jsonl`) — redacted conversation

### Topic

A **topic** is a work thread that groups related sessions. It lets loghop keep one immutable audit record per provider run while presenting work as a coherent unit such as “Ship auth” or “Fix TUI focus”. The active topic is stored in project config; `loghop run` attaches new sessions to it unless `--new-topic`, `--topic`, or `--no-topic` says otherwise.

### Handoff

A **handoff** is a context document built from the timeline before starting a new session. It includes:
- Recent decisions and progress
- Active todos
- Changed files
- Git diff (uncommitted changes)

### Timeline

The **timeline** is a chronological record of all sessions across all providers for a project. It enables:
- Cross-provider context
- Session history
- Activity reporting

## Integration Layers

When you run `loghop init`, loghop can set up three optional integrations:

### 1. Claude Hooks

Hooks capture sessions via Claude's lifecycle events:

```
~/.claude/settings.json → SessionStart → loghop hook → create session
~/.claude/settings.json → SessionEnd → loghop hook → capture transcript
```

Hooks are merged into existing settings, preserving other configurations.

### 2. Codex Shim

The shim wraps the `codex` binary:

```
~/.local/bin/codex → loghop wrap codex → create session → real codex → capture transcript
```

The shim only activates in initialized Git repos. Outside repos, it passes through to the real binary.

### 3. Prompt Block

The prompt block adds context to provider interactions:

```
~/.loghop/loghop-prompt.md → included in CLAUDE.md/AGENTS.md → provider sees context
```

Providers emit structured metadata (`loghop` fenced block) that loghop uses for fast-path capture.

## Capture Flow

1. **Before launch**: Resolve the active topic and build a handoff from topic plus project timeline
2. **Launch provider**: Start Claude or Codex with handoff context
3. **During session**: Monitor for lifecycle events (if hooks enabled)
4. **After exit**: Parse provider's native transcript
5. **Redact**: Strip API keys, tokens, credentials
6. **Store**: Write session metadata, transcript, update timeline

## Security Model

### File Permissions

- `.loghop/` directory: `0o700` (owner only)
- All files inside: `0o600` (owner read/write)
- Prevents other users on the same host from reading handoffs

### Atomic Writes

Writes use `mkstemp` + `fsync` + `replace` pattern:
1. Write to temp file
2. `fsync` the temp file
3. `os.replace` to target
4. `fsync` the directory

This prevents corruption if the process is killed mid-write.

### Secret Redaction

20+ regex patterns redact secrets before storage:
- API keys (AWS, Azure, GCP, OpenAI, Anthropic, etc.)
- Bearer tokens
- JWTs
- URLs with embedded credentials
- Private keys

### Symlink Protection

All file operations:
1. Reject symlinks in `.loghop/` paths
2. Reject paths outside the project root
3. Validate paths before any I/O

## Provider Detection

Providers are detected at runtime by checking `PATH`:

```bash
which claude   # Found → use Claude
which codex    # Found → use Codex
which neither  # Error → no provider available
```

No configuration needed. Just ensure the provider binary is on PATH.

## Why This Design?

### Local-First

All data stays in the project directory (`.loghop/`). No cloud service, no sync, no account required.

### Provider Agnostic

Same interface for Claude and Codex. Switch providers without losing context.

### Privacy by Default

Known secret patterns are redacted at write time before handoffs, transcripts, logs, and summaries are stored locally.

### Resilient Capture

Even if hooks fail or shim is bypassed, `loghop run` captures the session from the provider's transcript files.

### Recovery-Friendly

Auto-reconcile fixes stuck sessions. Atomic writes reduce corruption risk. Registry backups and private backup archives support recovery.

## Why Sessions Remain Separate From Topics

Sessions are intentionally not reused for the same topic. A session records a concrete provider process with its own timestamps, return code, transcript, and failure mode. Topics provide the user-facing continuity layer above sessions, so resume and TUI flows can stay focused on a work item without losing auditability.

## Version Compatibility

Patch releases maintain backward compatibility:
- `.loghop/` layout stays compatible
- CLI commands, flags, exit codes unchanged
- Provider transcript parsers frozen in fixtures

Minor releases may add fields to config files but never remove or change existing fields.

Breaking changes to `.loghop/` require:
1. Migration path in code
2. Backup of affected files
3. Release note documenting the change
4. Regression tests with old fixtures
