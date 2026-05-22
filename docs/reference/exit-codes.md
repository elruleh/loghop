# Exit Codes

loghop exits with specific codes for different conditions.

## Exit Code Reference

| Code | Name | Meaning |
|------|------|---------|
| `0` | Success | Command completed successfully |
| `1` | Internal Error | Unexpected internal error |
| `2` | Usage Error | Invalid arguments or validation failure |
| `3` | Timeout | Session timed out |
| `10` | Provider Non-Zero | Provider exited with non-zero status |
| `20` | Not Initialized | Project not initialized for loghop |

## Detailed Explanation

### `0` — Success

The command completed successfully. This includes:
- Session captured and stored
- Handoff created
- Project initialized
- Status query completed

### `1` — Internal Error

An unexpected error occurred. This is a bug. Please report:
- Command that failed
- Exact error message
- Provider and version
- Log file contents (`.loghop/loghop.log`)

### `2` — Usage Error

Invalid command-line arguments or validation failed:

```bash
# Missing required argument
loghop handoff show  # Error: handoff ID required

# Invalid option
loghop run --provider invalid  # Error: unknown provider

# Project not a git repo
loghop init  # Error: not a git repository
```

### `3` — Timeout

The session reached the timeout limit:

```bash
loghop run --timeout 60  # Fails after 60 seconds
```

Default timeout is 300 seconds (5 minutes). Adjust with `--timeout`.

### `10` — Provider Non-Zero

The provider (Claude or Codex) exited with a non-zero status:

```bash
loghop run  # Provider exited with code 1

# Check provider logs for details
loghop --verbose run
```

This usually indicates the provider encountered an error. Check:
- Provider authentication
- Provider logs
- Project configuration

### `20` — Not Initialized

Project has not been initialized for loghop:

```bash
loghop run
# Error: Project not initialized. Run `loghop init` first.

# Fix:
cd your-git-repo
loghop init
loghop run
```

## Using Exit Codes in Scripts

```bash
#!/bin/bash
loghop run --provider codex
exit_code=$?

case $exit_code in
    0) echo "Session complete" ;;
    3) echo "Timeout - retrying" ;;
    10) echo "Provider error - check logs" ;;
    *) echo "Unexpected error: $exit_code" ;;
esac
```

## Signal Handling

| Signal | Exit Code | Meaning |
|--------|-----------|---------|
| SIGINT (Ctrl+C) | 130 | User interrupted |
| SIGTERM | 130 | Terminated externally |

loghop converts SIGTERM to KeyboardInterrupt internally, which exits with code 130 (128 + 2).

## JSON Output with Exit Codes

```bash
loghop run --json 2>/dev/null | jq .exit_code
```

When using `--json`, the exit code is also included in the JSON envelope.
