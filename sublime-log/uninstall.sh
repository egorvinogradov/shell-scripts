#!/bin/zsh
# Stop and remove the Sublime change-log watcher. Logs are kept unless you pass --purge.
set -u
LABEL="com.egor.sublime-log"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
CONFIG="$HOME/.config/sublime-log/config.json"
LOG_DIR=""
[[ -f "$CONFIG" ]] && LOG_DIR="$(/usr/bin/python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["log_dir"])' "$CONFIG" 2>/dev/null || true)"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
for d in "$HOME/Library/Application Support"/Sublime\ Text*/Packages/User(N); do rm -f "$d/sublime_log_live.py"; done
rm -f "$PLIST" "$HOME/.local/bin/sublime_log"
if [[ "${1:-}" == "--purge" ]]; then
  rm -rf "$HOME/.config/sublime-log"
  [[ -n "$LOG_DIR" && -d "$LOG_DIR" ]] && rm -rf "$LOG_DIR" && echo "deleted log dir $LOG_DIR"
else
  echo "kept the logs${LOG_DIR:+ in $LOG_DIR} (and the config). Run with --purge to delete them too."
fi
echo "uninstalled."
