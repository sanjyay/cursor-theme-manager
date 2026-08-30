#!/usr/bin/env python3
import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "themes" / "omarchy-banana"
spec = json.loads((THEME / "theme.json").read_text(encoding="utf-8"))
assert spec["internalName"] == "Omarchy-Banana"
assert spec["displayName"] == "Omarchy Banana"
assert len(spec["roles"]) >= 30

default = spec["roles"]["default"]
pointer = spec["roles"]["pointer"]
assert default["source"] == "default.svg"
assert default["hotspot"] == [7, 6]
assert {"left_ptr", "arrow", "top_left_arrow"} <= set(default["aliases"])
assert pointer["source"] == "pointer.svg"
assert pointer["hotspot"] == [32, 5]
assert {"pointer", "link", "hand", "hand1", "hand2", "pointing_hand"} <= ({"pointer"} | set(pointer["aliases"]))
assert default["source"] != pointer["source"]

sources = {entry["source"] for entry in spec["roles"].values()}
assert sources == {path.name for path in (THEME / "source").glob("*.svg")}
for filename in sorted(sources):
    path = THEME / "source" / filename
    root = ET.parse(path).getroot()
    assert root.tag.endswith("svg")
    assert root.attrib.get("viewBox") == "0 0 64 64"
    raw = path.read_text(encoding="utf-8").lower()
    assert "<image" not in raw
    assert "http://" not in raw.replace("http://www.w3.org/2000/svg", "")
    assert "https://" not in raw

generated = THEME / "generated" / "Omarchy-Banana"
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
        assert alias_path.is_symlink(), alias_path
        assert alias_path.readlink() == Path(role)

def decode(role, expected_hotspot):
    with tempfile.TemporaryDirectory() as temp:
        result = subprocess.run(["xcur2png", "-n", str(generated / "cursors" / role)],
                                cwd=temp, text=True, capture_output=True)
        assert result.returncode == 0, (role, result.stderr)
        assert f"24\t{expected_hotspot[0]}\t{expected_hotspot[1]}" in result.stdout, (role, result.stdout)


for role in ("default", "left_ptr", "arrow", "top_left_arrow"):
    decode(role, (3, 2))
for role in ("pointer", "link", "hand", "hand1", "hand2", "pointing_hand",
             "9d800788f1b08800ae810202380a0822", "e29285e634086352946a0e7090d73106"):
    decode(role, (12, 2))

for role in ("default", "pointer"):
    for size in spec["sizes"]:
        image = THEME / ".build" / f"{role}-{size}.png"
        assert image.is_file(), image
        dimensions = subprocess.check_output(
            ["identify", "-format", "%w %h", str(image)], text=True).split()
        assert dimensions == [str(size), str(size)], (image, dimensions)

print("asset tests: ok")
