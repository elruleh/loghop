#!/usr/bin/env python3
"""
Provider switching example for loghop.

This script demonstrates how to programmatically switch between
Claude Code and Codex while maintaining context through loghop.
"""

import subprocess
import sys
from pathlib import Path


def run_loghop(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a loghop command and return the result."""
    cmd = ["loghop"] + args
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        print(f"❌ Error: {result.stderr}", file=sys.stderr)
        if check:
            sys.exit(result.returncode)
    return result


def check_provider(provider: str) -> bool:
    """Check if a provider is available."""
    result = subprocess.run(["loghop", "providers"], capture_output=True, text=True)
    return provider in result.stdout


def main():
    print("=== loghop Provider Switching Example ===\n")

    # Check available providers
    print("1. Checking available providers...")
    run_loghop(["providers"])
    print()

    # Check if in a git repo
    if not Path(".git").exists():
        print("⚠️  This script should be run inside a git repository.")
        print("   Initialize one with: git init")
        sys.exit(1)

    # Show current status
    print("2. Current project status...")
    run_loghop(["status"])
    print()

    # Initialize if needed
    if not Path(".loghop/config.toml").exists():
        print("3. Initializing project...")
        run_loghop(["init", "--no-prompt"])
        print()

    # Set a goal
    print("4. Setting a goal...")
    run_loghop(["goal", "Build a CLI tool with Python"])
    print()

    # List recent sessions
    print("5. Recent sessions...")
    run_loghop(["sessions", "list"])
    print()

    print("=== Setup Complete ===")
    print("\nTo start a session:")
    print("  loghop run --provider claude    # Use Claude Code")
    print("  loghop run --provider codex     # Use Codex")
    print("  loghop run                     # Use last provider")


if __name__ == "__main__":
    main()
