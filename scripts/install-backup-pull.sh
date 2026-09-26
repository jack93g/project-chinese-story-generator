#!/usr/bin/env bash
# Schedules scripts/pull-backups.sh on this Mac: every Monday at 09:00 local
# time, via a launchd agent. If the Mac is asleep then, launchd runs it at the
# next wake. Re-run this after moving the repo; it replaces the old agent.
#
#   scripts/install-backup-pull.sh              install or update
#   scripts/install-backup-pull.sh --uninstall  remove
#
# Output goes to ~/Library/Logs/huaben-backup-pull.log.
set -euo pipefail

label="app.huaben.backup-pull"
plist="$HOME/Library/LaunchAgents/$label.plist"
domain="gui/$(id -u)"

launchctl bootout "$domain/$label" 2>/dev/null || true

if [[ "${1:-}" == "--uninstall" ]]; then
  rm -f "$plist"
  echo "removed $label"
  exit 0
fi

script="$(cd "$(dirname "$0")" && pwd)/pull-backups.sh"
log="$HOME/Library/Logs/huaben-backup-pull.log"
mkdir -p "$(dirname "$plist")" "$(dirname "$log")"

cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$script</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>1</integer>
    <key>Hour</key>
    <integer>9</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$log</string>
  <key>StandardErrorPath</key>
  <string>$log</string>
</dict>
</plist>
EOF

plutil -lint "$plist" >/dev/null
launchctl bootstrap "$domain" "$plist"
echo "installed $label: Mondays 09:00, runs $script"
echo "run it now with: launchctl kickstart $domain/$label"
