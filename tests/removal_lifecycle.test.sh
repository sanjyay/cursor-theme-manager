#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd)
TEST_DIR=$(mktemp -d)
export TEST_DIR
trap 'rm -rf -- "$TEST_DIR"' EXIT

export HOME="$TEST_DIR/home"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_CONFIG_HOME="$TEST_DIR/config"
export XDG_STATE_HOME="$HOME/.local/state"
export XDG_CACHE_HOME="$TEST_DIR/cache"
export XDG_DATA_DIRS="$TEST_DIR/usr/share"

mkdir -p "$HOME" "$XDG_DATA_HOME" "$XDG_CONFIG_HOME" "$XDG_STATE_HOME" "$XDG_CACHE_HOME"

MOCK_BIN="$TEST_DIR/mock_bin"
mkdir -p "$MOCK_BIN"
export MOCK_LOG="$TEST_DIR/mock_calls.log"
touch "$MOCK_LOG"

cat <<'EOF_GS' > "$MOCK_BIN/gsettings"
#!/bin/sh
echo "gsettings $*" >> "$MOCK_LOG"
if [ "$1" = "get" ] && [ "$3" = "cursor-theme" ]; then echo "'Bibata-Modern-Ice'"; exit 0; fi
if [ "$1" = "get" ] && [ "$3" = "cursor-size" ]; then echo "32"; exit 0; fi
exit 0
EOF_GS
chmod +x "$MOCK_BIN/gsettings"

cat <<'EOF_SYS' > "$MOCK_BIN/systemctl"
#!/bin/sh
echo "systemctl $*" >> "$MOCK_LOG"
if [ "$1" = "--user" ] && [ "$2" = "show-environment" ]; then
  echo "XCURSOR_THEME=Bibata-Modern-Ice"
  echo "XCURSOR_SIZE=32"
  exit 0
fi
exit 0
EOF_SYS
chmod +x "$MOCK_BIN/systemctl"

cat <<'EOF_DBUS' > "$MOCK_BIN/dbus-update-activation-environment"
#!/bin/sh
echo "dbus-update-activation-environment $*" >> "$MOCK_LOG"
exit 0
EOF_DBUS
chmod +x "$MOCK_BIN/dbus-update-activation-environment"

cat <<'EOF_HYPR' > "$MOCK_BIN/hyprctl"
#!/bin/sh
echo "hyprctl $*" >> "$MOCK_LOG"
exit 0
EOF_HYPR
chmod +x "$MOCK_BIN/hyprctl"

PATH="$MOCK_BIN:/usr/bin:/bin"

# Create mock themes
mkdir -p "$XDG_DATA_HOME/icons/Bibata-Modern-Ice/cursors"
cp /usr/share/icons/Adwaita/cursors/left_ptr "$XDG_DATA_HOME/icons/Bibata-Modern-Ice/cursors/default"
printf "[Icon Theme]\nName=Bibata-Modern-Ice\n" > "$XDG_DATA_HOME/icons/Bibata-Modern-Ice/index.theme"

mkdir -p "$XDG_DATA_HOME/icons/Banana/cursors" "$XDG_DATA_HOME/icons/Nordzy/cursors"
cp /usr/share/icons/Adwaita/cursors/left_ptr "$XDG_DATA_HOME/icons/Banana/cursors/default"
cp /usr/share/icons/Adwaita/cursors/left_ptr "$XDG_DATA_HOME/icons/Nordzy/cursors/default"
printf "[Icon Theme]\nName=Banana\n" > "$XDG_DATA_HOME/icons/Banana/index.theme"
printf "[Icon Theme]\nName=Nordzy\n" > "$XDG_DATA_HOME/icons/Nordzy/index.theme"

# 1. Fresh state: verify ZERO external artifacts exist before consent
STATUS_INIT=$(PATH="$PATH" "$ROOT/scripts/cursorctl" integration-status)
python3 -c 'import sys, json; data = json.loads(sys.argv[1]); assert data["enabled"] == False; assert data["promptSeen"] == False' "$STATUS_INIT"
[[ ! -e "$XDG_DATA_HOME/applications/cursor-theme-manager.desktop" ]]
[[ ! -e "$HOME/.local/libexec/cursor-theme-manager/cleanup" ]]
[[ ! -e "$XDG_CONFIG_HOME/systemd/user/cursor-theme-manager-cleanup.path" ]]
[[ ! -e "$XDG_CONFIG_HOME/systemd/user/cursor-theme-manager-cleanup.service" ]]

# 2. Enable Integration (User explicitly consents)
ENABLE_RES=$(PATH="$PATH" "$ROOT/scripts/cursorctl" integration-enable)
python3 -c 'import sys, json; data = json.loads(sys.argv[1]); assert data["ok"] == True; assert data["enabled"] == True' "$ENABLE_RES"

DESKTOP_ENTRY="$XDG_DATA_HOME/applications/cursor-theme-manager.desktop"
CLEANUP_EXE="$HOME/.local/libexec/cursor-theme-manager/cleanup"
PATH_UNIT="$XDG_CONFIG_HOME/systemd/user/cursor-theme-manager-cleanup.path"
SERVICE_UNIT="$XDG_CONFIG_HOME/systemd/user/cursor-theme-manager-cleanup.service"

[[ -f "$DESKTOP_ENTRY" ]]
[[ -x "$CLEANUP_EXE" ]]
[[ -f "$PATH_UNIT" ]]
[[ -f "$SERVICE_UNIT" ]]

# Verify integration enabled, cursorModifiedByCtm is False before apply
STATE_FILE="$XDG_STATE_HOME/cursor-theme-manager/state.json"
[[ -f "$STATE_FILE" ]]

python3 -c "
import json
with open('$STATE_FILE') as f: data = json.load(f)
assert data.get('cursorModifiedByCtm', False) == False
"

# 3. Simulate multiple theme applies: Banana / 80, Nordzy / 48, Banana / 24
PATH="$PATH" "$ROOT/scripts/cursorctl" apply --hyprcursor - --xcursor Banana --size 80 --commit

# Verify baseline was captured atomically with first apply
python3 -c "
import json
with open('$STATE_FILE') as f: data = json.load(f)
assert data.get('cursorModifiedByCtm') == True
c = data.get('preCtmCursor') or data.get('originalCursor')
assert c['captured'] == True
assert 'liveTheme' in c or 'gtkTheme' in c or 'xcursorTheme' in c
"

FIRST_BASELINE=$(python3 -c "import json; f=open('$STATE_FILE'); data=json.load(f); f.close(); print(json.dumps(data.get('preCtmCursor') or data.get('originalCursor'), sort_keys=True))")

PATH="$PATH" "$ROOT/scripts/cursorctl" apply --hyprcursor - --xcursor Nordzy --size 48 --commit
PATH="$PATH" "$ROOT/scripts/cursorctl" apply --hyprcursor - --xcursor Banana --size 24 --commit

# Assert baseline is IMMUTABLE and has NOT changed across multiple applies!
python3 -c "
import json
with open('$STATE_FILE') as f: data = json.load(f)
c = data.get('preCtmCursor') or data.get('originalCursor')
first = json.loads('''$FIRST_BASELINE''')
assert json.dumps(c, sort_keys=True) == json.dumps(first, sort_keys=True), f'Baseline changed from {first} to {c}'
"

# 4. Create an imported cursor theme
IMPORTED_THEME_DIR="$XDG_DATA_HOME/icons/CursorSwitcher-Imported-MyUserTheme"
mkdir -p "$IMPORTED_THEME_DIR/cursors"
touch "$IMPORTED_THEME_DIR/cursors/default"
echo "1.0" > "$IMPORTED_THEME_DIR/.omarchy-cursor-switcher-imported"

# 5. Test Watcher No-Op while plugin directory still exists
PLUGIN_DIR="$XDG_CONFIG_HOME/omarchy/plugins/sanjyay.cursor-theme-manager"
mkdir -p "$PLUGIN_DIR"

PATH="$PATH" "$CLEANUP_EXE"
# Verify nothing was deleted
[[ -f "$DESKTOP_ENTRY" ]]
[[ -f "$CLEANUP_EXE" ]]
[[ -f "$STATE_FILE" ]]

# 6. Test Automatic Removal (simulating omarchy plugin remove)
rm -rf "$PLUGIN_DIR"

# Execute cleanup helper (as triggered by systemd user service)
PATH="$PATH" "$CLEANUP_EXE"

# 7. Verify all CTM integration artifacts and state are removed
[[ ! -e "$DESKTOP_ENTRY" ]]
[[ ! -e "$CLEANUP_EXE" ]]
[[ ! -e "$HOME/.local/libexec/cursor-theme-manager" ]]
[[ ! -e "$PATH_UNIT" ]]
[[ ! -e "$SERVICE_UNIT" ]]
[[ ! -e "$STATE_FILE" ]]
[[ ! -e "$XDG_STATE_HOME/cursor-theme-manager" ]]
[[ ! -e "$XDG_CONFIG_HOME/uwsm/env.d/90-omarchy-cursor-switcher" ]]
[[ ! -e "$XDG_CONFIG_HOME/uwsm/env-hyprland.d/90-omarchy-cursor-switcher" ]]

# 8. Assert user's imported theme was PRESERVED
[[ -d "$IMPORTED_THEME_DIR" ]]
[[ -f "$IMPORTED_THEME_DIR/.omarchy-cursor-switcher-imported" ]]

# 10. Reinstall Test: fresh install starts cleanly with zero state
STATUS_REINSTALL=$(PATH="$PATH" "$ROOT/scripts/cursorctl" integration-status)
python3 -c 'import sys, json; data = json.loads(sys.argv[1]); assert data["enabled"] == False; assert data["promptSeen"] == False' "$STATUS_REINSTALL"

echo "removal lifecycle tests: ok"
