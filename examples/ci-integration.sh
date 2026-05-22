#!/bin/bash
# CI integration example for loghop
# This script shows how to use loghop in automated pipelines

set -e

PROVIDER="${1:-claude}"
GOAL="${2:-CI pipeline maintenance}"

echo "=== loghop CI Integration ==="
echo "Provider: $PROVIDER"
echo "Goal: $GOAL"
echo ""

# Check provider is available
echo "1. Checking provider..."
if ! loghop providers | grep -q "$PROVIDER"; then
    echo "❌ Provider '$PROVIDER' not found"
    echo "   Available providers:"
    loghop providers
    exit 1
fi
echo "   ✅ Provider '$PROVIDER' available"
echo ""

# Show project status
echo "2. Project status..."
loghop status
echo ""

# Run session with provider
echo "3. Running session with timeout..."
timeout 300 loghop run --provider "$PROVIDER" --goal "$GOAL" --timeout 300 || {
    EXIT=$?
    if [ $EXIT -eq 3 ]; then
        echo "   ⏱️  Session timed out (expected for long tasks)"
    else
        echo "   ⚠️  Session exited with code $EXIT"
    fi
}
echo ""

# Show session summary
echo "4. Recent sessions..."
loghop sessions list
echo ""

echo "=== CI Integration Complete ==="
