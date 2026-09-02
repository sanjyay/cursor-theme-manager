#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd)
cd "$ROOT"

# 1. Snapshot real user directories before running tests
SNAP_DIR=$(mktemp -d /tmp/ctm-snap-XXXXXX)
GLOBAL_SANDBOX=$(mktemp -d /tmp/ctm-sandbox-XXXXXX)

cleanup_runner() {
  if declare -F restore_live_watcher_state >/dev/null; then
    restore_live_watcher_state
  fi
  rm -rf "$SNAP_DIR" "$GLOBAL_SANDBOX"
}
trap cleanup_runner EXIT

REAL_HOME="${HOME}"
CTM_LIVE_UNIT="cursor-theme-manager-cleanup.path"
CTM_LIVE_ENABLED=$(systemctl --user is-enabled "$CTM_LIVE_UNIT" 2>/dev/null || true)
CTM_LIVE_ACTIVE=$(systemctl --user is-active "$CTM_LIVE_UNIT" 2>/dev/null || true)

restore_live_watcher_state() {
  if [ "$CTM_LIVE_ENABLED" = "enabled" ]; then
    systemctl --user enable "$CTM_LIVE_UNIT" >/dev/null 2>&1 || true
  else
    systemctl --user disable "$CTM_LIVE_UNIT" >/dev/null 2>&1 || true
  fi
  if [ "$CTM_LIVE_ACTIVE" = "active" ]; then
    systemctl --user start "$CTM_LIVE_UNIT" >/dev/null 2>&1 || true
  else
    systemctl --user stop "$CTM_LIVE_UNIT" >/dev/null 2>&1 || true
  fi
}

snapshot_user_dirs() {
  local out_file="$1"
  : > "$out_file"
  local dirs=(
    "$REAL_HOME/.local/share/icons"
    "$REAL_HOME/.icons"
    "$REAL_HOME/.local/state/cursor-theme-manager"
    "$REAL_HOME/.local/share/applications"
    "$REAL_HOME/.local/libexec/cursor-theme-manager"
    "$REAL_HOME/.config/systemd/user"
  )
  for d in "${dirs[@]}"; do
    if [ -d "$d" ]; then
      find "$d" -maxdepth 2 -printf '%P %y %s\n' 2>/dev/null | sort >> "$out_file"
    fi
  done
}

snapshot_user_dirs "$SNAP_DIR/before.txt"

# 2. Establish global fallback sandbox environment
export HOME="$GLOBAL_SANDBOX/home"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_STATE_HOME="$HOME/.local/state"
export XDG_CONFIG_HOME="$GLOBAL_SANDBOX/config"
export XDG_CACHE_HOME="$GLOBAL_SANDBOX/cache"
export XDG_DATA_DIRS="$GLOBAL_SANDBOX/usr/share:/usr/local/share:/usr/share"

mkdir -p "$HOME" "$XDG_DATA_HOME/icons" "$XDG_STATE_HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_DIRS/icons"

echo "=== 1. Node Model Tests ==="
node tests/model.test.js

echo "=== 2. Preview Roles Tests ==="
python3 tests/preview_roles.test.py

echo "=== 3. Import Security Tests ==="
python3 tests/import_security.test.py

echo "=== 4. File Browser Tests ==="
python3 tests/file_browser.test.py

echo "=== 5. Network Security Static Analysis ==="
python3 tests/network_security.test.py

echo "=== 6. Local Discovery & Ownership Tests ==="
python3 tests/local_discovery.test.py

echo "=== 7. Cursorctl Shell Tests ==="
tests/cursorctl.test.sh

echo "=== 8. Live Restore Regression Tests ==="
python3 tests/live_restore.test.py

echo "=== 9. Adversarial Security Tests ==="
python3 "$ROOT/tests/security_adversarial.test.py"

echo "=== 10. First-Mutation Barrier / Actual QML Route Tests ==="
python3 "$ROOT/tests/first_mutation_barrier.test.py"

echo "=== 10b. Startup Lifecycle / Immediate-Reinstall Race Tests ==="
python3 "$ROOT/tests/startup_lifecycle_race.test.py"

echo "=== 10c. Persistent Lifecycle / Interruption Stress Tests ==="
python3 "$ROOT/tests/persistent_lifecycle.test.py"

echo "=== 11. Test Hygiene & Real Directory Isolation Assertions ==="
python3 tests/test_hygiene.test.py

echo "=== 12. Size Coalescing & Fast-Path Tests ==="
python3 tests/size_coalescing.test.py

echo "=== 13. QML Lint Validation ==="
qmllint -I /usr/share/omarchy/shell Panel.qml CursorService.qml components/*.qml
qmllint tests/manual-cursor-roles.qml

# Strict production executable resolution means subprocess lifecycle tests can
# reach the real user systemd manager even under an isolated HOME. Restore the
# watcher's exact pre-test state before evaluating filesystem isolation.
restore_live_watcher_state

# 3. Post-run snapshot and pollution check
snapshot_user_dirs "$SNAP_DIR/after.txt"

if ! diff -u "$SNAP_DIR/before.txt" "$SNAP_DIR/after.txt" > "$SNAP_DIR/diff.txt"; then
  echo "CRITICAL ERROR: Real user directory pollution detected after running test suite!" >&2
  cat "$SNAP_DIR/diff.txt" >&2
  exit 1
fi

echo "All tests passed with zero real-user directory pollution."
