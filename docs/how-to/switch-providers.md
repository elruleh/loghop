# Switch Between Providers

Use Claude Code and Codex interchangeably with full context continuity.

## Auto-Detection

loghop automatically detects available providers on your PATH:

```bash
loghop providers
```

Output:
```
Provider    Status      Path
claude      ✅ found    /usr/local/bin/claude
codex       ❌ missing
```

## Run with Specific Provider

```bash
# Use Claude Code
loghop run --provider claude

# Use Codex
loghop run --provider codex
```

## Remember Last Provider

loghop remembers which provider you used for each project:

```bash
# Without --provider, uses the last provider
loghop run
```

## Wrap Direct Calls

Add shell aliases so direct `claude` or `codex` calls go through loghop:

```bash
# In your .bashrc or .zshrc
alias claude='loghop wrap claude'
alias codex='loghop wrap codex'
```

Now every `claude` or `codex` command inside an initialized repo automatically captures the session.

## Transparent Capture

The wrapper:
1. Creates a session before launching the provider
2. Captures the transcript when the provider exits
3. Writes the handoff for the next session

Outside a Git repo or uninitialized project, the wrapper passes through to the real binary.

## Switch Mid-Project

You can switch providers mid-project. The timeline keeps context across both:

```bash
# Started with Claude, now use Codex
loghop run --provider codex

# Later, back to Claude
loghop run --provider claude
```

Each provider writes to the same timeline. The handoff includes context from both.

## Verify Provider Selection

Check the current project state:

```bash
loghop status
```

Output:
```
Project: /home/user/my-app
Provider: claude (last used)
Sessions: 12
Goal: Add user authentication
```

## Provider-Specific Notes

### Claude Code

- Sessions are captured via hooks in `~/.claude/settings.json`
- Hooks require Claude Code to write session metadata
- If hooks fail, transcript is captured from `~/.claude/projects/`

### Codex

- Sessions are captured via the shim in `~/.local/bin/codex`
- Shim wraps any `codex` invocation
- Transcript parsed from `~/.codex/sessions/`

Both providers store their native transcripts in home directory. loghop parses, redacts, and copies relevant content to the project `.loghop/` directory.
