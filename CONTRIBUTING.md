# Contributing to loghop

First off, thanks for taking the time to contribute.

## Local Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/elruleh/loghop.git
   cd loghop
   ```

2. **Install dependencies with uv:**
   ```bash
   uv sync --all-extras --dev
   ```

3. **Install pre-commit hooks:**
   ```bash
   uv run pre-commit install
   ```

## Daily Workflow

- **Testing:** We use `pytest`. Run tests locally to ensure nothing breaks:
  ```bash
  uv run pytest --cov=loghop --cov-report=term-missing --cov-fail-under=80
  ```

- **Linting & Formatting:** We use `ruff`.
  ```bash
  uv run ruff format --check src tests scripts
  uv run ruff check src tests scripts
  ```

- **Type Checking:** We use `mypy` in strict mode.
  ```bash
  uv run mypy src
  ```

- **Security:** Run `bandit` to check for security vulnerabilities:
  ```bash
  uv run bandit -c .bandit.yml -r src/loghop
  ```

- **Dependency audit:** Run `pip-audit` before release work:
  ```bash
  uv export --all-extras --dev --format requirements-txt --no-emit-project --no-hashes > /tmp/loghop-req.txt
  uv run pip-audit -r /tmp/loghop-req.txt --desc
  ```

- **Artifact smoke:** Validate the built package, not just the source tree:
  ```bash
  bash scripts/release_check.sh artifacts
  ```

The pre-commit hooks cover fast local hygiene only: YAML/TOML sanity, private-key checks, Ruff and Mypy. They do not replace the full release gates.

## Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Public history hygiene

This repository keeps a clean public history on purpose.

- Use **your own GitHub identity** consistently when authoring commits.
- Do **not** add AI-vendor co-author trailers (for example Anthropic/Claude, Copilot, etc.) to commits intended for `main` unless a real human co-author should be credited.
- If you used AI assistance, capture that in the PR description or notes instead of polluting the permanent contributor graph.
- Prefer one clear, reviewable PR over a burst of tiny cosmetic commits when polishing docs/assets.

**Types:**

| Type | When to use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or updating tests |
| `chore` | Maintenance tasks (deps, CI, configs) |
| `perf` | Performance improvements |

**Examples:**
```bash
feat(run): add --provider flag to override auto-detection
fix(capture): handle empty transcript gracefully
docs(readme): update installation instructions for pipx
refactor(store): extract session factory methods
```

## Branch Naming

- `feature/<description>` — new features
- `fix/<description>` — bug fixes
- `docs/<description>` — documentation changes
- `refactor/<description>` — code refactoring
- `release/<version>` — release preparation

**Example:** `feature/add-codex-support`, `fix/session-timeout-crash`

## Submitting Changes

1. Create a branch: `git checkout -b feature/my-new-feature`
2. Make your changes and write tests
3. Ensure all checks pass:
   ```bash
   uv run pytest --cov=loghop --cov-fail-under=80
   uv run ruff check src tests scripts
   uv run mypy src
   ```
4. Commit using Conventional Commits format
5. Push: `git push origin feature/my-new-feature`
6. Open a Pull Request — use the [PR template](.github/PULL_REQUEST_TEMPLATE.md)

**Requirements for merging:**
- All CI checks must pass (tests, lint, type check, security)
- Minimum 80% code coverage maintained
- CHANGELOG.md updated in the `[Unreleased]` section for user-facing changes
- No breaking changes to the CLI contract (commands, flags, exit codes)

## Code Review Process

1. Automated checks run first (CI)
2. At least one maintainer review required
3. Address feedback or explain your decisions
4. Once approved, maintainer merges

## Reporting Issues

- Use the [issue chooser](https://github.com/elruleh/loghop/issues/new/choose) for bugs and feature requests
- For security issues: [private reporting channel](https://github.com/elruleh/loghop/security/advisories/new)

## Additional Resources

- [Operations guide](docs/operations.md) — support scope, rollback, recovery
- [Release process](docs/how-to/release.md) — pre-release audit, discipline rules, step-by-step release
- [Compatibility policy](docs/compatibility.md) — backward compatibility promises
- [Security policy](SECURITY.md) — threat model and reporting

## Labels

| Label | Meaning |
|-------|---------|
| `bug` | Confirmed bug |
| `enhancement` | New feature request |
| `documentation` | Docs-only change |
| `security` | Security-related |
| `good first issue` | Starter task for new contributors |
