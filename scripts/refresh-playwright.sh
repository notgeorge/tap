#!/usr/bin/env bash
# refresh-playwright.sh — Kill all stale Playwright MCP processes.
#
# After running this, restart Claude Code (exit and re-run `claude`)
# so it spawns a fresh MCP connection.
#
# Usage:
#   ./scripts/refresh-playwright.sh

set -euo pipefail

echo "Looking for Playwright MCP processes..."

PIDS=$(pgrep -f 'playwright-mcp' 2>/dev/null || true)

if [ -z "$PIDS" ]; then
    echo "No Playwright MCP processes found."
else
    echo "Killing PIDs: $PIDS"
    echo "$PIDS" | xargs kill 2>/dev/null || true
    sleep 1

    # Check for stragglers.
    REMAINING=$(pgrep -f 'playwright-mcp' 2>/dev/null || true)
    if [ -n "$REMAINING" ]; then
        echo "Force-killing remaining: $REMAINING"
        echo "$REMAINING" | xargs kill -9 2>/dev/null || true
    fi

    echo "Done. All Playwright MCP processes killed."
fi

# Also kill any orphaned parent npm processes.
NPM_PIDS=$(pgrep -f '@playwright/mcp' 2>/dev/null || true)
if [ -n "$NPM_PIDS" ]; then
    echo "Killing parent npm processes: $NPM_PIDS"
    echo "$NPM_PIDS" | xargs kill 2>/dev/null || true
fi

echo ""
echo "Next step: restart Claude Code so it spawns a fresh MCP connection."
