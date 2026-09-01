#!/usr/bin/env python3
import json
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "themes" / "banana"
spec = json.loads((THEME / "theme.json").read_text(encoding="utf-8"))
assert spec["internalName"] == "Banana"
assert spec["displayName"] == "Banana"
assert len(spec["roles"]) >= 30

left_ptr = spec["roles"]["left_ptr"]
hand2 = spec["roles"]["hand2"]
assert left_ptr["source"] == "left_ptr.svg"
assert left_ptr["hotspot"] == [52, 50]
assert {"arrow", "default", "top_left_arrow"} <= set(left_ptr["aliases"])
assert hand2["source"] == "hand2.svg"
assert hand2["hotspot"] == [39, 45]
assert {"pointer", "pointing_hand"} <= set(hand2["aliases"])
assert left_ptr["source"] != hand2["source"]

# Upstream licensing and attribution validation
assert (THEME / "upstream" / "LICENSE").is_file()
assert (THEME / "upstream" / "ATTRIBUTION.md").is_file()
attrib_content = (THEME / "upstream" / "ATTRIBUTION.md").read_text(encoding="utf-8")
assert "ful1e5" in attrib_content
assert "banana-cursor" in attrib_content
assert "GPL-3.0" in attrib_content

# Bundled archive and catalog integrity validation
bundled_archive = ROOT / "themes" / "bundled" / "banana.tar.xz"
catalog_file = ROOT / "themes" / "bundled" / "catalog.json"
assert bundled_archive.is_file(), f"Bundled archive missing: {bundled_archive}"
assert catalog_file.is_file(), f"Catalog missing: {catalog_file}"

import hashlib, sys
sys.path.insert(0, str(ROOT / "scripts"))
import importlib.util
spec_ci = importlib.util.spec_from_file_location("cursor_import", ROOT / "scripts" / "cursor-import.py")
ci = importlib.util.module_from_spec(spec_ci)
spec_ci.loader.exec_module(ci)

catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
banana_entry = next((e for e in catalog if e["id"] == "banana"), None)
assert banana_entry is not None, "banana entry in catalog.json required"
assert hashlib.sha256(bundled_archive.read_bytes()).hexdigest() == banana_entry["sha256"]

temp_extract_dir = tempfile.TemporaryDirectory()
ci.extract_archive_safely(str(bundled_archive), temp_extract_dir.name)
generated = Path(temp_extract_dir.name) / "Banana"

assert (generated / "manifest.hl").is_file()
assert (generated / "index.theme").is_file()
for role, entry in spec["roles"].items():
    cursor = generated / "cursors" / role
    shape = generated / "hyprcursors" / f"{role}.hlc"
    assert cursor.is_file(), cursor
    assert shape.is_file(), shape
    output = subprocess.check_output(["file", "-b", cursor], text=True)
    assert "Xcursor data" in output, (cursor, output)
    for alias in entry["aliases"]:
        alias_path = generated / "cursors" / alias
        assert alias_path.is_file(), alias_path
        assert alias_path.read_bytes() == cursor.read_bytes()

def decode(role, expected_hotspot, size=24):
    with tempfile.TemporaryDirectory() as temp:
        result = subprocess.run(["xcur2png", "-n", str(generated / "cursors" / role)],
                                cwd=temp, text=True, capture_output=True)
        assert result.returncode == 0, (role, result.stderr)
        assert f"{size}\t{expected_hotspot[0]}\t{expected_hotspot[1]}" in result.stdout, (role, size, result.stdout)



for role in ("left_ptr", "arrow", "default", "top_left_arrow"):
    decode(role, (3, 3), 16)
    decode(role, (5, 5), 24)
    decode(role, (10, 9), 48)
    decode(role, (20, 19), 96)
    decode(role, (26, 25), 128)
    decode(role, (39, 38), 192)
    decode(role, (52, 50), 256)

for role in ("hand2", "pointer", "pointing_hand",
             "9d800788f1b08800ae810202380a0822", "e29285e634086352946a0e7090d73106"):
    decode(role, (2, 3), 16)
    decode(role, (4, 4), 24)
    decode(role, (7, 8), 48)
    decode(role, (15, 17), 96)
    decode(role, (20, 22), 128)
    decode(role, (29, 34), 192)
    decode(role, (39, 45), 256)

# Validate app integration assets
app_icon = ROOT / "icons" / "omarchy-cursor-switcher.svg"
assert app_icon.is_file(), app_icon
icon_root = ET.parse(app_icon).getroot()
assert icon_root.tag.endswith("svg")

desktop_file = ROOT / "desktop" / "omarchy-cursor-switcher.desktop"
assert desktop_file.is_file(), desktop_file
desktop_content = desktop_file.read_text(encoding="utf-8")
assert "Name=Cursor Theme Manager" in desktop_content
assert "Exec=omarchy-cursor-switcher" in desktop_content
assert "Icon=omarchy-cursor-switcher" in desktop_content

launcher = ROOT / "scripts" / "omarchy-cursor-switcher"
assert launcher.is_file(), launcher
assert os.access(launcher, os.X_OK)

print("asset tests: ok")
