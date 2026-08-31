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


def is_cursor_theme_dir(dir_path_str: str) -> tuple[bool, str]:
    """Check if directory contains a cursor theme structure in a single shallow pass."""
    try:
        has_cursors = False
        has_index = False
        has_hypr = False
        has_hypr_dir = False
        index_file_path = None
        with os.scandir(dir_path_str) as it:
            for entry in it:
                n = entry.name.lower()
                if n == "cursors" and entry.is_dir():
                    has_cursors = True
                elif n == "hyprcursors" and entry.is_dir():
                    has_hypr_dir = True
                elif n == "index.theme" and entry.is_file():
                    has_index = True
                    index_file_path = entry.path
                elif n in ("manifest.hl", "manifest.toml") and entry.is_file():
                    has_hypr = True

        if has_cursors or has_index or has_hypr or has_hypr_dir:
            theme_name = os.path.basename(dir_path_str)
            if index_file_path:
                try:
                    with open(index_file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if line.strip().lower().startswith("name="):
                                theme_name = line.strip().split("=", 1)[1].strip()
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

                full_path_str = entry.path
                try:
                    is_dir = entry.is_dir(follow_symlinks=True)
                    is_file = entry.is_file(follow_symlinks=True)
                except OSError:
                    continue

                if is_dir:
                    is_theme, theme_name = is_cursor_theme_dir(full_path_str)
                    entries.append({
                        "name": name,
                        "path": full_path_str,
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
                            "path": full_path_str,
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

    # Sort: cursor themes first, then regular folders alphabetically, then archives alphabetically
    entries.sort(key=lambda x: (x["sort_order"], x["name"].lower()))

    # Build breadcrumbs
    breadcrumbs = []
    curr = target_path
    while curr != curr.parent:
        breadcrumbs.append({
            "name": curr.name or "/",
            "path": str(curr)
        })
        curr = curr.parent
    breadcrumbs.append({"name": "/", "path": "/"})
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
    parser = argparse.ArgumentParser(description="Omarchy File Browser Helper")
    parser.add_argument("--path", default="~/Downloads", help="Directory path to list")
    args = parser.parse_args()

    result = list_directory(args.path)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
