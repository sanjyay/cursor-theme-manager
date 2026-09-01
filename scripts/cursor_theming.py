#!/usr/bin/env python3
"""
Multi-Role Cursor Preview Extractor for Omarchy Cursor Switcher.
Resolves generic semantic cursor roles (default, pointer, text, move, resize, wait)
against Hyprcursor and XCursor theme assets and caches rendered role previews.
"""

import sys
import os
import json
import shutil
import zipfile
import subprocess
import hashlib
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
CACHE_DIR = HOME / ".cache" / "omarchy-cursor-switcher"
ROLES_DIR = CACHE_DIR / "roles"
LOCAL_ICONS = Path(os.environ.get("XDG_DATA_HOME", str(HOME / ".local" / "share"))) / "icons"
SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent

# Canonical Semantic Preview Roles with prioritized alias candidate lists
SEMANTIC_ROLE_ALIASES = {
    "default": [
        "default", "left_ptr", "arrow", "top_left_arrow", "left-arrow"
    ],
    "pointer": [
        "pointer", "pointing_hand", "hand2", "hand", "hand1", "link", "openhand"
    ],
    "text": [
        "text", "xterm", "ibeam", "vertical-text"
    ],
    "move": [
        "all-scroll", "fleur", "size_all", "all-resize", "grab", "move", "dnd-move"
    ],
    "resize": [
        "ew-resize", "col-resize", "sb_h_double_arrow", "h_double_arrow", "size_hor", "left_right",
        "nwse-resize", "se-resize", "row-resize", "ns-resize", "size_ver"
    ],
    "wait": [
        "wait", "watch", "progress", "half-busy", "left_ptr_watch", "08e8e1c95fe2fc01f976f1e063a24ccd"
    ]
}

ROLE_LABELS = {
    "default": "Default",
    "pointer": "Pointer",
    "text": "Text",
    "move": "Move",
    "resize": "Resize",
    "wait": "Wait"
}


def find_theme_directory(theme_input, theme_path_hint=None):
    if theme_path_hint and os.path.isdir(theme_path_hint):
        return Path(theme_path_hint)

    s = str(theme_input).strip()
    if not s:
        return None
    if os.path.isabs(s) and os.path.isdir(s):
        return Path(s)

    search_roots = [LOCAL_ICONS, HOME / ".icons"]
    xdg_data_dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    for d in xdg_data_dirs:
        if d.strip():
            search_roots.append(Path(d.strip()) / "icons")

    candidates = []
    for root in search_roots:
        candidates.append(root / s)
        candidates.append(root / f"{s}-cursors")
        candidates.append(root / s.lower())

    for c in candidates:
        if c.is_dir():
            return c

    for base in search_roots:
        if base.is_dir():
            for d in base.iterdir():
                if not d.is_dir():
                    continue
                if d.name.lower() == s.lower():
                    return d
                idx = d / "index.theme"
                if idx.is_file():
                    try:
                        content = idx.read_text(encoding="utf-8", errors="ignore")
                        for line in content.splitlines():
                            if line.startswith("Name=") and line[5:].strip().lower() == s.lower():
                                return d
                    except Exception:
                        pass
    return None




def extract_role_from_hlc(hlc_path, out_file_base):
    try:
        hotspot_x = -1.0
        hotspot_y = -1.0
        with zipfile.ZipFile(hlc_path, "r") as zf:
            names = zf.namelist()
            # Try to read meta.hl for hotspot
            meta_names = [n for n in names if n == "meta.hl" or n.endswith("/meta.hl")]
            if meta_names:
                try:
                    meta_text = zf.read(meta_names[0]).decode("utf-8", errors="ignore")
                    define_size = 24.0
                    for line in meta_text.splitlines():
                        line = line.strip()
                        if line.startswith("hotspot_x"):
                            val = float(line.split("=")[1].strip())
                            hotspot_x = val
                        elif line.startswith("hotspot_y"):
                            val = float(line.split("=")[1].strip())
                            hotspot_y = val
                        elif line.startswith("define_size"):
                            try:
                                define_size = float(line.split("=")[1].split(",")[0].strip())
                            except Exception:
                                pass
                    if hotspot_x > 1.0 and define_size > 0:
                        hotspot_x /= define_size
                    if hotspot_y > 1.0 and define_size > 0:
                        hotspot_y /= define_size
                except Exception:
                    pass

            svgs = [n for n in names if n.endswith(".svg")]
            if svgs:
                out_path = out_file_base.with_suffix(".svg")
                out_path.write_bytes(zf.read(svgs[0]))
                return str(out_path), hotspot_x, hotspot_y

            pngs = [n for n in names if n.endswith(".png")]
            if pngs:
                pngs.sort(key=lambda n: len(n))
                out_path = out_file_base.with_suffix(".png")
                out_path.write_bytes(zf.read(pngs[-1]))
                return str(out_path), hotspot_x, hotspot_y
    except Exception:
        pass
    return None, -1.0, -1.0


def extract_role_from_xcursor(cursor_file, out_file_base):
    try:
        temp_dir = out_file_base.parent / f"_tmp_{out_file_base.name}"
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        res = subprocess.run(["xcur2png", "-d", str(temp_dir), str(cursor_file)], cwd=str(temp_dir), capture_output=True, text=True)
        if res.returncode == 0:
            pngs = list(temp_dir.glob("*.png"))
            conf_files = list(temp_dir.glob("*.conf"))
            hotspot_x = -1.0
            hotspot_y = -1.0
            if conf_files:
                try:
                    conf_lines = conf_files[0].read_text(encoding="utf-8", errors="ignore").splitlines()
                    for line in conf_lines:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            parts = line.split()
                            if len(parts) >= 3:
                                sz = float(parts[0])
                                xh = float(parts[1])
                                yh = float(parts[2])
                                if sz > 0:
                                    hotspot_x = xh / sz
                                    hotspot_y = yh / sz
                                break
                except Exception:
                    pass

            if pngs:
                pngs.sort(key=lambda p: p.stat().st_size, reverse=True)
                target_png = out_file_base.with_suffix(".png")
                shutil.copy2(pngs[0], target_png)
                shutil.rmtree(temp_dir, ignore_errors=True)
                return str(target_png), hotspot_x, hotspot_y
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass
    return None, -1.0, -1.0


def get_theme_role_previews(theme_name_or_path, theme_path_hint=None):
    ROLES_DIR.mkdir(parents=True, exist_ok=True)
    theme_dir = find_theme_directory(theme_name_or_path, theme_path_hint)
    if not theme_dir or not theme_dir.is_dir():
        return {}

    theme_id = theme_dir.name
    cache_target_dir = ROLES_DIR / theme_id
    cache_target_dir.mkdir(parents=True, exist_ok=True)

    meta_file = cache_target_dir / "meta.json"
    cached_meta = {}
    if meta_file.is_file():
        try:
            cached_meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            cached_meta = {}

    roles_found = {}
    roles_meta = {}

    for role_key, aliases in SEMANTIC_ROLE_ALIASES.items():
        cached_svg = cache_target_dir / f"{role_key}.svg"
        cached_png = cache_target_dir / f"{role_key}.png"

        if cached_svg.is_file() and role_key in cached_meta:
            roles_found[role_key] = str(cached_svg)
            roles_meta[role_key] = cached_meta[role_key]
            continue
        if cached_png.is_file() and role_key in cached_meta:
            roles_found[role_key] = str(cached_png)
            roles_meta[role_key] = cached_meta[role_key]
            continue

        resolved_file = None
        matched_source = ""
        hx = -1.0
        hy = -1.0

        # 1. Hyprcursor shapes in hyprcursors/*.hlc
        if (theme_dir / "hyprcursors").is_dir():
            for alias in aliases:
                hlc = theme_dir / "hyprcursors" / f"{alias}.hlc"
                if hlc.is_file():
                    res, hx, hy = extract_role_from_hlc(hlc, cache_target_dir / role_key)
                    if res:
                        resolved_file = res
                        matched_source = alias
                        break

        # 2. XCursor shapes in cursors/* (resolving symlinks safely)
        if not resolved_file and (theme_dir / "cursors").is_dir():
            for alias in aliases:
                cur = theme_dir / "cursors" / alias
                if cur.is_file():
                    res, hx, hy = extract_role_from_xcursor(cur, cache_target_dir / role_key)
                    if res:
                        resolved_file = res
                        matched_source = alias
                        break

        if resolved_file:
            roles_found[role_key] = resolved_file
            roles_meta[role_key] = {
                "label": ROLE_LABELS.get(role_key, role_key.capitalize()),
                "source": matched_source,
                "hotspot_x": round(hx, 3) if hx >= 0 else -1,
                "hotspot_y": round(hy, 3) if hy >= 0 else -1
            }

    try:
        meta_file.write_text(json.dumps(roles_meta, indent=2), encoding="utf-8")
    except Exception:
        pass

    roles_found["_meta"] = roles_meta
    return roles_found


def get_all_theme_role_previews():
    results = {}
    candidates = []
    search_roots = [LOCAL_ICONS, HOME / ".icons"]
    xdg_data_dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    for d in xdg_data_dirs:
        if d.strip():
            search_roots.append(Path(d.strip()) / "icons")

    for base in search_roots:
        if base.is_dir():
            for d in base.iterdir():
                if d.is_dir():
                    candidates.append(d.name)
    for c in sorted(set(candidates)):
        try:
            r = get_theme_role_previews(c)
            if r and any(k for k in r if not k.startswith("_")):
                results[c] = r
                results[c.lower()] = r
        except Exception:
            pass
    return results



def main():
    if len(sys.argv) < 2:
        print("Usage: cursor_theming.py get-preview-roles [--theme <name>] [--path <path>]", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "get-preview-roles":
        theme = "Banana"
        path_hint = None
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--theme" and i + 1 < len(sys.argv):
                theme = sys.argv[i+1]
                i += 2
            elif sys.argv[i] == "--path" and i + 1 < len(sys.argv):
                path_hint = sys.argv[i+1]
                i += 2
            elif not sys.argv[i].startswith("--"):
                theme = sys.argv[i]
                i += 1
            else:
                i += 1
        roles = get_theme_role_previews(theme, path_hint)
        print(json.dumps(roles))
    elif cmd == "get-all-preview-roles":
        all_roles = get_all_theme_role_previews()
        print(json.dumps(all_roles))
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

