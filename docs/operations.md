# Operations

## Support Scope

- Supported runtime target: Linux and macOS on Python 3.12+.
- Supported providers: `codex` and `claude`.
- Windows-native support: partial native support is provided through Windows PATH shim generation (`codex.cmd`) in Command Prompt (CMD) environments. Other native Windows features remain out of scope; WSL is supported as Linux. Upstream provider internals beyond transcripts are out of scope.

## Logs

- Global commands outside a repo write JSON logs to `~/.loghop/loghop.log`.
- Project commands write JSON logs to `<repo>/.loghop/loghop.log`.
- Logs are rotated and redacted before write. Ask users for the relevant log plus the failing command, provider, and exact timestamp.

## First Response

1. Run `loghop doctor`.
2. If the failure is install-related, run `loghop doctor --fix`.
3. If a session was interrupted, run `loghop sessions reconcile`.
4. If a project was deleted or moved, run `loghop projects cleanup`.
5. If wrappers or prompt assets look stale, run `loghop uninstall -y` and then prefer `loghop install` or `loghop init` before reaching for low-level `install-*` commands.

## Recovery Commands

- Preferred rebuild paths:
  - inside a repo: `loghop init --force-reinstall`
  - outside a repo: `loghop install --force-reinstall`
- Advanced/manual rebuild commands:
  - `loghop install-hooks`
  - `loghop install-shims --codex`
  - `loghop install-prompt`
- Advanced project-scoped rebuilds from inside a repo:
  - `loghop install-hooks --scope project`
  - `loghop install-prompt --scope project`
- Remove all managed assets and state: `loghop uninstall -y --purge`

## Release Gate

1. `uv sync --all-extras --dev`
2. `bash scripts/release_check.sh qa`
3. `bash scripts/release_check.sh artifacts`
4. `python3 scripts/e2e_user_flow.py --skip-pytest --skip-smoke`
5. Run the `release rehearsal` workflow manually for the target version. Enable `publish_testpypi` when the TestPyPI trusted publisher is configured.
6. Publish to TestPyPI, run `bash scripts/smoke_published.sh --version X.Y.Z --repository testpypi`, then publish to PyPI.
7. Run `bash scripts/smoke_published.sh --version X.Y.Z --repository pypi` before cutting the GitHub Release.

## Rollback

- If the TestPyPI smoke fails, do not publish to PyPI. Fix forward and retag.
- If the PyPI smoke fails after publish, `yank` the release on PyPI immediately and open a hotfix release.
- Do not create the GitHub Release until PyPI smoke is green.
- Capture the failing command, exact version, provider, and relevant `~/.loghop/loghop.log` or `<repo>/.loghop/loghop.log` in the incident report.

## Transcript Compatibility

- The parser contract suite lives in `tests/test_provider_contracts.py`.
- Drift warnings are covered in `tests/test_transcript_drift.py`.
- Any provider format regression that changes fixtures or drift expectations is a release blocker until the parser and fixtures are updated together.
- Compatibility policy for runtime, project state, global state and CLI behavior lives in `docs/compatibility.md`.
