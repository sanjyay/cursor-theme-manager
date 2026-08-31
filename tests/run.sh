#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd)
cd "$ROOT"
node tests/model.test.js
python3 tests/preview_roles.test.py
python3 tests/import_security.test.py
python3 tests/file_browser.test.py
tests/cursorctl.test.sh
tests/removal_lifecycle.test.sh
python3 tests/third_party_registry.test.py
python3 tests/assets.test.py
qmllint -I /usr/share/omarchy/shell Panel.qml CursorService.qml components/*.qml
qmllint tests/manual-cursor-roles.qml
probe_dir=$(mktemp -d)
trap 'rm -rf -- "$probe_dir"' EXIT
c++ -std=c++20 -Wall -Wextra -Werror tests/hyprcursor-probe.cpp -o "$probe_dir/hyprcursor-probe" $(pkg-config --cflags --libs hyprcursor)
mkdir -p "$probe_dir/home/.local/share/icons"
ln -s "$ROOT/themes/banana/generated/Banana" "$probe_dir/home/.local/share/icons/Banana"
HOME="$probe_dir/home" XDG_DATA_HOME="$probe_dir/home/.local/share" "$probe_dir/hyprcursor-probe" Banana
echo "all tests: ok"
