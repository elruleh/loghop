# Security Policy

## Scope

Loghop is a **local-first CLI**. It writes project data to `.loghop/` inside a
Git working tree and to `loghop.md` at the repo root. Optional install
features also write global state under `~/.loghop/`, update
`~/.claude/settings.json`, and may install a shim under `~/.local/bin/`. It
has no network listener or background daemon. The current production target is
Linux/macOS.

## Threat model

| Threat | Attack vector | Mitigation |
|--------|---------------|------------|
| Secret leakage | API keys or bearer tokens written to `loghop.md` or a handoff | Multi-pattern regex redaction at every write boundary (`redact_text`) |
| Symlink attack | `.loghop/` or `loghop.md` replaced by symlinks pointing outside the repo | Reads reject symlinks and project paths are validated before use |
| Partial writes | Process killed mid-write corrupts `config.toml` | Atomic writes: `tempfile.mkstemp` → write → `fsync` → `os.replace` → `fsync` on the directory |
| Permission leaks | Other users on the host read handoff contents | `.loghop/` is `0o700`, files are `0o600` |
| Concurrent handoffs | Two processes allocate the same handoff ID | Per-project lock file serializes handoff creation |
| Global install drift | Optional hook/shim/prompt files diverge from managed content | Install doctor/fix checks, idempotent installers, versioned install metadata |
| Shell env probe | Claude credential discovery spawns `bash -c env -0` to read interactive shell exports | Only `ANTHROPIC_*` and `CLAUDE_CODE_*` prefixed variables are retained; full env is never stored, logged, or written to disk. 3-second timeout, LRU-cached. Disable with `LOGHOP_DISABLE_CLAUDE_SHELL_ENV_PROBE=1` |
| Artifact tampering | Session or handoff frontmatter/body edited after write | HMAC signatures cover metadata and markdown body using a private per-project `.loghop/integrity.key`; mismatches are logged as warnings |
| Unsafe backup/restore archive | Backup archive contains sensitive local state, traversal paths, or symlink targets | Backups are written `0o600`; restore only accepts `.loghop/*` and `loghop.md`, rejects traversal and existing symlink targets |
| Transient provider preflight failure | Provider auth status briefly fails because of shell/process flakiness | Auth preflight uses bounded retry/backoff via `LOGHOP_PROVIDER_AUTH_RETRIES` and `LOGHOP_PROVIDER_AUTH_RETRY_DELAY_MS` |

## Reporting

Report vulnerabilities via GitHub Security Advisories:

  https://github.com/elruleh/loghop/security/advisories/new

We aim to respond within **48 hours** and resolve critical issues within **7 days**.

Please do not file public issues for security vulnerabilities.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |
| < 0.1   | No        |

## What is NOT in scope

Third-party provider binaries (`codex`, `claude`) and upstream transcript
storage formats are out of scope except where loghop wraps or parses them.
