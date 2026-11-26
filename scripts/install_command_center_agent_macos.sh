#!/bin/bash
# Install Command Center Agent as a macOS launchd service
#
# Supports multiple codebases per Mac Mini — each gets its own service instance
# identified by CODEBASE_NAME. The plist label, log file, and lockfile are all
# namespaced by codebase name to avoid conflicts.
#
# Usage:
#   ./scripts/install_command_center_agent_macos.sh
#
# The script reads COMMAND_CENTER_URL, COMMAND_CENTER_API_KEY, CODEBASE_NAME,
# and MACHINE_NAME from the project's .env file. These must be set before running.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TRIGGER_DIR="$REPO_ROOT/adws/adw_triggers"
USERNAME=$(whoami)
ENV_FILE="$REPO_ROOT/.env"

# ─── Load .env ──────────────────────────────────────────────────

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found at $ENV_FILE"
    echo "Copy .env.sample to .env and configure it first."
    exit 1
fi

# Source .env (handle values with and without quotes)
set -a
source "$ENV_FILE"
set +a

# ─── Validate required vars ────────────────────────────────────

MISSING=""
[ -z "$COMMAND_CENTER_URL" ] && MISSING="$MISSING COMMAND_CENTER_URL"
[ -z "$COMMAND_CENTER_API_KEY" ] && MISSING="$MISSING COMMAND_CENTER_API_KEY"
[ -z "$CODEBASE_NAME" ] && MISSING="$MISSING CODEBASE_NAME"
[ -z "$MACHINE_NAME" ] && MISSING="$MISSING MACHINE_NAME"

if [ -n "$MISSING" ]; then
    echo "Error: Missing required variables in .env:$MISSING"
    echo ""
    echo "Set these in $ENV_FILE before running this script."
    exit 1
fi

# ─── Derive service identity from CODEBASE_NAME ────────────────

# Sanitize codebase name for use in file paths and plist labels
# Replace any non-alphanumeric chars (except hyphen) with hyphen
SAFE_NAME=$(echo "$CODEBASE_NAME" | tr -cs 'a-zA-Z0-9-' '-' | sed 's/^-//;s/-$//')
PLIST_LABEL="com.ayzer.cc-agent.${SAFE_NAME}"
PLIST_NAME="${PLIST_LABEL}.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"
LOG_FILE="/tmp/cc-agent-${SAFE_NAME}.log"

# ─── Find dependencies ─────────────────────────────────────────

UV_PATH=$(which uv 2>/dev/null)
if [ -z "$UV_PATH" ]; then
    echo "Error: 'uv' not found in PATH"
    echo "Please install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# ─── Display configuration ─────────────────────────────────────

echo "=== Command Center Agent - macOS Service Installer ==="
echo ""
echo "Codebase:    $CODEBASE_NAME"
echo "Machine:     $MACHINE_NAME"
echo "Server:      $COMMAND_CENTER_URL"
echo "Project:     $REPO_ROOT"
echo ""
echo "Service:     $PLIST_LABEL"
echo "Plist:       $PLIST_DEST"
echo "Log file:    $LOG_FILE"
echo "uv path:     $UV_PATH"
echo ""

# ─── Handle existing service ───────────────────────────────────

if launchctl list 2>/dev/null | grep -q "$PLIST_LABEL"; then
    echo "Stopping existing service ($PLIST_LABEL)..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# ─── Build environment dict entries ────────────────────────────
# Collect all env vars that the agent needs. The .env file is the source of truth.

build_env_entry() {
    local key="$1" val="$2"
    if [ -n "$val" ]; then
        echo "        <key>$key</key>"
        echo "        <string>$val</string>"
    fi
}

# ─── Generate plist ────────────────────────────────────────────

mkdir -p "$HOME/Library/LaunchAgents"

echo "Generating plist..."
cat > "$PLIST_DEST" << PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>exec ${UV_PATH} run trigger_command_center.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${TRIGGER_DIR}</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>${LOG_FILE}</string>

    <key>StandardErrorPath</key>
    <string>${LOG_FILE}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/Users/${USERNAME}/.local/bin</string>
        <key>HOME</key>
        <string>/Users/${USERNAME}</string>

        <key>COMMAND_CENTER_URL</key>
        <string>${COMMAND_CENTER_URL}</string>
        <key>COMMAND_CENTER_API_KEY</key>
        <string>${COMMAND_CENTER_API_KEY}</string>
        <key>CODEBASE_NAME</key>
        <string>${CODEBASE_NAME}</string>
        <key>MACHINE_NAME</key>
        <string>${MACHINE_NAME}</string>

        <key>ANTHROPIC_API_KEY</key>
        <string>${ANTHROPIC_API_KEY}</string>
$([ -n "$CLAUDE_CODE_PATH" ] && build_env_entry "CLAUDE_CODE_PATH" "$CLAUDE_CODE_PATH")
$([ -n "$GITHUB_PAT" ] && build_env_entry "GITHUB_PAT" "$GITHUB_PAT")
$([ -n "$CC_AGENT_HEALTH_PORT" ] && build_env_entry "CC_AGENT_HEALTH_PORT" "$CC_AGENT_HEALTH_PORT")
$([ -n "$E2B_API_KEY" ] && build_env_entry "E2B_API_KEY" "$E2B_API_KEY")
$([ -n "$CLOUDFLARED_TUNNEL_TOKEN" ] && build_env_entry "CLOUDFLARED_TUNNEL_TOKEN" "$CLOUDFLARED_TUNNEL_TOKEN")
    </dict>
</dict>
</plist>
PLIST_EOF

# ─── Validate & load ───────────────────────────────────────────

echo "Validating plist..."
if ! plutil -lint "$PLIST_DEST" > /dev/null; then
    echo "Error: Invalid plist file. Check the generated file at:"
    echo "  $PLIST_DEST"
    exit 1
fi

echo "Loading service..."
launchctl load "$PLIST_DEST"

sleep 1
if launchctl list 2>/dev/null | grep -q "$PLIST_LABEL"; then
    echo ""
    echo "=== Service installed and running ==="
    echo ""
    echo "View logs:"
    echo "  tail -f $LOG_FILE"
    echo ""
    echo "Management commands:"
    echo "  Stop:    launchctl unload $PLIST_DEST"
    echo "  Start:   launchctl load $PLIST_DEST"
    echo "  Status:  launchctl list | grep cc-agent"
    echo "  Uninstall: launchctl unload $PLIST_DEST && rm $PLIST_DEST"
    echo ""

    # Show all cc-agent services on this machine
    AGENT_COUNT=$(launchctl list 2>/dev/null | grep -c "com.ayzer.cc-agent" || true)
    if [ "$AGENT_COUNT" -gt 1 ]; then
        echo "Active command center agents on this machine ($AGENT_COUNT):"
        launchctl list 2>/dev/null | grep "com.ayzer.cc-agent" | awk '{print "  " $3}'
    fi
else
    echo ""
    echo "Warning: Service may not have started. Check logs:"
    echo "  tail $LOG_FILE"
fi
