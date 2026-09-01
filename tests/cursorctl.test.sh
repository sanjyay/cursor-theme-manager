#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd)
TEST_DIR=$(mktemp -d)
export TEST_DIR
trap 'rm -rf -- "$TEST_DIR"' EXIT
export HOME="$TEST_DIR/home"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_CACHE_HOME="$HOME/.cache"
export XDG_DATA_DIRS="$TEST_DIR/system/share"
mkdir -p "$XDG_DATA_HOME/icons/XOnly/cursors" "$XDG_DATA_HOME/icons/Both/cursors" \
  "$XDG_DATA_HOME/icons/Both/hyprcursors" "$XDG_DATA_HOME/icons/IconsOnly/32x32/apps" \
  "$XDG_DATA_DIRS/icons/SystemHypr/hyprcursors"
cp /usr/share/icons/Adwaita/cursors/left_ptr "$XDG_DATA_HOME/icons/XOnly/cursors/left_ptr"
cp /usr/share/icons/Adwaita/cursors/default "$XDG_DATA_HOME/icons/Both/cursors/default"
printf '[Icon Theme]\nName=Friendly Both\n' > "$XDG_DATA_HOME/icons/Both/index.theme"
printf 'name = Both-Hypr\ncursors_directory = hyprcursors\n' > "$XDG_DATA_HOME/icons/Both/manifest.hl"
printf 'name = System-Hypr\ncursors_directory = hyprcursors\n' > "$XDG_DATA_DIRS/icons/SystemHypr/manifest.hl"

"$ROOT/scripts/cursorctl" discover > "$TEST_DIR/discovery.json"
python3 - "$TEST_DIR/discovery.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
themes = {entry["path"].rsplit("/", 1)[-1]: entry for entry in data["themes"]}
assert set(themes) == {"XOnly", "Both", "SystemHypr"}, themes
assert themes["XOnly"]["formats"] == ["xcursor"]
assert themes["Both"]["formats"] == ["hyprcursor", "xcursor"]
assert themes["Both"]["hyprcursor"] == "Both-Hypr"
assert themes["Both"]["xcursor"] == "Both"
assert themes["Both"]["displayName"] == "Friendly Both"
assert themes["SystemHypr"]["formats"] == ["hyprcursor"]
PY



if "$ROOT/scripts/cursorctl" apply --hyprcursor 'bad;name' --xcursor - --size 24 --preview 2>/dev/null; then
  echo "unsafe theme name accepted" >&2
  exit 1
fi
if "$ROOT/scripts/cursorctl" apply --hyprcursor Safe --xcursor - --size 99 --preview 2>/dev/null; then
  echo "unsupported size accepted" >&2
  exit 1
fi

MOCK_BIN="$TEST_DIR/mock-bin"
mkdir -p "$MOCK_BIN" "$TEST_DIR/config"
for command in hyprctl gsettings systemctl dbus-update-activation-environment; do
  printf '#!/bin/sh\nexit 0\n' > "$MOCK_BIN/$command"
  chmod +x "$MOCK_BIN/$command"
done
PATH="$MOCK_BIN:/usr/bin:/bin" XDG_CONFIG_HOME="$TEST_DIR/config" \
  "$ROOT/scripts/cursorctl" apply --hyprcursor Both-Hypr --xcursor Both --size 256 --commit
grep -qx "export XCURSOR_THEME='Both'" "$TEST_DIR/config/uwsm/env.d/90-omarchy-cursor-switcher"
grep -qx "export XCURSOR_SIZE='256'" "$TEST_DIR/config/uwsm/env.d/90-omarchy-cursor-switcher"
grep -qx "export HYPRCURSOR_THEME='Both-Hypr'" "$TEST_DIR/config/uwsm/env-hyprland.d/90-omarchy-cursor-switcher"
grep -qx "export HYPRCURSOR_SIZE='256'" "$TEST_DIR/config/uwsm/env-hyprland.d/90-omarchy-cursor-switcher"

# Test XCursor-only theme live application via conversion
PATH="$MOCK_BIN:/usr/bin:/bin" XDG_CONFIG_HOME="$TEST_DIR/config" \
  "$ROOT/scripts/cursorctl" apply --hyprcursor - --xcursor XOnly --theme-path "$XDG_DATA_HOME/icons/XOnly" --size 24 --commit
grep -qx "export XCURSOR_THEME='XOnly'" "$TEST_DIR/config/uwsm/env.d/90-omarchy-cursor-switcher"
grep -q "export HYPRCURSOR_THEME='CursorSwitcher-XCursor-XOnly-" "$TEST_DIR/config/uwsm/env-hyprland.d/90-omarchy-cursor-switcher"

# Test cursorctl import & remove-imported CLI commands
IMPORT_TEST_SRC="$TEST_DIR/cli_import_src"
mkdir -p "$IMPORT_TEST_SRC/cursors"
cp /usr/share/icons/Adwaita/cursors/left_ptr "$IMPORT_TEST_SRC/cursors/left_ptr"
cp /usr/share/icons/Adwaita/cursors/default "$IMPORT_TEST_SRC/cursors/default"
printf '[Icon Theme]\nName=CliImported\n' > "$IMPORT_TEST_SRC/index.theme"
printf 'MIT License\n' > "$IMPORT_TEST_SRC/LICENSE"




IMPORT_RES=$(PATH="$MOCK_BIN:/usr/bin:/bin" "$ROOT/scripts/cursorctl" import --source "$IMPORT_TEST_SRC")
IMPORTED_ID=$(python3 -c 'import sys, json; data = json.loads(sys.argv[1]); assert data.get("ok"); print(data["theme"]["id"])' "$IMPORT_RES")
[[ -d "$XDG_DATA_HOME/icons/$IMPORTED_ID" ]]
[[ -f "$XDG_DATA_HOME/icons/$IMPORTED_ID/.omarchy-cursor-switcher-imported" ]]


# Test remove-imported CLI command
REMOVE_RES=$(PATH="$MOCK_BIN:/usr/bin:/bin" "$ROOT/scripts/cursorctl" remove-imported --id "$IMPORTED_ID")
python3 -c 'import sys, json; data = json.loads(sys.argv[1]); assert data.get("ok")' "$REMOVE_RES"
[[ ! -e "$XDG_DATA_HOME/icons/$IMPORTED_ID" ]]

# App registration & unregistration tests
"$ROOT/scripts/cursorctl" register-app --source "$ROOT"
[[ -x "$HOME/.local/bin/omarchy-cursor-switcher" ]]
[[ -f "$XDG_DATA_HOME/applications/omarchy-cursor-switcher.desktop" ]]
[[ -f "$XDG_DATA_HOME/icons/hicolor/scalable/apps/omarchy-cursor-switcher.svg" ]]

# Idempotency check
"$ROOT/scripts/cursorctl" register-app --source "$ROOT"
[[ -x "$HOME/.local/bin/omarchy-cursor-switcher" ]]
[[ -f "$XDG_DATA_HOME/applications/omarchy-cursor-switcher.desktop" ]]
[[ -f "$XDG_DATA_HOME/icons/hicolor/scalable/apps/omarchy-cursor-switcher.svg" ]]

if command -v desktop-file-validate >/dev/null 2>&1; then
  desktop-file-validate "$XDG_DATA_HOME/applications/omarchy-cursor-switcher.desktop"
fi

"$ROOT/scripts/cursorctl" unregister-app
[[ ! -e "$HOME/.local/bin/omarchy-cursor-switcher" ]]
[[ ! -e "$XDG_DATA_HOME/applications/omarchy-cursor-switcher.desktop" ]]
[[ ! -e "$XDG_DATA_HOME/icons/hicolor/scalable/apps/omarchy-cursor-switcher.svg" ]]

# Test install-cleanup-helper
"$ROOT/scripts/cursorctl" install-cleanup-helper --source "$ROOT"
CLEANUP_HELPER="$XDG_DATA_HOME/omarchy-cursor-switcher/omarchy-cursor-switcher-cleanup"
[[ -x "$CLEANUP_HELPER" ]]

# Test snapshot-original-state
# Earlier apply tests intentionally created plugin fragments; a first activation
# starts without those files.
rm -f "$TEST_DIR/config/uwsm/env.d/90-omarchy-cursor-switcher" \
  "$TEST_DIR/config/uwsm/env-hyprland.d/90-omarchy-cursor-switcher"
mkdir -p "$TEST_DIR/config/uwsm/env.d"
printf '%s\n' '# pre-existing user fragment' "export XCURSOR_THEME='MyPriorTheme'" \
  > "$TEST_DIR/config/uwsm/env.d/90-omarchy-cursor-switcher"
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

SNAPSHOT_FILE="$TEST_DIR/config/omarchy/cursor-switcher-original-state.json"
[[ -f "$SNAPSHOT_FILE" ]]

python3 - "$SNAPSHOT_FILE" <<'PY'
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
PY

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
[[ -f "$TEST_DIR/config/omarchy/cursor-switcher.json" ]]
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
