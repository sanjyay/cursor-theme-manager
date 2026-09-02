#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TEST_DIR"
}
trap cleanup EXIT

export HOME="$TEST_DIR/home"
export XDG_CONFIG_HOME="$TEST_DIR/config"
export XDG_DATA_HOME="$TEST_DIR/data"
export XDG_CACHE_HOME="$TEST_DIR/cache"
export XDG_STATE_HOME="$TEST_DIR/state"
export XDG_DATA_DIRS="$TEST_DIR/usr/share"
export XDG_RUNTIME_DIR="$TEST_DIR/run"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$TEST_DIR/run/no-session-bus"
export HYPRLAND_INSTANCE_SIGNATURE=""
export WAYLAND_DISPLAY=""

mkdir -p "$HOME" "$XDG_CONFIG_HOME/omarchy/plugins/sanjyay.cursor-theme-manager" "$XDG_DATA_HOME/icons" "$XDG_CACHE_HOME" "$XDG_STATE_HOME" "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

MOCK_BIN="$TEST_DIR/mock_bin"
mkdir -p "$MOCK_BIN"

cat <<'EOF_MOCK' > "$MOCK_BIN/gsettings"
#!/bin/sh
exit 0
EOF_MOCK
chmod +x "$MOCK_BIN/gsettings"

cat <<'EOF_MOCK' > "$MOCK_BIN/systemctl"
#!/bin/sh
exit 0
EOF_MOCK
chmod +x "$MOCK_BIN/systemctl"

cat <<'EOF_MOCK' > "$MOCK_BIN/dbus-update-activation-environment"
#!/bin/sh
exit 0
EOF_MOCK
chmod +x "$MOCK_BIN/dbus-update-activation-environment"

cat <<'EOF_MOCK' > "$MOCK_BIN/hyprctl"
#!/bin/sh
exit 0
EOF_MOCK
chmod +x "$MOCK_BIN/hyprctl"

# Create mock themes
mkdir -p "$XDG_DATA_HOME/icons/MockHypr/hyprcursors"
cat <<'EOF_HYPR' > "$XDG_DATA_HOME/icons/MockHypr/manifest.hl"
name = MockHypr
description = A test hyprcursor theme
version = 1.0.0
EOF_HYPR

mkdir -p "$XDG_DATA_HOME/icons/MockXCursor/cursors"
touch "$XDG_DATA_HOME/icons/MockXCursor/cursors/default"
cat <<'EOF_XCUR' > "$XDG_DATA_HOME/icons/MockXCursor/index.theme"
[Icon Theme]
Name=MockXCursor
Comment=A test xcursor theme
EOF_XCUR

# Test discover
DISC_RES=$(PATH="$MOCK_BIN:$PATH" "$ROOT/scripts/cursorctl" discover)
python3 -c 'import sys, json; data = json.loads(sys.argv[1]); assert len(data.get("themes", [])) >= 2' "$DISC_RES"

# Test state-read and state-write
WRITE_RES=$("$ROOT/scripts/cursorctl" state-write --state '{"version": 2, "theme": {"displayName": "MockHypr", "hyprcursor": "MockHypr"}, "size": 32}')
python3 -c 'import sys, json; data = json.loads(sys.argv[1]); assert data.get("ok")' "$WRITE_RES"

READ_RES=$("$ROOT/scripts/cursorctl" state-read)
python3 -c 'import sys, json; data = json.loads(sys.argv[1]); assert data["theme"]["displayName"] == "MockHypr"; assert data["size"] == 32' "$READ_RES"

# Test durable baseline plus persistent theme state. Live setcursor ordering is
# exercised hermetically in first_mutation_barrier.test.py because production
# correctly rejects PATH-injected executables.
PATH="$MOCK_BIN:$PATH" "$ROOT/scripts/cursorctl" capture-baseline >/dev/null
PATH="$MOCK_BIN:$PATH" "$ROOT/scripts/cursorctl" persist-theme \
  --theme '{"id":"MockHypr","displayName":"MockHypr","hyprcursor":"MockHypr","xcursor":"-"}' \
  --size 32 >/dev/null
[[ -f "$TEST_DIR/config/uwsm/env.d/90-omarchy-cursor-switcher" ]]
[[ -f "$TEST_DIR/config/uwsm/env-hyprland.d/90-omarchy-cursor-switcher" ]]
grep -q "export HYPRCURSOR_THEME='MockHypr'" "$TEST_DIR/config/uwsm/env-hyprland.d/90-omarchy-cursor-switcher"
grep -q "export HYPRCURSOR_SIZE='32'" "$TEST_DIR/config/uwsm/env-hyprland.d/90-omarchy-cursor-switcher"

# Test CLI theme import and removal
STAGE_ARCHIVE="$TEST_DIR/sample_theme.tar.gz"
mkdir -p "$TEST_DIR/sample_src/cursors"
cp /usr/share/icons/Adwaita/cursors/left_ptr "$TEST_DIR/sample_src/cursors/left_ptr"
printf "[Icon Theme]\nName=CliImported\n" > "$TEST_DIR/sample_src/index.theme"
tar -czf "$STAGE_ARCHIVE" -C "$TEST_DIR/sample_src" .

IMPORT_RES=$(PATH="$MOCK_BIN:$PATH" "$ROOT/scripts/cursorctl" import --source "$STAGE_ARCHIVE")
IMPORTED_ID=$(python3 -c 'import sys, json; data = json.loads(sys.argv[1]); assert data.get("ok"); print(data["theme"]["id"])' "$IMPORT_RES")
[[ -d "$XDG_DATA_HOME/icons/$IMPORTED_ID" ]]
[[ -f "$XDG_DATA_HOME/icons/$IMPORTED_ID/.omarchy-cursor-switcher-imported" ]]

REMOVE_RES=$(PATH="$MOCK_BIN:$PATH" "$ROOT/scripts/cursorctl" remove-imported --id "$IMPORTED_ID")
python3 -c 'import sys, json; data = json.loads(sys.argv[1]); assert data.get("ok")' "$REMOVE_RES"
[[ ! -e "$XDG_DATA_HOME/icons/$IMPORTED_ID" ]]

# Test Integration Lifecycle
# 1. Status initially disabled, prompt not seen
STATUS_0=$(PATH="$MOCK_BIN:$PATH" "$ROOT/scripts/cursorctl" integration-status)
python3 -c 'import sys, json; data = json.loads(sys.argv[1]); assert data["enabled"] == False; assert data["promptSeen"] == False' "$STATUS_0"

# 2. Dismiss prompt (in-memory/session only, zero durable state)
DISMISS_RES=$(PATH="$MOCK_BIN:$PATH" "$ROOT/scripts/cursorctl" integration-dismiss-prompt)
python3 -c 'import sys, json; data = json.loads(sys.argv[1]); assert data["ok"] == True' "$DISMISS_RES"
[[ ! -e "$XDG_DATA_HOME/applications/cursor-theme-manager.desktop" ]]
[[ ! -e "$HOME/.local/libexec/cursor-theme-manager/cleanup" ]]

STATUS_1=$(PATH="$MOCK_BIN:$PATH" "$ROOT/scripts/cursorctl" integration-status)
python3 -c 'import sys, json; data = json.loads(sys.argv[1]); assert data["enabled"] == False; assert data["promptSeen"] == False' "$STATUS_1"

echo "cursorctl tests: ok"
