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
export XDG_DATA_DIRS="$TEST_DIR/system/share"

MOCK_BIN="$TEST_DIR/mock-bin"
mkdir -p "$XDG_DATA_HOME/icons/CustomTheme/cursors" \
  "$XDG_DATA_DIRS/icons/SystemTheme/hyprcursors" \
  "$MOCK_BIN" \
  "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"

cp /usr/share/icons/Adwaita/cursors/left_ptr "$XDG_DATA_HOME/icons/CustomTheme/cursors/left_ptr"
printf "[Icon Theme]\nName=CustomTheme\n" > "$XDG_DATA_HOME/icons/CustomTheme/index.theme"

MOCK_LOG="$TEST_DIR/mock_calls.log"

cat <<EOF > "$MOCK_BIN/gsettings"
#!/bin/sh
echo "gsettings \$*" >> "$MOCK_LOG"
if [ "\$1" = "get" ] && [ "\$3" = "cursor-theme" ]; then echo "'CustomTheme'"; exit 0; fi
if [ "\$1" = "get" ] && [ "\$3" = "cursor-size" ]; then echo "48"; exit 0; fi
exit 0
EOF
chmod +x "$MOCK_BIN/gsettings"

cat <<EOF > "$MOCK_BIN/systemctl"
#!/bin/sh
echo "systemctl \$*" >> "$MOCK_LOG"
if [ "\$1" = "--user" ] && [ "\$2" = "show-environment" ]; then
  echo "XCURSOR_THEME=CustomTheme"
  echo "XCURSOR_SIZE=48"
  exit 0
fi
exit 0
EOF
chmod +x "$MOCK_BIN/systemctl"

cat <<EOF > "$MOCK_BIN/hyprctl"
#!/bin/sh
echo "hyprctl \$*" >> "$MOCK_LOG"
exit 0
EOF
chmod +x "$MOCK_BIN/hyprctl"

cat <<EOF > "$MOCK_BIN/dbus-update-activation-environment"
#!/bin/sh
echo "dbus-update-activation-environment \$*" >> "$MOCK_LOG"
exit 0
EOF
chmod +x "$MOCK_BIN/dbus-update-activation-environment"

PATH="$MOCK_BIN:/usr/bin:/bin"

# 1. Step 1: Initialize plugin environment
PLUGIN_DIR="$TEST_DIR/mock_plugins/sanjyay.cursor-theme-manager"
mkdir -p "$PLUGIN_DIR"
cp -a "$ROOT"/. "$PLUGIN_DIR"/

"$PLUGIN_DIR/scripts/cursorctl" snapshot-original-state
"$PLUGIN_DIR/scripts/cursorctl" install-cleanup-helper --source "$PLUGIN_DIR"
"$PLUGIN_DIR/scripts/cursorctl" register-app --source "$PLUGIN_DIR"
"$PLUGIN_DIR/scripts/cursorctl" apply --hyprcursor CustomTheme --xcursor CustomTheme --size 96 --commit

# Verify snapshot recorded CustomTheme and 48px, with absent HYPRCURSOR
SNAPSHOT_FILE="$XDG_STATE_HOME/cursor-theme-manager/snapshot.json"
[[ -f "$SNAPSHOT_FILE" ]]

python3 - "$SNAPSHOT_FILE" <<'PY_INNER'
import json, sys
snap = json.load(open(sys.argv[1]))
assert snap["version"] == 2
assert snap["gtkTheme"]["present"] == True and snap["gtkTheme"]["value"] == "CustomTheme"
assert snap["gtkSize"]["present"] == True and snap["gtkSize"]["value"] == 48
env = snap["systemdEnvironment"]
assert env["XCURSOR_THEME"] == {"present": True, "value": "CustomTheme"}
assert env["XCURSOR_SIZE"] == {"present": True, "value": "48"}
assert env["HYPRCURSOR_THEME"]["present"] == False
assert env["HYPRCURSOR_SIZE"]["present"] == False
PY_INNER

# Verify active artifacts
AUDIT_ACTIVE=$("$XDG_DATA_HOME/omarchy-cursor-switcher/omarchy-cursor-switcher-cleanup" audit-installation)
python3 -c "import sys, json; rep = json.loads(sys.argv[1]); assert rep['is_clean'] == False; assert rep['desktop_entry'] == True" "$AUDIT_ACTIVE"

# 2. Test DISABLE lifecycle (plugin dir still exists)
# on-destroy should deactivate cursor, unregister app, but keep snapshot & state
"$XDG_DATA_HOME/omarchy-cursor-switcher/omarchy-cursor-switcher-cleanup" on-destroy --plugin-dir "$PLUGIN_DIR"

[[ ! -e "$HOME/.local/bin/omarchy-cursor-switcher" ]]
[[ ! -e "$XDG_DATA_HOME/applications/omarchy-cursor-switcher.desktop" ]]
[[ ! -e "$XDG_DATA_HOME/icons/hicolor/scalable/apps/omarchy-cursor-switcher.svg" ]]
[[ ! -e "$XDG_CONFIG_HOME/uwsm/env.d/90-omarchy-cursor-switcher" ]]
[[ ! -e "$XDG_CONFIG_HOME/uwsm/env-hyprland.d/90-omarchy-cursor-switcher" ]]

# State & snapshot must remain intact during simple disable
[[ -f "$SNAPSHOT_FILE" ]]

# Verify gsettings was restored to CustomTheme and 48px
grep -q "gsettings set org.gnome.desktop.interface cursor-theme CustomTheme" "$MOCK_LOG"
grep -q "gsettings set org.gnome.desktop.interface cursor-size 48" "$MOCK_LOG"

# Verify systemctl unset HYPRCURSOR_THEME (since it did not exist prior)
grep -q "systemctl --user unset-environment HYPRCURSOR_THEME" "$MOCK_LOG"

# 3. Test UNINSTALL / DESTROY lifecycle (plugin checkout deleted)
# Re-activate integration to simulate active plugin being uninstalled
"$PLUGIN_DIR/scripts/cursorctl" register-app --source "$PLUGIN_DIR"
rm -rf "$PLUGIN_DIR"

# Now run on-destroy when plugin directory is GONE -> triggers full purge
"$XDG_DATA_HOME/omarchy-cursor-switcher/omarchy-cursor-switcher-cleanup" on-destroy --plugin-dir "$PLUGIN_DIR"

# Verify all traces purged
[[ ! -e "$HOME/.local/bin/omarchy-cursor-switcher" ]]
[[ ! -e "$XDG_DATA_HOME/applications/omarchy-cursor-switcher.desktop" ]]
[[ ! -e "$XDG_DATA_HOME/icons/hicolor/scalable/apps/omarchy-cursor-switcher.svg" ]]
[[ ! -e "$XDG_DATA_HOME/omarchy-cursor-switcher" ]]
[[ ! -e "$SNAPSHOT_FILE" ]]
[[ ! -e "$XDG_STATE_HOME/cursor-theme-manager/state.json" ]]
[[ ! -e "$XDG_CACHE_HOME/omarchy-cursor-switcher" ]]

echo "removal lifecycle tests: ok"
