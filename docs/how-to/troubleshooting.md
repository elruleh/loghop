# Troubleshooting

Solutions for common loghop issues.

## Installation Issues

### "command not found: loghop" after pipx install

```bash
# Reinstall
pipx reinstall loghop

# Or ensure pipx bin is on PATH
echo $PATH | tr ':' '\n' | grep -q pipx || export PATH="$PATH:$(pipx environment | grep BINARY_PATH | cut -d= -f2)"
```

### Python version error

loghop requires Python 3.12+.

```bash
python3 --version
# Must be 3.12 or later
```

If on an older version:
```bash
# Install newer Python (macOS)
brew install python@3.12

# Install newer Python (Linux)
sudo apt install python3.12 python3.12-venv
```

## Session Issues

### "Project not initialized"

Run `loghop init` first:

```bash
cd your-git-repo
loghop init
```

### Session marked as "running" after provider crashed

Auto-reconcile runs on every command. Manual fix:

```bash
loghop sessions reconcile
```

### "Provider unavailable"

Check providers:

```bash
loghop providers
```

If provider is missing:
- **Claude**: Install from https://docs.anthropic.com/en/docs/claude-code
- **Codex**: Install from https://platform.openai.com/docs/guides/codex

### Session capture failed

Check the log:

```bash
# Project-level log
cat .loghop/loghop.log

# Global log
cat ~/.loghop/loghop.log
```

Run doctor to diagnose:

```bash
loghop doctor
```

Run doctor with fix for common issues:

```bash
loghop doctor --fix
```

## Provider Authentication

### Claude auth error

```bash
# Verify Claude can authenticate
claude --version

# Re-run with auth check
loghop run --verbose
```

If auth fails, Claude writes error details to its own log. Check Claude logs for details.

### Codex auth error

```bash
# Verify Codex API key is present without printing the secret
[ -n "${OPENAI_API_KEY:-}" ] && echo "OPENAI_API_KEY is set" || echo "OPENAI_API_KEY is not set"

# Re-run with verbose
loghop run --verbose
```

## Handoff Issues

### "No handoff found" when resuming

No previous session exists yet. Use `loghop run` instead.

### Handoff missing recent context

Check session status:

```bash
loghop sessions list
```

If a session is stuck in "running", reconcile:

```bash
loghop sessions reconcile
```

### Goal not showing in handoff

Set goal:

```bash
loghop goal "Your task description"
```

The goal is written to `config.toml` and included in the next handoff.

## Uninstall Issues

### "Permission denied" removing hook files

Run with appropriate permissions:

```bash
loghop uninstall -y
```

Or manually remove:

```bash
# Remove Claude hooks
rm ~/.claude/settings.json  # Edit instead of delete if other hooks exist

# Remove Codex shim
rm ~/.local/bin/codex

# Remove prompt blocks
rm ~/.loghop/loghop-prompt.md
rm ~/path/to/project/CLAUDE.md  # Remove loghop section manually
rm ~/path/to/project/AGENTS.md  # Remove loghop section manually
```

## Log Access

For support, collect relevant logs:

```bash
# Project log
cat .loghop/loghop.log > /tmp/loghop-project.log

# Global log
cat ~/.loghop/loghop.log > /tmp/loghop-global.log

# Provider version
loghop --version
```

## Reset Everything

To remove all loghop data and reinstall:

```bash
# From inside a project
cd your-git-repo
loghop uninstall -y --purge

# Then reinitialize
loghop init
```

## Get Help

- [GitHub Issues](https://github.com/raul/loghop/issues) — Bug reports and features
- [GitHub Discussions](https://github.com/raul/loghop/discussions) — Questions
- [Security Advisories](https://github.com/raul/loghop/security/advisories/new) — Private security reports
