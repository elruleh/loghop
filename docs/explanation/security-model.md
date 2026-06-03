---
layout: default
title: Security model
description: How loghop protects local project data and secrets.
---

# Security Model

How loghop protects local project context and which risks it mitigates.

## Scope

loghop is a **local-first CLI**. It writes project data to `.loghop/` inside a Git working tree and writes a generated `loghop.md` summary at the repo root. Optional install features also write global state under `~/.loghop/`, update `~/.claude/settings.json`, and may install a shim under `~/.local/bin/`.

loghop has no network listener or background daemon. The supported production target is Linux/macOS.

## Threat Model

| Threat | Attack vector | Mitigation |
|--------|---------------|------------|
| Secret leakage | API keys or bearer tokens written to `loghop.md`, handoffs, transcripts, logs, or session metadata | Multi-pattern redaction at write boundaries |
| Symlink attack | `.loghop/`, `loghop.md`, backup output, or restored files replaced by symlinks | Reads and writes reject symlinks where sensitive data is involved; project paths are validated before use |
| Permission leaks | Other users on the host read handoff/session contents | `.loghop/` is `0o700`; sensitive files are `0o600`; backups are created `0o600` |
| Partial writes | Process killed while writing config, timeline, session, or handoff files | Atomic writes using temp file, `fsync`, `os.replace`, and directory `fsync` |
| Concurrent handoffs/sessions | Two processes allocate the same ID | Per-project lock file serializes state updates |
| Artifact tampering | Local handoff/session markdown edited after write | HMAC signatures cover frontmatter and body using `.loghop/integrity.key` |
| Unsafe restore archive | Backup archive contains traversal paths, unsafe member types, or symlink targets | Restore accepts only `.loghop/*` and `loghop.md`, rejects traversal and existing symlink targets |
| Shell environment leakage | Claude credential discovery probes an interactive shell environment | Only Claude-scoped variables are retained; full env is not logged or stored; probe can be disabled |
| Global install drift | Hook, shim, or prompt files diverge from managed content | `loghop doctor` checks install state; installers are idempotent |

## Key Security Features

### Secret Redaction

Before writing local context, loghop applies redaction for common secret formats, including:

- provider API keys and tokens;
- bearer/basic/token authorization headers;
- JWTs;
- AWS/GitHub/GitLab/Slack/Discord/SendGrid-style tokens;
- private key blocks;
- URLs with embedded credentials;
- database and connection-string variables.

#### Custom Secrets Redaction

In addition to built-in system rules, loghop supports **custom redaction patterns**. Users can configure custom regular expression patterns inside global (`~/.loghop/config.toml`) or project-level (`.loghop/config.toml`) configurations using the `[[redaction]]` block. Custom redaction patterns are executed **first**, before the default system secret rules are evaluated.

Redaction is a defense-in-depth control, not a reason to intentionally paste secrets into prompts or handoffs.

### File Permissions

```python
DIR_MODE = 0o700    # .loghop/ directories
FILE_MODE = 0o600   # Sensitive files
```

Project state, transcripts, logs, integrity keys, and backups are written with restrictive permissions. Security does not rely on the user's `umask`.

### Atomic Writes

For mutable local state, loghop uses the durable write pattern:

1. create a temporary file in the target directory;
2. write and flush content;
3. `fsync` the temporary file;
4. atomically replace the target with `os.replace`;
5. `fsync` the parent directory.

This reduces corruption risk during crashes, interruptions, or power loss.

### Symlink and Path Validation

Sensitive reads use no-follow semantics where available. Directory creation walks path components and rejects symlinked ancestors. Restore and delete operations validate that resolved paths stay inside the expected project or `.loghop/` directory.

### Artifact Integrity

Session and handoff markdown files include an HMAC signature in frontmatter:

```yaml
_signature: 0123456789abcdef0123456789abcdef
```

New signatures are 32 hex characters. Existing 16-character signatures remain valid for backward compatibility.

The signature covers both metadata and markdown body. It detects local tampering in `.loghop/`; it does not encrypt content and it does not protect against a user or process that can also read/write `.loghop/integrity.key`.

### Project Lock

State-changing operations use a per-project lock file to avoid duplicate session/handoff IDs and partial concurrent updates.

### Claude Shell Environment Probe

When Claude API credentials are missing from the current process, loghop may run `bash -c "env -0"` to discover credentials exported by the user's interactive shell. Only `ANTHROPIC_*` and `CLAUDE_CODE_*` variables are retained.

Disable this behavior in hardened environments:

```bash
export LOGHOP_DISABLE_CLAUDE_SHELL_ENV_PROBE=1
```

## Out of Scope

Third-party provider binaries (`codex`, `claude`) and upstream transcript storage formats are out of scope except where loghop wraps or parses them.

## Reporting Security Issues

See [SECURITY.md](../../SECURITY.md) for the full security policy and reporting instructions.

**Private reporting:** https://github.com/elruleh/loghop/security/advisories/new

Please do not open public issues for vulnerabilities.

## Security Best Practices

When using loghop:

1. Keep `.loghop/` and `~/.loghop/` private.
2. Do not commit generated local state.
3. Prefer `loghop run` or `loghop wrap` so sessions are captured consistently.
4. Run `loghop doctor` if hooks, shims, or prompt includes appear stale.
5. Review handoffs before sharing them outside your machine.
