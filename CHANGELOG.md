# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-06-19

### Fixed
- TUI project loading now works correctly from packaged installs, restoring the home-screen project list for users installing via PyPI/`uv tool install`.
- `loghop sessions list` no longer leaks Rich markup in tree labels when rendered outside an interactive terminal.
- `sessions reconcile` is more stable around near-future timestamps and clock skew.
- Claude shell-environment probing handles both `bytes` and `str` subprocess output.
- Low-severity Bandit findings in subprocess and broad-exception paths have been addressed.

### Changed
- Demo assets now show real command output and an actual Textual TUI recording over a populated multi-project workspace.
- Public repository hygiene was tightened: maintainer identity, CODEOWNERS, release-hygiene tests, issue links, metadata, support policy and contribution policy.
- Documentation now includes a comparison page for adjacent AI coding tools and refreshed social/demo assets.

## [0.2.0] - 2026-06-10

### Added
- TUI tests for screen-state helpers, list-screen search parser, and the new declarative terminal specs (`tests/test_tui_screen_state.py`, `tests/test_launcher_specs.py`).
- `pytest.mark.slow` marker for TUI tests that need a real pilot; `pytest -m "not slow"` skips them in the inner loop.
- Tests for redaction cache invalidation by config mtime, TTL-bounded Claude shell-env probe cache, `_expand_doublestar` globbing, `project_lock` reentrancy, and threading serialisation.
- Tests for the redaction pipeline's edge cases (short Slack tokens, idempotence, double-redaction).

### Changed
- Redaction custom-pattern cache now invalidates on config-file mtime changes; edits to `~/.loghop/config.toml` or `<project>/.loghop/config.toml` take effect on the next call without a process restart.
- Claude shell-env probe cache switched from `lru_cache` (process-lifetime) to a 30-second TTL bounded dict; new `ANTHROPIC_*` exports in the current shell become visible after the window expires.
- TUI terminal-launcher builders refactored from nine near-duplicate functions to a declarative `_TerminalSpec` table; only `konsole` (key=value style) and `wt.exe` (WSL script) keep dedicated builders.
- Slack token regex tightened with a minimum length (8 chars after prefix) to avoid over-redacting short placeholders in docs and logs.
- TUI test files reorganised so `pytestmark = pytest.mark.slow` is declared after imports.
- `release_check.sh` now comments on the slow vs fast test split.

### Fixed
- Redaction pipeline's eager `find_project_root` call would propagate `KeyboardInterrupt` from a test-mocked `subprocess.run`; the lookup helper now catches `BaseException` so redaction can never escape a path-discovery failure into the runner.

### Documentation
- README clarifies Linux/macOS as the supported production target and explains Windows best-effort behaviour.
- `reference/configuration.md` documents that custom redaction edits apply on the next call (mtime-based cache invalidation) and that the Claude shell-env probe is cached for 30 seconds.

## [0.1.1] - 2026-06-03

### Added
- Polymorphic provider architecture under `src/loghop/providers/` extending `BaseProvider` for future-proof AI provider integration.
- User-configurable terminal emulator and execution templates via `~/.loghop/config.toml` (vía `terminal.emulator` and `terminal.template`), with variable placeholders (`{title}`, `{workdir}`, `{command}`) and bash command list expansion (`{bash_command}`).
- Fallback generic command execution for custom terminal emulators lacking a builder.
- Extended HMAC-SHA256 integrity signature to 32 hex chars with backward-compatible 16-char validation fallback.

### Changed
- Bounded greedy prefix wildcards in `redact.py` secrets redaction pattern to 50 characters, preventing catastrophic backtracking (ReDoS) on large input strings.
- Hardened POSIX advisory lock files with the `O_NOFOLLOW` flag to mitigate symlink attack vulnerabilities.
- Isolated test environments (`HOME`, `USERPROFILE`, and `Path.home()`) to prevent parallel test conflicts.
- Cleared shadowing `providers.py` module in favor of the new providers package.

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

[Unreleased]: https://github.com/elruleh/loghop/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/elruleh/loghop/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/elruleh/loghop/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/elruleh/loghop/releases/tag/v0.1.1
[0.1.0]: https://github.com/elruleh/loghop/releases/tag/v0.1.0
[Pre-0.1 rewrite]: https://github.com/elruleh/loghop/commits/main
[Prototype]: https://github.com/elruleh/loghop/commits/main
