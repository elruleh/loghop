# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-04-29

### Added
- Documented development utilities (`anyio` for async testing, `types-pyyaml` for type stubs, and `vulture` for dead code analysis) in `NOTICE.md` to ensure complete compliance.
- Added optional `loghop[tui]` dependencies and a `loghop tui` command that
  lazily imports Textual and reports a clear install hint when the extra is
  missing.
- `loghop init` now orchestrates optional global setup for Claude session
  hooks, a Codex PATH shim, and the shared prompt block, with answers saved in
  `~/.loghop/config.toml`.
- Added `loghop init --no-prompt` for CI/scripted installs; it assumes "No" for
  optional global integrations and does not ask interactively.
- Added low-level `loghop install-hooks`, `loghop install-shims --codex`,
  `loghop install-prompt`, and the internal
  `loghop hook claude-session-start|end` endpoint.
- Added parsing for final fenced `loghop` metadata blocks so autocapture can
  use explicit provider summaries, decisions, and todos before heuristic
  fallback.

### Changed
- Plain `loghop` now opens the Textual TUI by default in an interactive
  terminal; use `loghop --plain` to keep the compact CLI dashboard.
- Hardened project I/O so private permissions apply only inside `.loghop/`.
- Added `--version`, safer goal/output redaction, and stricter CLI validation
  for `--timeout` and single-line metadata.
- `handoff show` now prints the stored markdown handoff instead of metadata
  only.
- CI now validates Bandit with project config and smoke-tests built artifacts.
- Providers are now detected from `PATH` at use time instead of persisted in
  project config.
- Handoff history records execution status and `loghop.md` now uses the same
  ignore policy as handoffs.

## [Pre-0.1 rewrite] - 2026-04-24

### Changed
- **Full rewrite, not compatible with 0.1.x projects.** Delete any existing
  `.loghop/` directory and re-run `loghop init`.
- CLI trimmed from ~40 subcommands to 7: `init`, `providers list`, `goal`,
  `handoff {build,run,list,show}`, `status`.
- `setup` was merged into `init`: initialization now detects Codex and Claude
  Code in `PATH` and records them in the project's `config.toml`.
- `overview set` is now `goal`.
- `status` absorbed the read-only parts of `doctor`.
- Project state is flat: a single `.loghop/config.toml` holds the goal,
  handoff counter, and provider records. Handoffs live in
  `.loghop/handoffs/H-NNN.md` with frontmatter metadata.

### Removed
- Supported providers dropped to Codex and Claude Code. Gemini and opencode are
  gone (and so is the hash-verification machinery).
- Session capture: `watch`, `shim install`, embedded PTY capture,
  `session_capture.py`, `memory_scorer.py`.
- State-derived features: `note`, `task`, `checkpoint`, `memory review/apply`,
  `conversation list/show/resume`, project registry.
- Admin/infra: `archive`, `export`, `import`, `doctor --repair`, HMAC integrity
  chain, per-project lock (`ProjectLock`), random `.secret` key, `state.json`,
  `events.jsonl`.

### Added
- Python 3.13 classifier (already covered by CI matrix).

## [Prototype] - 2026-04-19
### Added
- Initial release of loghop.
- Minimal CLI for auditable AI handoffs in local Git repositories.
- Core commands: `init`, `note`, `task`, `status`, `handoff`, `import`,
  `export`.

[Unreleased]: https://github.com/elruleh/loghop/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/elruleh/loghop/releases/tag/v0.1.0
[Pre-0.1 rewrite]: https://github.com/elruleh/loghop/commits/main
[Prototype]: https://github.com/elruleh/loghop/commits/main
