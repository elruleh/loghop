## Description

<!-- A brief description of the change. What does it fix or add? -->

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change)
- [ ] Documentation update (changes to docs only)

## Testing

<!-- Describe how you tested this change (manual steps, automated tests, etc.) -->

## Checklist

- [ ] Tests added or updated
- [ ] CHANGELOG.md updated (Unreleased section)
- [ ] `uv run ruff format --check src tests scripts` passes
- [ ] `uv run ruff check src tests scripts` passes
- [ ] `uv run mypy src` passes
- [ ] `uv run pytest --cov=loghop` passes
- [ ] If adding a new provider: fixtures added in `tests/fixtures/transcripts/`

## Additional context

<!-- Add any other relevant context here (screenshots, related issues, etc.) -->
