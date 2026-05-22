#!/bin/bash
# Basic loghop usage example
# Usage: ./examples/basic-usage.sh

set -e

echo "=== loghop Basic Usage Example ==="
echo ""

# Check if in a git repo
if ! git rev-parse --is-inside-work-tree 2>/dev/null; then
    echo "⚠️  Not in a git repository. Create one first:"
    echo "   mkdir my-project && cd my-project && git init"
    exit 1
fi

# Show current status
echo "1. Current project status:"
loghop status || echo "   (Not initialized yet)"
echo ""

# Initialize if needed
if [ ! -d ".loghop" ]; then
    echo "2. Initializing loghop..."
    loghop init --no-prompt
    echo "   ✅ Project initialized"
    echo ""
fi

# Set a goal
echo "3. Setting project goal..."
loghop goal "Add user authentication to the project"
echo ""

# Show status with goal
echo "4. Status with goal:"
loghop status
echo ""

# List providers
echo "5. Available providers:"
loghop providers
echo ""

echo "=== Ready! ==="
echo "Run 'loghop run' to start a session"
echo "Run 'loghop goal \"new goal\"' to update the goal"
