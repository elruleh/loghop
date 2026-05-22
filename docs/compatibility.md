# Compatibility

## Runtime Support

- Supported operating systems: Linux, macOS, and Windows (with partial native support via Command Prompt shims).
- Supported Python: 3.12+.
- Supported providers: `codex` and `claude`.
- Windows-native support: partial native support is provided through Windows PATH shim generation (`codex.cmd`) in CMD environments. Linux and macOS remain the primary focus. WSL is treated as Linux when paths and provider CLIs behave like Linux.

## Project State

The `.loghop/` directory is private local state. Patch releases must keep existing `.loghop/config.toml`, sessions, handoffs and transcripts readable.

Minor releases may add fields to frontmatter or config files. They must remain backward-compatible with older fields, and migrations must be idempotent.

Breaking changes to `.loghop/` layout require:

- a migration path in `loghop.install._migrations`;
- a backup of every file the migration may rewrite;
- a release note that names the affected files;
- regression tests that load old fixtures and verify the migrated result.

## Global State

Global state lives under `~/.loghop/`. The registry file `projects.toml` must be treated as user data. If it cannot be parsed, loghop must preserve a `projects.toml.corrupt-*` copy before rebuilding or returning an empty registry.

Install migrations must back up global config, hooks, shims and prompt files before reapplying managed content.

## Provider Transcripts

Provider transcript formats are upstream contracts outside loghop's control. Parser compatibility is enforced with frozen fixtures in `tests/fixtures/transcripts/` and contract tests in `tests/test_provider_contracts.py`.

Any parser change that makes old fixtures unreadable is a release blocker unless the release explicitly declares a compatibility break and includes a migration or fallback.

## CLI Compatibility

Patch releases should not remove commands, flags, JSON fields, session statuses or exit codes.

Minor releases may add commands or JSON fields. Scripts should tolerate unknown fields, and loghop should preserve known fields when rewriting metadata.

Commands marked as advanced may change more quickly, but they should still fail with clear validation errors rather than silently changing project state.
