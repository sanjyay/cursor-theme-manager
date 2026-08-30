#!/usr/bin/env python3
import os
import sys
import json
import shutil
import subprocess
import zipfile
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
THEMES_DIR = ROOT_DIR / "themes"
THIRD_PARTY_DIR = ROOT_DIR / "third_party"
SCRATCH_AUDIT = Path("/tmp/cursor-audit")
SIZES = [16, 20, 24, 28, 32, 40, 48, 64, 80, 96, 128, 160, 192, 224, 256]

pack_bin = ROOT_DIR / "scripts" / "xcursor-pack"
if not pack_bin.exists():
    subprocess.run(["gcc", "-O2", "-s", str(ROOT_DIR / "scripts" / "xcursor-pack.c"), "-lXcursor", "-lpng", "-o", str(pack_bin)], check=True)

def render_svg_to_png(svg_path_or_content, size):
    """Renders SVG to PNG at exact size using rsvg-convert or magick"""
    if isinstance(svg_path_or_content, (str, Path)) and os.path.exists(str(svg_path_or_content)):
        res = subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), "-f", "png", str(svg_path_or_content)], capture_output=True)
        if res.returncode == 0:
            return res.stdout
        res = subprocess.run(["magick", "-background", "none", "-density", "288", str(svg_path_or_content), "-resize", f"{size}x{size}", "png:-"], capture_output=True)
        if res.returncode == 0:
            return res.stdout
        raise RuntimeError(f"Failed rendering {svg_path_or_content} at {size}px")
    else:
        content = svg_path_or_content if isinstance(svg_path_or_content, bytes) else svg_path_or_content.encode("utf-8")
        res = subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), "-f", "png"], input=content, capture_output=True)
        if res.returncode == 0:
            return res.stdout
        res = subprocess.run(["magick", "-background", "none", "-density", "288", "svg:-", "-resize", f"{size}x{size}", "png:-"], input=content, capture_output=True)
        if res.returncode == 0:
            return res.stdout
        raise RuntimeError(f"Failed rendering inline svg at {size}px")

def create_xcursor(frames_list, out_path):
    """
    frames_list: list of (size, xhot, yhot, png_bytes, delay_ms)
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        args = [str(pack_bin), str(out_path)]
        for i, (size, xhot, yhot, png_bytes, delay) in enumerate(frames_list):
            png_file = Path(tmp) / f"frame_{i}_{size}_{xhot}_{yhot}_{delay}.png"
            png_file.write_bytes(png_bytes)
            args.extend([str(size), str(xhot), str(yhot), str(delay), str(png_file)])
        subprocess.run(args, check=True)

def write_hlc(zip_path, meta_hl, images_dict):
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("meta.hl", meta_hl)
        for name, data in images_dict.items():
            if isinstance(data, str):
                data = data.encode("utf-8")
            zf.writestr(name, data)

# -------------------------------------------------------------
# 1. PHINGER BUILDER
# -------------------------------------------------------------
def build_phinger():
    print("Building Phinger...")
    src_dir = SCRATCH_AUDIT / "phinger"
    dest_dir = THEMES_DIR / "phinger"
    gen_dir = dest_dir / "generated" / "Phinger"
    if gen_dir.exists(): shutil.rmtree(gen_dir)
    (gen_dir / "hyprcursors").mkdir(parents=True, exist_ok=True)
    (gen_dir / "cursors").mkdir(parents=True, exist_ok=True)

    json_data = json.loads((src_dir / "theme" / "cursor-theme.json").read_text())
    dark_cursors = []
    for var in json_data["variants"]:
        if var["name"] == "dark":
            dark_cursors = var["cursors"]
            break

    # Hotspot map for phinger (derived from 24px SVG coordinates and element tips)
    hotspots = {
        "default": (1, 1),
        "pointer": (4, 1),
        "context-menu": (1, 1),
        "help": (1, 1),
        "progress": (1, 1),
        "wait": (12, 12),
        "cell": (12, 12),
        "crosshair": (12, 12),
        "text": (12, 12),
        "vertical-text": (12, 12),
        "alias": (1, 1),
        "copy": (1, 1),
        "no-drop": (1, 1),
        "not-allowed": (1, 1),
        "grab": (12, 12),
        "grabbing": (12, 12),
        "all-scroll": (12, 12),
        "col-resize": (12, 12),
        "row-resize": (12, 12),
        "n-resize": (12, 4),
        "e-resize": (20, 12),
        "s-resize": (12, 20),
        "w-resize": (4, 12),
        "ne-resize": (19, 5),
        "nw-resize": (5, 5),
        "se-resize": (19, 19),
        "sw-resize": (5, 19),
        "ew-resize": (12, 12),
        "ns-resize": (12, 12),
        "nesw-resize": (12, 12),
        "nwse-resize": (12, 12),
        "zoom-in": (9, 9),
        "zoom-out": (9, 9),
        "pen": (2, 22),
        "pencil": (2, 22),
        "pipette": (2, 22),
        "move": (12, 12),
        "skull": (12, 12),
        "middle_finger": (12, 12),
        "rock_and_roll": (12, 12),
        "up": (12, 2),
        "right": (22, 12),
        "down": (12, 22),
        "left": (2, 12)
    }

    manifest_hl = "name = Phinger\ndescription = Phinger Cursors (Dark) by Philipp Schaffrath (phisch)\nversion = 1.0\ncursors_directory = hyprcursors\n"
    (gen_dir / "manifest.hl").write_text(manifest_hl)

    index_theme = "[Icon Theme]\nName=Phinger\nComment=Phinger Cursors (Dark) by Philipp Schaffrath (phisch)\nInherits=core\n"
    (gen_dir / "index.theme").write_text(index_theme)

    for c in dark_cursors:
        name = c["name"]
        svg_file = src_dir / "theme" / f"dark/{name}_24.svg"
        if not svg_file.exists():
            continue
        svg_content = svg_file.read_text()
        base_x, base_y = hotspots.get(name, (1, 1))

        # 1. Hyprcursor .hlc
        meta = f"hotspot_x = {base_x / 24.0:.3f}\nhotspot_y = {base_y / 24.0:.3f}\ndefine_size = 24, {name}.svg\n"
        write_hlc(gen_dir / "hyprcursors" / f"{name}.hlc", meta, {f"{name}.svg": svg_content})

        # 2. Multi-size XCursor
        frames = []
        for s in SIZES:
            png = render_svg_to_png(svg_file, s)
            hx = int(round(base_x * s / 24.0))
            hy = int(round(base_y * s / 24.0))
            frames.append((s, hx, hy, png, 50))
        create_xcursor(frames, gen_dir / "cursors" / name)

        # 3. Aliases
        for alias in c.get("aliases") or []:
            # XCursor alias symlink
            alias_path = gen_dir / "cursors" / alias
            if not alias_path.exists():
                alias_path.symlink_to(name)
            # Hyprcursor alias copy/link
            alias_hlc = gen_dir / "hyprcursors" / f"{alias}.hlc"
            if not alias_hlc.exists():
                shutil.copy2(gen_dir / "hyprcursors" / f"{name}.hlc", alias_hlc)

    # Extra canonical aliases
    alias_pairs = [
        ("left_ptr", "default"),
        ("arrow", "default"),
        ("top_left_arrow", "default"),
        ("pointing_hand", "pointer"),
        ("hand2", "pointer"),
        ("left_ptr_watch", "progress"),
        ("watch", "wait"),
        ("ibeam", "text"),
        ("size_ver", "ns-resize"),
        ("size_hor", "ew-resize"),
        ("size_bdiag", "nesw-resize"),
        ("size_fdiag", "nwse-resize"),
        ("split_v", "row-resize"),
        ("split_h", "col-resize"),
        ("cross", "crosshair"),
        ("tcross", "crosshair"),
        ("hand1", "grab"),
        ("openhand", "grab"),
        ("closedhand", "grabbing"),
        ("dnd-none", "not-allowed"),
        ("dnd-move", "move")
    ]
    for src, dst in alias_pairs:
        if (gen_dir / "cursors" / dst).exists() and not (gen_dir / "cursors" / src).exists():
            (gen_dir / "cursors" / src).symlink_to(dst)
        if (gen_dir / "hyprcursors" / f"{dst}.hlc").exists() and not (gen_dir / "hyprcursors" / f"{src}.hlc").exists():
            shutil.copy2(gen_dir / "hyprcursors" / f"{dst}.hlc", gen_dir / "hyprcursors" / f"{src}.hlc")

    shutil.copy2(src_dir / "theme/dark/default_24.svg", dest_dir / "preview.svg")
    print("Phinger build complete.")

# -------------------------------------------------------------
# 2. OREO BUILDER
# -------------------------------------------------------------
def build_oreo():
    print("Building Oreo...")
    src_dir = SCRATCH_AUDIT / "oreo"
    dest_dir = THEMES_DIR / "oreo"
    gen_dir = dest_dir / "generated" / "Oreo"
    if gen_dir.exists(): shutil.rmtree(gen_dir)
    (gen_dir / "hyprcursors").mkdir(parents=True, exist_ok=True)
    (gen_dir / "cursors").mkdir(parents=True, exist_ok=True)

    manifest_hl = "name = Oreo\ndescription = Oreo Cursors (Black) by Alexey Varfolomeev (varlesh)\nversion = 1.0\ncursors_directory = hyprcursors\n"
    (gen_dir / "manifest.hl").write_text(manifest_hl)

    index_theme = "[Icon Theme]\nName=Oreo\nComment=Oreo Cursors (Black) by Alexey Varfolomeev (varlesh)\nInherits=core\n"
    (gen_dir / "index.theme").write_text(index_theme)

    # Process .svg.oreo into .svg with dark colorway (#424242)
    svg_map = {}
    base_dir = src_dir / "generator" / "oreo_base_cursors"
    for f in base_dir.glob("*.svg.oreo"):
        base_name = f.name[:-9] # strip .svg.oreo
        content = f.read_text()
        content = content.replace("{{ background }}", "#424242")
        content = content.replace("{{ label }}", "#ffffff")
        content = content.replace("{{ shadow }}", "#000000")
        content = re_shadow = content.replace("{{ shadow opacity }}", "0.4")
        svg_map[base_name] = content

    # Parse config files for hotspots
    config_dir = src_dir / "src" / "config"
    hotspots = {}
    for cfg in config_dir.glob("*.cursor"):
        name = cfg.stem
        lines = [l.strip() for l in cfg.read_text().splitlines() if l.strip() and not l.startswith("#")]
        for l in lines:
            parts = l.split()
            if len(parts) >= 3 and parts[0] == "32":
                hotspots[name] = (int(parts[1]), int(parts[2]))
                break

    for name, svg_content in svg_map.items():
        if "-0" in name or "-1" in name or "-2" in name or "-3" in name or "-4" in name:
            # frame of animated cursor, handled separately if needed
            continue
        base_x, base_y = hotspots.get(name, (8, 2) if "ptr" in name or name == "default" else (16, 16))

        # Hyprcursor .hlc
        meta = f"hotspot_x = {base_x / 32.0:.3f}\nhotspot_y = {base_y / 32.0:.3f}\ndefine_size = 32, {name}.svg\n"
        write_hlc(gen_dir / "hyprcursors" / f"{name}.hlc", meta, {f"{name}.svg": svg_content})

        # Multi-size XCursor
        frames = []
        for s in SIZES:
            png = render_svg_to_png(svg_content, s)
            hx = int(round(base_x * s / 32.0))
            hy = int(round(base_y * s / 32.0))
            frames.append((s, hx, hy, png, 50))
        create_xcursor(frames, gen_dir / "cursors" / name)

    # Process cursorList aliases
    cursor_list = src_dir / "src" / "cursorList"
    if cursor_list.exists():
        for line in cursor_list.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            parts = line.split()
            if len(parts) == 2:
                src, dst = parts[0], parts[1]
                if (gen_dir / "cursors" / src).exists() and not (gen_dir / "cursors" / dst).exists():
                    (gen_dir / "cursors" / dst).symlink_to(src)
                if (gen_dir / "hyprcursors" / f"{src}.hlc").exists() and not (gen_dir / "hyprcursors" / f"{dst}.hlc").exists():
                    shutil.copy2(gen_dir / "hyprcursors" / f"{src}.hlc", gen_dir / "hyprcursors" / f"{dst}.hlc")

    # Extra canonical aliases
    alias_pairs = [
        ("left_ptr", "default"),
        ("arrow", "default"),
        ("top_left_arrow", "default"),
        ("pointer", "link"),
        ("pointing_hand", "link"),
        ("hand2", "link"),
        ("ibeam", "text"),
        ("cross", "crosshair"),
        ("left_ptr_watch", "progress"),
        ("watch", "wait")
    ]
    for src, dst in alias_pairs:
        if (gen_dir / "cursors" / dst).exists() and not (gen_dir / "cursors" / src).exists():
            (gen_dir / "cursors" / src).symlink_to(dst)
        if (gen_dir / "hyprcursors" / f"{dst}.hlc").exists() and not (gen_dir / "hyprcursors" / f"{src}.hlc").exists():
            shutil.copy2(gen_dir / "hyprcursors" / f"{dst}.hlc", gen_dir / "hyprcursors" / f"{src}.hlc")

    (dest_dir / "preview.svg").write_text(svg_map["default"])
    print("Oreo build complete.")

# -------------------------------------------------------------
# 3. VOLANTES BUILDER
# -------------------------------------------------------------
def build_volantes():
    print("Building Volantes...")
    src_dir = SCRATCH_AUDIT / "volantes"
    dest_dir = THEMES_DIR / "volantes"
    gen_dir = dest_dir / "generated" / "Volantes"
    if gen_dir.exists(): shutil.rmtree(gen_dir)
    (gen_dir / "hyprcursors").mkdir(parents=True, exist_ok=True)
    (gen_dir / "cursors").mkdir(parents=True, exist_ok=True)

    manifest_hl = "name = Volantes\ndescription = Volantes Cursors by Alexey Varfolomeev (varlesh)\nversion = 1.0\ncursors_directory = hyprcursors\n"
    (gen_dir / "manifest.hl").write_text(manifest_hl)

    index_theme = "[Icon Theme]\nName=Volantes\nComment=Volantes Cursors by Alexey Varfolomeev (varlesh)\nInherits=core\n"
    (gen_dir / "index.theme").write_text(index_theme)

    svg_dir = src_dir / "src" / "volantes_cursors"
    config_dir = src_dir / "src" / "config"

    hotspots = {}
    for cfg in config_dir.glob("*.cursor"):
        name = cfg.stem
        lines = [l.strip() for l in cfg.read_text().splitlines() if l.strip() and not l.startswith("#")]
        for l in lines:
            parts = l.split()
            if len(parts) >= 3 and parts[0] == "24":
                hotspots[name] = (int(parts[1]), int(parts[2]))
                break

    for svg_file in svg_dir.glob("*.svg"):
        if svg_file.name.endswith("_24.svg"):
            name = svg_file.stem[:-3]
        else:
            name = svg_file.stem

        if "-0" in name or "-1" in name or "-2" in name: # frame of animated cursor
            continue

        svg_content = svg_file.read_text()
        base_x, base_y = hotspots.get(name, (2, 1) if "ptr" in name or name == "default" else (12, 12))

        # Hyprcursor .hlc
        meta = f"hotspot_x = {base_x / 24.0:.3f}\nhotspot_y = {base_y / 24.0:.3f}\ndefine_size = 24, {name}.svg\n"
        write_hlc(gen_dir / "hyprcursors" / f"{name}.hlc", meta, {f"{name}.svg": svg_content})

        # Multi-size XCursor
        frames = []
        for s in SIZES:
            png = render_svg_to_png(svg_file, s)
            hx = int(round(base_x * s / 24.0))
            hy = int(round(base_y * s / 24.0))
            frames.append((s, hx, hy, png, 50))
        create_xcursor(frames, gen_dir / "cursors" / name)

    # Process cursorList aliases
    cursor_list = src_dir / "src" / "cursorList"
    if cursor_list.exists():
        for line in cursor_list.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            parts = line.split()
            if len(parts) == 2:
                src, dst = parts[0], parts[1]
                if (gen_dir / "cursors" / src).exists() and not (gen_dir / "cursors" / dst).exists():
                    (gen_dir / "cursors" / dst).symlink_to(src)
                if (gen_dir / "hyprcursors" / f"{src}.hlc").exists() and not (gen_dir / "hyprcursors" / f"{dst}.hlc").exists():
                    shutil.copy2(gen_dir / "hyprcursors" / f"{src}.hlc", gen_dir / "hyprcursors" / f"{dst}.hlc")

    # Extra canonical aliases
    alias_pairs = [
        ("left_ptr", "default"),
        ("arrow", "default"),
        ("top_left_arrow", "default"),
        ("pointer", "link"),
        ("pointing_hand", "link"),
        ("hand2", "link"),
        ("ibeam", "text"),
        ("cross", "crosshair"),
        ("left_ptr_watch", "progress"),
        ("watch", "wait")
    ]
    for src, dst in alias_pairs:
        if (gen_dir / "cursors" / dst).exists() and not (gen_dir / "cursors" / src).exists():
            (gen_dir / "cursors" / src).symlink_to(dst)
        if (gen_dir / "hyprcursors" / f"{dst}.hlc").exists() and not (gen_dir / "hyprcursors" / f"{src}.hlc").exists():
            shutil.copy2(gen_dir / "hyprcursors" / f"{dst}.hlc", gen_dir / "hyprcursors" / f"{src}.hlc")

    shutil.copy2(svg_dir / "default.svg", dest_dir / "preview.svg")
    print("Volantes build complete.")

# -------------------------------------------------------------
# 4. NORDZY BUILDER
# -------------------------------------------------------------
def build_nordzy():
    print("Building Nordzy...")
    src_dir = SCRATCH_AUDIT / "nordzy"
    dest_dir = THEMES_DIR / "nordzy"
    gen_dir = dest_dir / "generated" / "Nordzy"
    if gen_dir.exists(): shutil.rmtree(gen_dir)

    # Copy native Hyprcursor and XCursor
    shutil.copytree(src_dir / "hyprcursors/themes/Nordzy-hyprcursors", gen_dir)
    shutil.copytree(src_dir / "xcursors/Nordzy-cursors/cursors", gen_dir / "cursors")
    shutil.copy2(src_dir / "xcursors/Nordzy-cursors/index.theme", gen_dir / "index.theme")

    # Extract preview from left_ptr or default
    preview_src = src_dir / "tools" / "svg" / "Nordzy-cursors" / "left_ptr.svg"
    if preview_src.exists():
        shutil.copy2(preview_src, dest_dir / "preview.svg")
    else:
        # extract SVG from default.hlc
        with zipfile.ZipFile(gen_dir / "hyprcursors" / "left_ptr.hlc") as zf:
            (dest_dir / "preview.svg").write_bytes(zf.read("left_ptr.svg"))
    print("Nordzy build complete.")

# -------------------------------------------------------------
# 5. CAPITAINE BUILDER
# -------------------------------------------------------------
def build_capitaine():
    print("Building Capitaine...")
    src_dir = SCRATCH_AUDIT / "capitaine"
    dest_dir = THEMES_DIR / "capitaine"
    gen_dir = dest_dir / "generated" / "Capitaine"
    if gen_dir.exists(): shutil.rmtree(gen_dir)
    (gen_dir / "hyprcursors").mkdir(parents=True, exist_ok=True)
    (gen_dir / "cursors").mkdir(parents=True, exist_ok=True)

    manifest_hl = "name = Capitaine\ndescription = Capitaine Cursors by Keefer Rourke\nversion = 1.0\ncursors_directory = hyprcursors\n"
    (gen_dir / "manifest.hl").write_text(manifest_hl)

    index_theme = "[Icon Theme]\nName=Capitaine\nComment=Capitaine Cursors by Keefer Rourke\nInherits=core\n"
    (gen_dir / "index.theme").write_text(index_theme)

    svg_dir = src_dir / "src" / "svg" / "dark"
    spec_dir = src_dir / "src" / "config" / "static"

    hotspots = {}
    for spec in spec_dir.glob("*.spec"):
        name = spec.stem
        parts = spec.read_text().strip().split()
        if len(parts) >= 2:
            hotspots[name] = (int(parts[0]), int(parts[1]))

    for svg_file in svg_dir.glob("*.svg"):
        name = svg_file.stem
        if "-0" in name or "-1" in name or "-2" in name: # frame of animation
            continue
        base_x, base_y = hotspots.get(name, (2, 2) if "ptr" in name or name == "default" else (12, 12))
        svg_content = svg_file.read_text()

        # Hyprcursor .hlc
        meta = f"hotspot_x = {base_x / 24.0:.3f}\nhotspot_y = {base_y / 24.0:.3f}\ndefine_size = 24, {name}.svg\n"
        write_hlc(gen_dir / "hyprcursors" / f"{name}.hlc", meta, {f"{name}.svg": svg_content})

        # Multi-size XCursor
        frames = []
        for s in SIZES:
            png = render_svg_to_png(svg_file, s)
            hx = int(round(base_x * s / 24.0))
            hy = int(round(base_y * s / 24.0))
            frames.append((s, hx, hy, png, 50))
        create_xcursor(frames, gen_dir / "cursors" / name)

    # Process cursor-aliases
    alias_file = src_dir / "src" / "cursor-aliases"
    if alias_file.exists():
        for line in alias_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            parts = line.split()
            if len(parts) == 2:
                dst, src = parts[0], parts[1]
                if (gen_dir / "cursors" / src).exists() and not (gen_dir / "cursors" / dst).exists():
                    (gen_dir / "cursors" / dst).symlink_to(src)
                if (gen_dir / "hyprcursors" / f"{src}.hlc").exists() and not (gen_dir / "hyprcursors" / f"{dst}.hlc").exists():
                    shutil.copy2(gen_dir / "hyprcursors" / f"{src}.hlc", gen_dir / "hyprcursors" / f"{dst}.hlc")

    alias_pairs = [
        ("default", "left_ptr"),
        ("arrow", "left_ptr"),
        ("top_left_arrow", "left_ptr"),
        ("pointer", "pointing_hand"),
        ("hand2", "pointing_hand"),
        ("link", "pointing_hand"),
        ("ibeam", "text"),
        ("cross", "crosshair"),
        ("left_ptr_watch", "progress"),
        ("watch", "wait")
    ]
    for src, dst in alias_pairs:
        if (gen_dir / "cursors" / dst).exists() and not (gen_dir / "cursors" / src).exists():
            (gen_dir / "cursors" / src).symlink_to(dst)
        if (gen_dir / "hyprcursors" / f"{dst}.hlc").exists() and not (gen_dir / "hyprcursors" / f"{src}.hlc").exists():
            shutil.copy2(gen_dir / "hyprcursors" / f"{dst}.hlc", gen_dir / "hyprcursors" / f"{src}.hlc")

    shutil.copy2(svg_dir / "default.svg", dest_dir / "preview.svg")
    print("Capitaine build complete.")

if __name__ == "__main__":
    build_phinger()
    build_oreo()
    build_volantes()
    build_nordzy()
    build_capitaine()
    print("All bundled cursor themes built successfully.")
