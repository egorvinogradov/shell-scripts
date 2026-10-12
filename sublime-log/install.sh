#!/bin/zsh
# Install the Sublime change-log watcher: launchd agent (starts at login, restarts if it dies) + `sublime_log` command.
#   ./install.sh                      default log dir ~/.local/share/sublime-log
#   ./install.sh --log-dir PATH       store the log elsewhere (remembered in ~/.config/sublime-log/config.json)
# Safe to re-run (it replaces the previous install). Remove with ./uninstall.sh.
set -eu
HERE="${0:A:h}"
LABEL="com.egor.sublime-log"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
CONFIG_DIR="$HOME/.config/sublime-log"
BIN_DIR="$HOME/.local/bin"
LOG_DIR="${SUBLIME_LOG_DIR:-}"
[[ -z "$LOG_DIR" && -f "$CONFIG_DIR/config.json" ]] && LOG_DIR="$(/usr/bin/python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["log_dir"])' "$CONFIG_DIR/config.json" 2>/dev/null || true)"
while (( $# )); do
  case "$1" in
    --log-dir) LOG_DIR="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
LOG_DIR="${LOG_DIR:-$HOME/.local/share/sublime-log}"
LOG_DIR="${LOG_DIR/#\~/$HOME}"

# a python >= 3.8 as an absolute path (launchd has no useful PATH); first hit wins
PY=""
for c in "$(command -v python3 || true)" /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  [[ -x "$c" ]] && "$c" -c 'import sys;sys.exit(0 if sys.version_info>=(3,8) else 1)' 2>/dev/null && { PY="$c"; break; }
done
[[ -n "$PY" ]] || { echo "need python3 >= 3.8" >&2; exit 1; }

mkdir -p "$LOG_DIR" "$CONFIG_DIR" "$BIN_DIR" "$HOME/Library/LaunchAgents"
chmod 700 "$LOG_DIR"
print -r -- "{\"log_dir\": \"$LOG_DIR\"}" > "$CONFIG_DIR/config.json"
ln -sf "$HERE/sublime_log" "$BIN_DIR/sublime_log"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>$PY</string><string>$HERE/sublime_log_watcher.py</string><string>--log-dir</string><string>$LOG_DIR</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$LOG_DIR/watcher.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/watcher.log</string>
</dict></plist>
PLIST

UIDN="$(id -u)"
launchctl bootout "gui/$UIDN/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UIDN" "$PLIST"
launchctl kickstart -k "gui/$UIDN/$LABEL" 2>/dev/null || true

echo "installed."
echo "  watcher : $LABEL  (python: $PY)"
echo "  log dir : $LOG_DIR"
echo "  command : sublime_log   (make sure $BIN_DIR is on PATH)"
sleep 2
"$BIN_DIR/sublime_log" status || true
