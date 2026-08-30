#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd)
cd "$ROOT"
node tests/model.test.js
tests/cursorctl.test.sh
python3 tests/assets.test.py
qmllint -I /usr/share/omarchy/shell Panel.qml CursorService.qml components/*.qml
qmllint tests/manual-cursor-roles.qml
probe_dir=$(mktemp -d)
trap 'rm -rf -- "$probe_dir"' EXIT
c++ -std=c++20 -Wall -Wextra -Werror tests/hyprcursor-probe.cpp -o "$probe_dir/hyprcursor-probe" $(pkg-config --cflags --libs hyprcursor)
mkdir -p "$probe_dir/home/.local/share/icons"
ln -s "$ROOT/themes/omarchy-banana/generated/Omarchy-Banana" "$probe_dir/home/.local/share/icons/Omarchy-Banana"
HOME="$probe_dir/home" XDG_DATA_HOME="$probe_dir/home/.local/share" "$probe_dir/hyprcursor-probe" Omarchy-Banana
echo "all tests: ok"
