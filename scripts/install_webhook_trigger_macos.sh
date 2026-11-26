#!/bin/bash
# Install ADW Webhook Trigger as a macOS launchd service
# This script configures and installs the service to run at login

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_NAME="com.adw.webhook-trigger.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"
TRIGGER_DIR="$REPO_ROOT/adws/adw_triggers"
USERNAME=$(whoami)

# Find uv binary
UV_PATH=$(which uv 2>/dev/null)
if [ -z "$UV_PATH" ]; then
    echo "Error: 'uv' not found in PATH"
    echo "Please install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "=== ADW Webhook Trigger macOS Service Installer ==="
echo ""
echo "Configuration:"
echo "  Username: $USERNAME"
echo "  Working directory: $TRIGGER_DIR"
echo "  Repo root: $REPO_ROOT"
echo "  uv path: $UV_PATH"
echo ""
echo "Log file: /tmp/adw-webhook-trigger.log"
echo ""

# Unload existing service if running
if launchctl list | grep -q "com.adw.webhook-trigger"; then
    echo "Stopping existing service..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# Create LaunchAgents directory if needed
mkdir -p "$HOME/Library/LaunchAgents"

# Generate plist directly (avoids quarantine inheritance from source files)
echo "Generating plist at $PLIST_DEST..."
cat > "$PLIST_DEST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.adw.webhook-trigger</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>exec $UV_PATH run trigger_webhook.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$TRIGGER_DIR</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/tmp/adw-webhook-trigger.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/adw-webhook-trigger.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/Users/$USERNAME/.local/bin</string>
        <key>HOME</key>
        <string>/Users/$USERNAME</string>
    </dict>
</dict>
</plist>
EOF

# Validate plist
echo "Validating plist..."
if ! plutil -lint "$PLIST_DEST" > /dev/null; then
    echo "Error: Invalid plist file"
    exit 1
fi

# Load the service
echo "Loading service..."
launchctl load "$PLIST_DEST"

# Verify it's running
sleep 1
if launchctl list | grep -q "com.adw.webhook-trigger"; then
    echo ""
    echo "=== Service installed and running ==="
    echo ""
    echo "View logs:"
    echo "  tail -f /tmp/adw-webhook-trigger.log"
    echo ""
    echo "Management commands:"
    echo "  Stop:    launchctl unload ~/Library/LaunchAgents/$PLIST_NAME"
    echo "  Start:   launchctl load ~/Library/LaunchAgents/$PLIST_NAME"
    echo "  Status:  launchctl list | grep adw"
else
    echo ""
    echo "Warning: Service may not have started. Check logs:"
    echo "  tail /tmp/adw-webhook-trigger.log"
fi
