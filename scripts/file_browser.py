#!/usr/bin/env python3
"""
Fast, secure directory browser and cursor candidate inspector for Omarchy Cursor Switcher.
Returns JSON with directories, cursor archives, and cursor theme folders.
"""

import sys
import os
import re
import json
import argparse
from pathlib import Path

ARCHIVE_EXTENSIONS = {
    ".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2", ".tar", ".zip"
}


def human_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def is_cursor_archive(filename: str) -> bool:
    lower = filename.lower()
    for ext in ARCHIVE_EXTENSIONS:
        if lower.endswith(ext):
            return True
    return False


def is_cursor_theme_dir(dir_path: Path) -> tuple[bool, str]:
    """Check if directory contains a cursor theme structure and extract theme name."""
    try:
        if not dir_path.is_dir():
            return False, ""

        has_cursors = (dir_path / "cursors").is_dir()
        has_index = (dir_path / "index.theme").is_file()
        has_hypr = (dir_path / "manifest.hl").is_file() or (dir_path / "manifest.toml").is_file()
        has_hypr_dir = (dir_path / "hyprcursors").is_dir()

        if has_cursors or has_index or has_hypr or has_hypr_dir:
            theme_name = dir_path.name
            if has_index:
                try:
                    with open(dir_path / "index.theme", "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            line = line.strip()
                            if line.lower().startswith("name="):
                                theme_name = line.split("=", 1)[1].strip()
                                break
                except Exception:
                    pass
            return True, theme_name
    except (PermissionError, OSError):
        return False, ""
    return False, ""


def list_directory(target_path_str: str) -> dict:
    home = Path.home()
    if not target_path_str:
        target_path_str = str(home / "Downloads")

    expanded = os.path.expanduser(target_path_str)
    try:
        target_path = Path(expanded).resolve()
    except Exception:
        target_path = home / "Downloads"

    if not target_path.exists() or not target_path.is_dir():
        # Fallback to home or Downloads
        if (home / "Downloads").is_dir():
            target_path = home / "Downloads"
        else:
            target_path = home

    parent_path = str(target_path.parent) if target_path.parent != target_path else ""
    can_go_up = bool(parent_path and parent_path != str(target_path))

    entries = []
    try:
        with os.scandir(target_path) as it:
            for entry in it:
                name = entry.name
                # Skip hidden files unless in .local/share/icons or .icons
                if name.startswith(".") and not (target_path.name in ["icons", ".icons"] or name in [".icons"]):
                    continue

                full_path = Path(entry.path)
                try:
                    is_dir = entry.is_dir(follow_symlinks=True)
                    is_file = entry.is_file(follow_symlinks=True)
                except OSError:
                    continue

                if is_dir:
                    is_theme, theme_name = is_cursor_theme_dir(full_path)
                    entries.append({
                        "name": name,
                        "path": str(full_path),
                        "is_dir": True,
                        "is_archive": False,
                        "is_theme_dir": is_theme,
                        "theme_name": theme_name if is_theme else name,
                        "size_str": "Cursor theme" if is_theme else "Folder",
                        "sort_order": 0 if is_theme else 1
                    })
                elif is_file:
                    if is_cursor_archive(name):
                        try:
                            stat_res = entry.stat()
                            size_str = human_size(stat_res.st_size)
                        except OSError:
                            size_str = "Archive"
                        entries.append({
                            "name": name,
                            "path": str(full_path),
                            "is_dir": False,
                            "is_archive": True,
                            "is_theme_dir": False,
                            "theme_name": name,
                            "size_str": size_str,
                            "sort_order": 2
                        })
    except (PermissionError, OSError) as err:
        return {
            "ok": False,
            "error": f"Cannot access directory: {err}",
            "path": str(target_path),
            "parent": parent_path,
            "can_go_up": can_go_up,
            "entries": []
        }

    # Sort entries: theme dirs first (0), normal dirs (1), archives (2), then alphabetically by name
    entries.sort(key=lambda e: (e["sort_order"], e["name"].lower()))

    # Build breadcrumb segments
    breadcrumbs = []
    curr = target_path
    while curr:
        breadcrumbs.append({
            "name": curr.name or str(curr),
            "path": str(curr)
        })
        if curr.parent == curr:
            break
        curr = curr.parent
    breadcrumbs.reverse()

    return {
        "ok": True,
        "path": str(target_path),
        "parent": parent_path,
        "can_go_up": can_go_up,
        "breadcrumbs": breadcrumbs,
        "entries": entries
    }


def main():
    parser = argparse.ArgumentParser(description="List directory and cursor candidates")
    parser.add_argument("--path", default="", help="Target directory to inspect")
    args = parser.parse_args()

    result = list_directory(args.path)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
