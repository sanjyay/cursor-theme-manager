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
mkdir -p \
  "$XDG_DATA_HOME/icons/UserOnly/cursors" \
  "$XDG_DATA_HOME/icons/Both/cursors" \
  "$XDG_DATA_HOME/icons/Both/hyprcursors" \
  "$XDG_DATA_DIRS/icons/SystemOnly/cursors" \
  "$XDG_DATA_DIRS/icons/SystemOnly/hyprcursors" \
  "$MOCK_BIN" \
  "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"

cp /usr/share/icons/Adwaita/cursors/left_ptr "$XDG_DATA_HOME/icons/UserOnly/cursors/left_ptr"
printf "[Icon Theme]\nName=User Only\n" > "$XDG_DATA_HOME/icons/UserOnly/index.theme"

cp /usr/share/icons/Adwaita/cursors/left_ptr "$XDG_DATA_HOME/icons/Both/cursors/left_ptr"
printf "[Icon Theme]\nName=Both Formats\n" > "$XDG_DATA_HOME/icons/Both/index.theme"
printf "name = Both-Hypr\nversion = 0.1\ncursors_directory = hyprcursors\n" > "$XDG_DATA_HOME/icons/Both/manifest.hl"

cp /usr/share/icons/Adwaita/cursors/left_ptr "$XDG_DATA_DIRS/icons/SystemOnly/cursors/left_ptr"
printf "[Icon Theme]\nName=System Theme\n" > "$XDG_DATA_DIRS/icons/SystemOnly/index.theme"
printf "name = System-Hypr\nversion = 0.1\ncursors_directory = hyprcursors\n" > "$XDG_DATA_DIRS/icons/SystemOnly/manifest.hl"

cat <<'EOF' > "$MOCK_BIN/gsettings"
#!/bin/sh
if [ "$1" = "get" ] && [ "$3" = "cursor-theme" ]; then
  echo "'Both'"
  exit 0
fi
exit 0
EOF
chmod +x "$MOCK_BIN/gsettings"

PATH="$MOCK_BIN:/usr/bin:/bin"
JSON_OUTPUT=$("$ROOT/scripts/cursorctl" discover)

python3 - "$JSON_OUTPUT" <<'PY_INNER'
import json, sys
data = json.loads(sys.argv[1])
themes = data["themes"]
assert data["currentXcursor"] == "Both"
assert len(themes) == 3

user_only = next(t for t in themes if t["displayName"] == "User Only")
assert user_only["sourceType"] == "user"
assert user_only["formats"] == ["xcursor"]
assert user_only["xcursor"] == "UserOnly"
assert user_only["hyprcursor"] == ""

both = next(t for t in themes if t["displayName"] == "Both Formats")
assert both["sourceType"] == "user"
assert "hyprcursor" in both["formats"]
assert "xcursor" in both["formats"]
assert both["xcursor"] == "Both"
assert both["hyprcursor"] == "Both-Hypr"

system_only = next(t for t in themes if t["displayName"] == "System Theme")
assert system_only["sourceType"] == "system"
assert "hyprcursor" in system_only["formats"]
assert "xcursor" in system_only["formats"]
PY_INNER

cat <<'EOF' > "$MOCK_BIN/hyprctl"
#!/bin/sh
if [ "$1" = "setcursor" ]; then
  echo "SETCURSOR $2 $3" >> "$TEST_DIR/hyprctl.log"
  exit 0
fi
exit 0
EOF
chmod +x "$MOCK_BIN/hyprctl"

# Test Preview
PATH="$MOCK_BIN:/usr/bin:/bin" "$ROOT/scripts/cursorctl" apply --hyprcursor Both-Hypr --xcursor Both --size 48 --preview
grep -q "SETCURSOR Both-Hypr 48" "$TEST_DIR/hyprctl.log"
[[ ! -f "$TEST_DIR/config/uwsm/env.d/90-omarchy-cursor-switcher" ]]

# Test Commit
PATH="$MOCK_BIN:/usr/bin:/bin" XDG_CONFIG_HOME="$TEST_DIR/config" "$ROOT/scripts/cursorctl" apply --hyprcursor Both-Hypr --xcursor Both --size 48 --commit
grep -q "SETCURSOR Both-Hypr 48" "$TEST_DIR/hyprctl.log"
[[ -f "$TEST_DIR/config/uwsm/env.d/90-omarchy-cursor-switcher" ]]
[[ -f "$TEST_DIR/config/uwsm/env-hyprland.d/90-omarchy-cursor-switcher" ]]

grep -q "export XCURSOR_THEME='Both'" "$TEST_DIR/config/uwsm/env.d/90-omarchy-cursor-switcher"
grep -q "export XCURSOR_SIZE='48'" "$TEST_DIR/config/uwsm/env.d/90-omarchy-cursor-switcher"
grep -q "export HYPRCURSOR_THEME='Both-Hypr'" "$TEST_DIR/config/uwsm/env-hyprland.d/90-omarchy-cursor-switcher"
grep -q "export HYPRCURSOR_SIZE='48'" "$TEST_DIR/config/uwsm/env-hyprland.d/90-omarchy-cursor-switcher"

# Test CLI theme import and removal
STAGE_ARCHIVE="$TEST_DIR/sample_theme.tar.gz"
mkdir -p "$TEST_DIR/sample_src/cursors"
cp /usr/share/icons/Adwaita/cursors/left_ptr "$TEST_DIR/sample_src/cursors/left_ptr"
printf "[Icon Theme]\nName=CliImported\n" > "$TEST_DIR/sample_src/index.theme"
tar -czf "$STAGE_ARCHIVE" -C "$TEST_DIR/sample_src" .

IMPORT_RES=$(PATH="$MOCK_BIN:/usr/bin:/bin" "$ROOT/scripts/cursorctl" import --source "$STAGE_ARCHIVE")
IMPORTED_ID=$(python3 -c 'import sys, json; data = json.loads(sys.argv[1]); assert data.get("ok"); print(data["theme"]["id"])' "$IMPORT_RES")
[[ -d "$XDG_DATA_HOME/icons/$IMPORTED_ID" ]]
[[ -f "$XDG_DATA_HOME/icons/$IMPORTED_ID/.omarchy-cursor-switcher-imported" ]]

REMOVE_RES=$(PATH="$MOCK_BIN:/usr/bin:/bin" "$ROOT/scripts/cursorctl" remove-imported --id "$IMPORTED_ID")
python3 -c 'import sys, json; data = json.loads(sys.argv[1]); assert data.get("ok")' "$REMOVE_RES"
[[ ! -e "$XDG_DATA_HOME/icons/$IMPORTED_ID" ]]

# Test Desktop Integration: register-app / unregister-app
"$ROOT/scripts/cursorctl" register-app --source "$ROOT"
[[ -x "$HOME/.local/bin/omarchy-cursor-switcher" ]]
[[ -f "$XDG_DATA_HOME/applications/omarchy-cursor-switcher.desktop" ]]
[[ -f "$XDG_DATA_HOME/icons/hicolor/scalable/apps/omarchy-cursor-switcher.svg" ]]

# Validate desktop file syntax if desktop-file-validate is present
if command -v desktop-file-validate >/dev/null 2>&1; then
  desktop-file-validate "$XDG_DATA_HOME/applications/omarchy-cursor-switcher.desktop"
fi

"$ROOT/scripts/cursorctl" unregister-app
[[ ! -e "$HOME/.local/bin/omarchy-cursor-switcher" ]]
[[ ! -e "$XDG_DATA_HOME/applications/omarchy-cursor-switcher.desktop" ]]
[[ ! -e "$XDG_DATA_HOME/icons/hicolor/scalable/apps/omarchy-cursor-switcher.svg" ]]

# Test cleanup helper installation
"$ROOT/scripts/cursorctl" install-cleanup-helper --source "$ROOT"
CLEANUP_HELPER="$XDG_DATA_HOME/omarchy-cursor-switcher/omarchy-cursor-switcher-cleanup"
[[ -x "$CLEANUP_HELPER" ]]

# Test Snapshotting of pre-existing state
rm -f "$TEST_DIR/config/uwsm/env.d/90-omarchy-cursor-switcher" "$TEST_DIR/config/uwsm/env-hyprland.d/90-omarchy-cursor-switcher"
mkdir -p "$TEST_DIR/config/uwsm/env.d"
printf '%s\n' '# pre-existing user fragment' "export XCURSOR_THEME='MyPriorTheme'" > "$TEST_DIR/config/uwsm/env.d/90-omarchy-cursor-switcher"

MOCK_CALLS="$TEST_DIR/mock_calls.log"

cat <<EOF > "$MOCK_BIN/gsettings"
#!/bin/sh
echo "gsettings \$*" >> "$MOCK_CALLS"
if [ "\$1" = "get" ] && [ "\$3" = "cursor-theme" ]; then echo "'MyPriorTheme'"; exit 0; fi
if [ "\$1" = "get" ] && [ "\$3" = "cursor-size" ]; then echo "32"; exit 0; fi
exit 0
EOF
chmod +x "$MOCK_BIN/gsettings"

cat <<EOF > "$MOCK_BIN/systemctl"
#!/bin/sh
echo "systemctl \$*" >> "$MOCK_CALLS"
if [ "\$1" = "--user" ] && [ "\$2" = "show-environment" ]; then
  echo "XCURSOR_THEME=MyPriorTheme"
  echo "XCURSOR_SIZE=32"
  exit 0
fi
exit 0
EOF
chmod +x "$MOCK_BIN/systemctl"

cat <<EOF > "$MOCK_BIN/hyprctl"
#!/bin/sh
echo "hyprctl \$*" >> "$MOCK_CALLS"
exit 0
EOF
chmod +x "$MOCK_BIN/hyprctl"

PATH="$MOCK_BIN:/usr/bin:/bin" XDG_CONFIG_HOME="$TEST_DIR/config" \
  "$ROOT/scripts/cursorctl" snapshot-original-state

SNAPSHOT_FILE="${XDG_STATE_HOME:-$HOME/.local/state}/cursor-theme-manager/snapshot.json"
[[ -f "$SNAPSHOT_FILE" ]]

python3 - "$SNAPSHOT_FILE" <<'PY_INNER'
import json, sys
snap = json.load(open(sys.argv[1]))
assert snap["version"] == 2
assert snap["gtkTheme"]["present"] == True and snap["gtkTheme"]["value"] == "MyPriorTheme"
assert snap["gtkSize"]["present"] == True and snap["gtkSize"]["value"] == 32
env = snap["systemdEnvironment"]
assert env["XCURSOR_THEME"] == {"present": True, "value": "MyPriorTheme"}
assert env["XCURSOR_SIZE"] == {"present": True, "value": "32"}
assert env["HYPRCURSOR_THEME"]["present"] == False
assert snap["uwsmEnvCommon"]["present"] == True
assert "pre-existing user fragment" in snap["uwsmEnvCommon"]["content"]
assert snap["uwsmEnvHyprland"]["present"] == False
PY_INNER

# Verify snapshot is NOT overwritten on subsequent runs
touch -t 202001010000 "$SNAPSHOT_FILE"
ORIG_MTIME=$(stat -c %Y "$SNAPSHOT_FILE")
PATH="$MOCK_BIN:/usr/bin:/bin" XDG_CONFIG_HOME="$TEST_DIR/config" \
  "$ROOT/scripts/cursorctl" snapshot-original-state
[[ $(stat -c %Y "$SNAPSHOT_FILE") == "$ORIG_MTIME" ]]

# Apply Both and register app
PATH="$MOCK_BIN:/usr/bin:/bin" XDG_CONFIG_HOME="$TEST_DIR/config" \
  "$ROOT/scripts/cursorctl" apply --hyprcursor Both-Hypr --xcursor Both --size 96 --commit
"$ROOT/scripts/cursorctl" register-app --source "$ROOT"
mkdir -p "$TEST_DIR/config/omarchy"
echo '{"version": 1}' > "$TEST_DIR/config/omarchy/cursor-switcher.json"

# Check audit-installation before deactivate
AUDIT_JSON=$(PATH="$MOCK_BIN:/usr/bin:/bin" XDG_CONFIG_HOME="$TEST_DIR/config" XDG_DATA_HOME="$XDG_DATA_HOME" "$ROOT/scripts/cursorctl" audit-installation)
python3 -c 'import sys, json; rep = json.loads(sys.argv[1]); assert rep["is_clean"] == False; assert rep["desktop_entry"] == True; assert rep["snapshot"] == True' "$AUDIT_JSON"

# Test deactivate: restores pre-plugin state & removes desktop entry, but keeps state & snapshot
PATH="$MOCK_BIN:/usr/bin:/bin" XDG_CONFIG_HOME="$TEST_DIR/config" \
  "$ROOT/scripts/cursorctl" deactivate

[[ ! -e "$HOME/.local/bin/omarchy-cursor-switcher" ]]
[[ ! -e "$XDG_DATA_HOME/applications/omarchy-cursor-switcher.desktop" ]]
[[ ! -e "$XDG_DATA_HOME/icons/hicolor/scalable/apps/omarchy-cursor-switcher.svg" ]]
grep -q '^# pre-existing user fragment$' "$TEST_DIR/config/uwsm/env.d/90-omarchy-cursor-switcher"
[[ ! -e "$TEST_DIR/config/uwsm/env-hyprland.d/90-omarchy-cursor-switcher" ]]
[[ -f "$SNAPSHOT_FILE" ]]

# Verify gsettings restored MyPriorTheme / 32
grep -q "gsettings set org.gnome.desktop.interface cursor-theme MyPriorTheme" "$MOCK_CALLS"
grep -q "gsettings set org.gnome.desktop.interface cursor-size 32" "$MOCK_CALLS"

# Verify systemctl unset HYPRCURSOR_THEME (since it was absent)
grep -q "systemctl --user unset-environment HYPRCURSOR_THEME" "$MOCK_CALLS"

# Test purge: removes all plugin-owned themes, caches, state, and snapshot
# Setup plugin-owned theme vs foreign unowned theme
mkdir -p "$XDG_DATA_HOME/icons/OwnedTheme" "$XDG_DATA_HOME/icons/UnownedTheme"
echo "1.0" > "$XDG_DATA_HOME/icons/OwnedTheme/.omarchy-cursor-switcher-theme"
mkdir -p "$TEST_DIR/home/.cache/omarchy-cursor-switcher"

PATH="$MOCK_BIN:/usr/bin:/bin" XDG_CONFIG_HOME="$TEST_DIR/config" XDG_CACHE_HOME="$TEST_DIR/home/.cache" \
  "$ROOT/scripts/cursorctl" purge

[[ ! -e "$XDG_DATA_HOME/icons/OwnedTheme" ]]
[[ -d "$XDG_DATA_HOME/icons/UnownedTheme" ]]
[[ ! -e "$TEST_DIR/config/omarchy/cursor-switcher.json" ]]
[[ ! -e "$SNAPSHOT_FILE" ]]
[[ ! -e "$TEST_DIR/home/.cache/omarchy-cursor-switcher" ]]
[[ ! -e "$XDG_DATA_HOME/omarchy-cursor-switcher" ]]

# Test double purge (idempotency)
PATH="$MOCK_BIN:/usr/bin:/bin" XDG_CONFIG_HOME="$TEST_DIR/config" XDG_CACHE_HOME="$TEST_DIR/home/.cache" \
  "$ROOT/scripts/cursorctl" purge

# Test audit-installation after purge: must be clean
AUDIT_JSON_CLEAN=$(PATH="$MOCK_BIN:/usr/bin:/bin" XDG_CONFIG_HOME="$TEST_DIR/config" XDG_DATA_HOME="$XDG_DATA_HOME" XDG_CACHE_HOME="$TEST_DIR/home/.cache" "$ROOT/scripts/omarchy-cursor-switcher-cleanup" audit-installation)
python3 -c 'import sys, json; rep = json.loads(sys.argv[1]); assert rep["is_clean"] == True, rep' "$AUDIT_JSON_CLEAN"

echo "cursorctl tests: ok"
