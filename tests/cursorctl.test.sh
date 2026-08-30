#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd)
TEST_DIR=$(mktemp -d)
trap 'rm -rf -- "$TEST_DIR"' EXIT
export HOME="$TEST_DIR/home"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_DATA_DIRS="$TEST_DIR/system/share"
mkdir -p "$XDG_DATA_HOME/icons/XOnly/cursors" "$XDG_DATA_HOME/icons/Both/cursors" \
  "$XDG_DATA_HOME/icons/Both/hyprcursors" "$XDG_DATA_HOME/icons/IconsOnly/32x32/apps" \
  "$XDG_DATA_DIRS/icons/SystemHypr/hyprcursors"
cp "$ROOT/themes/banana/generated/Banana/cursors/left_ptr" "$XDG_DATA_HOME/icons/XOnly/cursors/left_ptr"
cp "$ROOT/themes/banana/generated/Banana/cursors/default" "$XDG_DATA_HOME/icons/Both/cursors/default"
printf '[Icon Theme]\nName=Friendly Both\n' > "$XDG_DATA_HOME/icons/Both/index.theme"
printf 'name = Both-Hypr\ncursors_directory = hyprcursors\n' > "$XDG_DATA_HOME/icons/Both/manifest.hl"
printf 'name = System-Hypr\ncursors_directory = hyprcursors\n' > "$XDG_DATA_DIRS/icons/SystemHypr/manifest.hl"

"$ROOT/scripts/cursorctl" discover "$ROOT/themes/banana/upstream/svg/left_ptr.svg" > "$TEST_DIR/discovery.json"
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

INSTALL_PARENT="$TEST_DIR/install"
"$ROOT/scripts/cursorctl" install-bundled --source "$ROOT/themes/banana/generated/Banana" \
  --target "$INSTALL_PARENT/Banana" --version 2.0.0
"$ROOT/scripts/cursorctl" install-bundled --source "$ROOT/themes/banana/generated/Banana" \
  --target "$INSTALL_PARENT/Banana" --version 2.0.0
[[ $(<"$INSTALL_PARENT/Banana/.omarchy-cursor-switcher-theme") == 2.0.0 ]]
[[ -f "$INSTALL_PARENT/Banana/cursors/default" ]]
[[ -f "$INSTALL_PARENT/Banana/manifest.hl" ]]

mkdir -p "$TEST_DIR/collision/Banana"
if "$ROOT/scripts/cursorctl" install-bundled --source "$ROOT/themes/banana/generated/Banana" \
  --target "$TEST_DIR/collision/Banana" --version 2.0.0 2>/dev/null; then
  echo "collision protection failed" >&2
  exit 1
fi

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

echo "cursorctl tests: ok"
