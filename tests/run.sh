#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd)
cd "$ROOT"

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

echo "=== 8. Removal Lifecycle Shell Tests ==="
tests/removal_lifecycle.test.sh

echo "=== 9. QML Lint Validation ==="
qmllint -I /usr/share/omarchy/shell Panel.qml CursorService.qml components/*.qml
qmllint tests/manual-cursor-roles.qml

echo "all tests: ok"
