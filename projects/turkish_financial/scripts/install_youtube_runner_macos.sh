#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="$(command -v python3)"
PLIST_PATH="$HOME/Library/LaunchAgents/com.turkishfinancial.youtube-runner.plist"
LOG_DIR="$PROJECT_DIR/.local"

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

cat >"$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.turkishfinancial.youtube-runner</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>$PROJECT_DIR/scripts/youtube_runner_server.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$PROJECT_DIR</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/youtube-runner.launchd.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/youtube-runner.launchd.error.log</string>
</dict>
</plist>
PLIST

USER_DOMAIN="gui/$(id -u)"
launchctl bootout "$USER_DOMAIN/com.turkishfinancial.youtube-runner" 2>/dev/null || true
launchctl bootstrap "$USER_DOMAIN" "$PLIST_PATH"

echo "Local YouTube runner is ready at http://127.0.0.1:8765."
echo "Open the finance dashboard and click Run local video transcription."
