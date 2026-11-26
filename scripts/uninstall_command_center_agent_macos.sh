#!/bin/bash
# Uninstall Command Center Agent macOS launchd service
#
# Stops and removes the launchd service for this codebase's command center agent.
# Reads CODEBASE_NAME from .env to identify which service to remove.
#
# Usage:
#   ./scripts/uninstall_command_center_agent_macos.sh
#
# To uninstall ALL command center agents on this machine:
#   ./scripts/uninstall_command_center_agent_macos.sh --all

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

# ─── Handle --all flag ──────────────────────────────────────────

if [ "${1:-}" = "--all" ]; then
    echo "=== Uninstalling ALL command center agents ==="
    echo ""

    FOUND=0
    for plist in "$HOME/Library/LaunchAgents"/com.ayzer.cc-agent.*.plist; do
        [ -f "$plist" ] || continue
        FOUND=$((FOUND + 1))
        LABEL=$(basename "$plist" .plist)
        SAFE_NAME=$(echo "$LABEL" | sed 's/com\.ayzer\.cc-agent\.//')

        echo "Stopping $LABEL..."
        launchctl unload "$plist" 2>/dev/null || true

        echo "Removing $plist"
        rm -f "$plist"

        LOG_FILE="/tmp/cc-agent-${SAFE_NAME}.log"
        LOCK_FILE="/tmp/cc-agent-${SAFE_NAME}.lock"
        [ -f "$LOG_FILE" ] && rm -f "$LOG_FILE" && echo "Removed $LOG_FILE"
        [ -f "$LOCK_FILE" ] && rm -f "$LOCK_FILE" && echo "Removed $LOCK_FILE"
        echo ""
    done

    if [ "$FOUND" -eq 0 ]; then
        echo "No command center agents found."
    else
        echo "=== Uninstalled $FOUND agent(s) ==="
    fi
    exit 0
fi

# ─── Single codebase uninstall ──────────────────────────────────

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found at $ENV_FILE"
    echo "Cannot determine CODEBASE_NAME. Use --all to remove all agents."
    exit 1
fi

# Source .env
set -a
source "$ENV_FILE"
set +a

if [ -z "$CODEBASE_NAME" ]; then
    echo "Error: CODEBASE_NAME not set in .env"
    echo "Use --all to remove all agents on this machine."
    exit 1
fi

SAFE_NAME=$(echo "$CODEBASE_NAME" | tr -cs 'a-zA-Z0-9-' '-' | sed 's/^-//;s/-$//')
PLIST_LABEL="com.ayzer.cc-agent.${SAFE_NAME}"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
LOG_FILE="/tmp/cc-agent-${SAFE_NAME}.log"
LOCK_FILE="/tmp/cc-agent-${SAFE_NAME}.lock"

echo "=== Uninstalling Command Center Agent ==="
echo ""
echo "Codebase: $CODEBASE_NAME"
echo "Service:  $PLIST_LABEL"
echo ""

# Stop the service
if launchctl list 2>/dev/null | grep -q "$PLIST_LABEL"; then
    echo "Stopping service..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
    echo "Service stopped."
else
    echo "Service not running."
fi

# Remove plist
if [ -f "$PLIST_DEST" ]; then
    rm -f "$PLIST_DEST"
    echo "Removed $PLIST_DEST"
else
    echo "Plist not found (already removed)."
fi

# Clean up log and lock files
[ -f "$LOG_FILE" ] && rm -f "$LOG_FILE" && echo "Removed $LOG_FILE"
[ -f "$LOCK_FILE" ] && rm -f "$LOCK_FILE" && echo "Removed $LOCK_FILE"

echo ""
echo "=== Uninstall complete ==="

# Show remaining agents
REMAINING=$(ls "$HOME/Library/LaunchAgents"/com.ayzer.cc-agent.*.plist 2>/dev/null | wc -l | tr -d ' ')
if [ "$REMAINING" -gt 0 ]; then
    echo ""
    echo "Remaining agents on this machine ($REMAINING):"
    for plist in "$HOME/Library/LaunchAgents"/com.ayzer.cc-agent.*.plist; do
        [ -f "$plist" ] || continue
        echo "  $(basename "$plist" .plist | sed 's/com\.ayzer\.cc-agent\.//')"
    done
fi
