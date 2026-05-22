# Examples

This directory contains example scripts for using loghop.

## Scripts

### basic-usage.sh

Basic workflow example showing how to:
- Initialize a project
- Set a goal
- Check status
- Use providers

```bash
./basic-usage.sh
```

### provider-switch.py

Python example demonstrating how to:
- Check available providers
- Run loghop commands programmatically
- Handle errors gracefully

```bash
python3 examples/provider-switch.py
```

### ci-integration.sh

Example of using loghop in CI/CD pipelines:
- Provider validation
- Timeout handling
- Session status checking

```bash
# Use Claude Code for CI tasks
./ci-integration.sh claude "CI pipeline maintenance"

# Use Codex for CI tasks
./ci-integration.sh codex "Update dependencies"
```

## Prerequisites

- loghop installed (`pipx install loghop`)
- Git repository initialized
- Provider (claude or codex) on PATH

## Quick Start

```bash
# Inside any Git repo:
loghop init
loghop run
```
