#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd)
TEST_DIR=$(mktemp -d)
export TEST_DIR
trap "rm -rf -- \"$TEST_DIR\"" EXIT

export HOME="$TEST_DIR/home"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_CONFIG_HOME="$TEST_DIR/config"
export XDG_CACHE_HOME="$TEST_DIR/cache"
export XDG_DATA_DIRS="$TEST_DIR/system/share"

MOCK_BIN="$TEST_DIR/mock-bin"
mkdir -p "$XDG_DATA_HOME/icons/CustomTheme/cursors" \
  "$XDG_DATA_DIRS/icons/SystemTheme/hyprcursors" \
  "$MOCK_BIN" \
  "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"

cp "$ROOT/themes/banana/generated/Banana/cursors/left_ptr" "$XDG_DATA_HOME/icons/CustomTheme/cursors/left_ptr"
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
PLUGIN_DIR="$TEST_DIR/mock_plugins/goblin.cursor-switcher"
mkdir -p "$PLUGIN_DIR"
cp -a "$ROOT"/. "$PLUGIN_DIR"/

"$PLUGIN_DIR/scripts/cursorctl" snapshot-original-state
"$PLUGIN_DIR/scripts/cursorctl" install-cleanup-helper --source "$PLUGIN_DIR"
"$PLUGIN_DIR/scripts/cursorctl" install-bundled --source "$PLUGIN_DIR/themes/banana/generated/Banana" --target "$XDG_DATA_HOME/icons/Banana" --version 2.0.0
"$PLUGIN_DIR/scripts/cursorctl" register-app --source "$PLUGIN_DIR"
"$PLUGIN_DIR/scripts/cursorctl" apply --hyprcursor Banana --xcursor Banana --size 96 --commit

# Verify snapshot recorded CustomTheme and 48px, with absent HYPRCURSOR
SNAPSHOT_FILE="$XDG_CONFIG_HOME/omarchy/cursor-switcher-original-state.json"
[[ -f $SNAPSHOT_FILE ]]

python3 - "$SNAPSHOT_FILE" <<PY
import json, sys
snap = json.load(open(sys.argv[1]))
assert snap["version"] == 1
assert snap["gtkTheme"]["present"] == True and snap["gtkTheme"]["value"] == "CustomTheme"
assert snap["gtkSize"]["present"] == True and snap["gtkSize"]["value"] == 48
assert snap["xcursorTheme"]["present"] == True and snap["xcursorTheme"]["value"] == "CustomTheme"
assert snap["xcursorSize"]["present"] == True and snap["xcursorSize"]["value"] == "48"
assert snap["hyprcursorTheme"]["present"] == False
assert snap["hyprcursorSize"]["present"] == False
PY

# Verify active artifacts
AUDIT_ACTIVE=$("$XDG_DATA_HOME/omarchy-cursor-switcher/omarchy-cursor-switcher-cleanup" audit-installation)
python3 -c "import sys, json; rep = json.loads(sys.argv[1]); assert rep['is_clean'] == False; assert rep['desktop_entry'] == True; assert 'Banana' in rep['bundled_themes']" "$AUDIT_ACTIVE"

# 2. Test DISABLE lifecycle (plugin dir still exists)
# on-destroy should deactivate cursor, unregister app, but keep bundled themes & state
"$XDG_DATA_HOME/omarchy-cursor-switcher/omarchy-cursor-switcher-cleanup" on-destroy --plugin-dir "$PLUGIN_DIR"

[[ ! -e "$HOME/.local/bin/omarchy-cursor-switcher" ]]
[[ ! -e "$XDG_DATA_HOME/applications/omarchy-cursor-switcher.desktop" ]]
[[ ! -e "$XDG_DATA_HOME/icons/hicolor/scalable/apps/omarchy-cursor-switcher.svg" ]]
[[ ! -e "$XDG_CONFIG_HOME/uwsm/env.d/90-omarchy-cursor-switcher" ]]
[[ ! -e "$XDG_CONFIG_HOME/uwsm/env-hyprland.d/90-omarchy-cursor-switcher" ]]

# Verify gsettings and systemctl restored CustomTheme / 48
grep -q "gsettings set org.gnome.desktop.interface cursor-theme CustomTheme" "$MOCK_LOG"
grep -q "gsettings set org.gnome.desktop.interface cursor-size 48" "$MOCK_LOG"
grep -q "systemctl --user unset-environment HYPRCURSOR_THEME" "$MOCK_LOG"

# Verify bundled theme and snapshot were preserved during disable
[[ -d "$XDG_DATA_HOME/icons/Banana" ]]
[[ -f "$SNAPSHOT_FILE" ]]

# 3. Re-enable plugin (re-register app)
"$PLUGIN_DIR/scripts/cursorctl" register-app --source "$PLUGIN_DIR"
"$PLUGIN_DIR/scripts/cursorctl" apply --hyprcursor Banana --xcursor Banana --size 96 --commit
[[ -f "$XDG_DATA_HOME/applications/omarchy-cursor-switcher.desktop" ]]

# 4. Test REMOVAL lifecycle (plugin dir deleted)
# Simulate omarchy-plugin-remove removing directory
rm -rf -- "$PLUGIN_DIR"

# on-destroy should detect plugin dir is missing and trigger full purge
"$XDG_DATA_HOME/omarchy-cursor-switcher/omarchy-cursor-switcher-cleanup" on-destroy --plugin-dir "$PLUGIN_DIR"

# 5. Verify NO traces remain
[[ ! -e "$HOME/.local/bin/omarchy-cursor-switcher" ]]
[[ ! -e "$XDG_DATA_HOME/applications/omarchy-cursor-switcher.desktop" ]]
[[ ! -e "$XDG_DATA_HOME/icons/hicolor/scalable/apps/omarchy-cursor-switcher.svg" ]]
[[ ! -e "$XDG_DATA_HOME/icons/Banana" ]]
[[ ! -e "$XDG_CONFIG_HOME/uwsm/env.d/90-omarchy-cursor-switcher" ]]
[[ ! -e "$XDG_CONFIG_HOME/uwsm/env-hyprland.d/90-omarchy-cursor-switcher" ]]
[[ ! -e "$XDG_CONFIG_HOME/omarchy/cursor-switcher.json" ]]
[[ ! -e "$SNAPSHOT_FILE" ]]
[[ ! -e "$XDG_CACHE_HOME/omarchy-cursor-switcher" ]]
[[ ! -e "$XDG_DATA_HOME/omarchy-cursor-switcher" ]]

# Verify unrelated theme is intact
[[ -d "$XDG_DATA_HOME/icons/CustomTheme" ]]

echo "removal_lifecycle tests: ok"
