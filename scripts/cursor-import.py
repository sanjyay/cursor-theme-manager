#!/usr/bin/env python3
"""
Secure Import Engine for Omarchy Cursor Switcher.
Imports local cursor theme directories or safe archives into ~/.local/share/icons.
"""

import sys
import os
import re
import json
import shutil
import tarfile
import zipfile
import hashlib
import tempfile
import argparse
import subprocess
from datetime import datetime, timezone

MAX_ARCHIVE_BYTES = 50 * 1024 * 1024    # 50 MB
MAX_EXTRACTED_BYTES = 150 * 1024 * 1024  # 150 MB
MAX_FILE_COUNT = 5000

ARCHIVE_EXTENSIONS = {
    ".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2", ".tar", ".zip"
}


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', name)
    return cleaned.strip('._') or "imported_theme"


def is_safe_relpath(path: str) -> bool:
    if not path or path.startswith("/") or path.startswith("\\"):
        return False
    parts = os.path.normpath(path).split(os.sep)
    return ".." not in parts and parts[0] != ".."


def detect_license_text(content: str) -> str:
    lower = content.lower()
    if "gnu general public license" in lower:
        if "version 3" in lower or "gplv3" in lower or "gpl-3" in lower:
            return "GPL-3.0"
        if "version 2" in lower or "gplv2" in lower or "gpl-2" in lower:
            return "GPL-2.0"
        return "GPL"
    if "mit license" in lower or "permission is hereby granted, free of charge" in lower:
        return "MIT"
    if "apache license" in lower and "version 2.0" in lower:
        return "Apache-2.0"
    if "creative commons" in lower:
        if "attribution-sharealike" in lower or "by-sa" in lower:
            return "CC-BY-SA"
        if "attribution" in lower:
            return "CC-BY"
        if "zero" in lower or "public domain" in lower or "cc0" in lower:
            return "CC0"
    if "mozilla public license" in lower:
        return "MPL-2.0"
    if "bsd" in lower:
        return "BSD"
    return "Unknown"


def scan_license_in_dir(theme_dir: str) -> str:
    for fname in os.listdir(theme_dir):
        if re.match(r'^(license|copying|copyright)(\.[a-z0-9]+)?$', fname, re.IGNORECASE):
            fpath = os.path.join(theme_dir, fname)
            if os.path.isfile(fpath) and not os.path.islink(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        txt = f.read(8192)
                        detected = detect_license_text(txt)
                        if detected != "Unknown":
                            return detected
                except Exception:
                    pass
    return "Unknown"


def compute_content_hash(theme_root: str) -> str:
    hasher = hashlib.sha256()
    cursor_files = []
    for root, _, files in os.walk(theme_root):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, theme_root)
            cursor_files.append((rel, full))
    cursor_files.sort()
    for rel, full in cursor_files:
        hasher.update(rel.encode("utf-8"))
        try:
            with open(full, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
        except Exception:
            pass
    return hasher.hexdigest()


def extract_archive_safely(archive_path: str, stage_dir: str):
    if os.path.getsize(archive_path) > MAX_ARCHIVE_BYTES:
        raise ValueError(f"Archive exceeds maximum allowed size of {MAX_ARCHIVE_BYTES // (1024*1024)} MB")

    total_bytes = 0
    file_count = 0

    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, 'r') as zf:
            infolist = zf.infolist()
            if len(infolist) > MAX_FILE_COUNT:
                raise ValueError(f"Archive contains too many files ({len(infolist)} > {MAX_FILE_COUNT})")
            for info in infolist:
                if not is_safe_relpath(info.filename):
                    raise ValueError(f"Dangerous path in ZIP archive: {info.filename}")
                total_bytes += info.file_size
                if total_bytes > MAX_EXTRACTED_BYTES:
                    raise ValueError(f"Extracted content exceeds size limit of {MAX_EXTRACTED_BYTES // (1024*1024)} MB")
            zf.extractall(stage_dir)
            return

    # Tar archive
    try:
        with tarfile.open(archive_path, 'r:*') as tf:
            members = tf.getmembers()
            if len(members) > MAX_FILE_COUNT:
                raise ValueError(f"Archive contains too many files ({len(members)} > {MAX_FILE_COUNT})")
            for m in members:
                if not is_safe_relpath(m.name):
                    raise ValueError(f"Dangerous path in TAR archive: {m.name}")
                if m.isdev() or m.ischr() or m.isblk() or m.isfifo():
                    raise ValueError(f"Special/device files are forbidden in archive: {m.name}")
                if m.issym() or m.islnk():
                    if not is_safe_relpath(m.linkname):
                        raise ValueError(f"Symlink escapes root in archive: {m.name} -> {m.linkname}")
                total_bytes += m.size
                if total_bytes > MAX_EXTRACTED_BYTES:
                    raise ValueError(f"Extracted content exceeds size limit of {MAX_EXTRACTED_BYTES // (1024*1024)} MB")
            # Extract
            if hasattr(tarfile, 'data_filter'):
                tf.extractall(stage_dir, filter='data')
            else:
                tf.extractall(stage_dir)
            return
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Could not unpack archive: {e}")


def find_theme_root(stage_dir: str) -> str:
    """Finds the actual theme directory inside the staging folder."""
    # Check if stage_dir itself is the theme
    if os.path.isfile(os.path.join(stage_dir, "manifest.hl")) or os.path.isdir(os.path.join(stage_dir, "cursors")):
        return stage_dir

    # Check top-level subdirectories
    candidates = []
    for entry in os.listdir(stage_dir):
        sub = os.path.join(stage_dir, entry)
        if os.path.isdir(sub):
            if os.path.isfile(os.path.join(sub, "manifest.hl")) or os.path.isdir(os.path.join(sub, "cursors")):
                candidates.append(sub)

    if len(candidates) == 1:
        return candidates[0]
    elif len(candidates) > 1:
        # Prefer one named cursors or first candidate
        return candidates[0]

    # Walk 2 levels deep
    for root, dirs, _ in os.walk(stage_dir):
        depth = len(os.path.relpath(root, stage_dir).split(os.sep))
        if depth > 3:
            continue
        if os.path.isfile(os.path.join(root, "manifest.hl")) or os.path.isdir(os.path.join(root, "cursors")):
            return root

    raise ValueError("Not a valid cursor theme: no cursors/ directory or manifest.hl found. Regular icon themes are not supported.")


def validate_symlinks(theme_root: str):
    """Ensures all symlinks within theme_root stay inside theme_root."""
    real_root = os.path.realpath(theme_root)
    for root, dirs, files in os.walk(theme_root, followlinks=False):
        for name in dirs + files:
            full = os.path.join(root, name)
            if os.path.islink(full):
                target = os.path.realpath(full)
                if not target.startswith(real_root + os.sep) and target != real_root:
                    raise ValueError(f"Security error: symlink escapes theme directory ({name} -> {target})")


def detect_theme_metadata(theme_root: str, user_name_override: str = ""):
    has_manifest = os.path.isfile(os.path.join(theme_root, "manifest.hl"))
    has_xcursors = os.path.isdir(os.path.join(theme_root, "cursors"))

    if not has_manifest and not has_xcursors:
        raise ValueError("Directory contains neither manifest.hl (Hyprcursor) nor cursors/ (XCursor).")

    formats = []
    declared_name = user_name_override.strip()

    if has_manifest:
        formats.append("hyprcursor")
        try:
            with open(os.path.join(theme_root, "manifest.hl"), "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    m = re.match(r'^\s*name\s*=\s*([^\n\r]+)', line)
                    if m and not declared_name:
                        declared_name = m.group(1).strip().strip('"\'')
        except Exception:
            pass

    if has_xcursors:
        formats.append("xcursor")
        cursor_files = os.listdir(os.path.join(theme_root, "cursors"))
        if not cursor_files:
            raise ValueError("The cursors/ directory is empty; no cursor images found.")
        # Check index.theme for Name=
        index_theme = os.path.join(theme_root, "index.theme")
        if os.path.isfile(index_theme) and not declared_name:
            try:
                with open(index_theme, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        m = re.match(r'^\s*Name\s*=\s*([^\n\r]+)', line)
                        if m:
                            declared_name = m.group(1).strip()
                            break
            except Exception:
                pass

    if not declared_name:
        declared_name = os.path.basename(theme_root)

    license_name = scan_license_in_dir(theme_root)

    return {
        "declared_name": declared_name,
        "formats": formats,
        "license": license_name
    }


def copy_theme_atomically(src_dir: str, dst_dir: str):
    parent = os.path.dirname(dst_dir)
    os.makedirs(parent, exist_ok=True)
    temp_dst = tempfile.mkdtemp(prefix=".install-", dir=parent)
    try:
        shutil.copytree(src_dir, temp_dst, dirs_exist_ok=True, symlinks=True)
        if os.path.exists(dst_dir):
            shutil.rmtree(dst_dir)
        os.rename(temp_dst, dst_dir)
    finally:
        if os.path.exists(temp_dst):
            shutil.rmtree(temp_dst, ignore_errors=True)


def check_existing_hash(icons_dir: str, content_hash: str):
    """Checks if an imported theme with the same content hash already exists."""
    if not os.path.isdir(icons_dir):
        return None
    for entry in os.listdir(icons_dir):
        full = os.path.join(icons_dir, entry)
        if os.path.isdir(full) and entry.startswith("CursorSwitcher-Imported-"):
            marker = os.path.join(full, ".omarchy-cursor-switcher-imported")
            if os.path.isfile(marker):
                try:
                    with open(marker, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        if meta.get("contentHash") == content_hash:
                            return meta
                except Exception:
                    pass
    return None


def run_import(source_path: str, display_name_override: str = "", script_dir: str = ""):
    if not source_path or not os.path.exists(source_path):
        return {"ok": False, "error": f"Source path does not exist: {source_path}"}

    home = os.environ.get("HOME", "")
    data_home = os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local/share"))
    icons_dir = os.path.join(data_home, "icons")
    os.makedirs(icons_dir, exist_ok=True)

    stage_temp = tempfile.mkdtemp(prefix=".cs-stage-")
    try:
        # Extract or copy into stage
        if os.path.isfile(source_path):
            extract_archive_safely(source_path, stage_temp)
        elif os.path.isdir(source_path):
            # Check size and file count
            total_size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(source_path) for f in fs if not os.path.islink(os.path.join(r, f)))
            file_count = sum(len(fs) for _, _, fs in os.walk(source_path))
            if file_count > MAX_FILE_COUNT:
                return {"ok": False, "error": f"Directory contains too many files ({file_count} > {MAX_FILE_COUNT})"}
            if total_size > MAX_EXTRACTED_BYTES:
                return {"ok": False, "error": f"Directory exceeds size limit of {MAX_EXTRACTED_BYTES // (1024*1024)} MB"}
            shutil.copytree(source_path, os.path.join(stage_temp, "theme"), symlinks=True)
        else:
            return {"ok": False, "error": f"Unsupported source type: {source_path}"}

        theme_root = find_theme_root(stage_temp)
        validate_symlinks(theme_root)
        meta = detect_theme_metadata(theme_root, display_name_override)
        content_hash = compute_content_hash(theme_root)

        # Check deduplication
        existing = check_existing_hash(icons_dir, content_hash)
        if existing:
            return {
                "ok": True,
                "alreadyImported": True,
                "theme": existing
            }

        declared_name = meta["declared_name"]
        slug = re.sub(r'[^a-zA-Z0-9_\-]', '-', declared_name).strip('-')
        if not slug:
            slug = "theme"
        short_hash = content_hash[:12]
        internal_id = f"CursorSwitcher-Imported-{slug}-{short_hash}"
        display_name = f"{declared_name} (Imported)"
        install_path = os.path.join(icons_dir, internal_id)

        # Copy theme to destination
        copy_theme_atomically(theme_root, install_path)

        # Write marker metadata
        theme_record = {
            "id": internal_id,
            "displayName": display_name,
            "sourceType": "imported",
            "imported": True,
            "bundled": False,
            "contentHash": content_hash,
            "importedAt": datetime.now(timezone.utc).isoformat(),
            "formats": meta["formats"],
            "xcursor": internal_id if "xcursor" in meta["formats"] else "",
            "hyprcursor": internal_id if "hyprcursor" in meta["formats"] else "",
            "path": install_path,
            "license": meta["license"],
            "subtitle": f"Imported • {meta['license']}"
        }

        # If XCursor-only or lacks Hyprcursor, run ensure-hyprcursor
        if "xcursor" in meta["formats"] and "hyprcursor" not in meta["formats"]:
            cursorctl_bin = os.path.join(script_dir or os.path.dirname(__file__), "cursorctl")
            if os.path.isfile(cursorctl_bin):
                try:
                    res = subprocess.run([
                        cursorctl_bin, "ensure-hyprcursor",
                        "--xcursor", internal_id,
                        "--theme-path", install_path
                    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
                    if res.returncode == 0:
                        out = res.stdout.strip()
                        if out:
                            theme_record["hyprcursor"] = out
                            if "hyprcursor" not in theme_record["formats"]:
                                theme_record["formats"].append("hyprcursor")
                except Exception as e:
                    sys.stderr.write(f"Conversion note: {e}\n")

        # Save metadata marker inside installed directory
        marker_file = os.path.join(install_path, ".omarchy-cursor-switcher-imported")
        with open(marker_file, "w", encoding="utf-8") as f:
            json.dump(theme_record, f, indent=2)

        return {
            "ok": True,
            "alreadyImported": False,
            "theme": theme_record
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        if os.path.exists(stage_temp):
            shutil.rmtree(stage_temp, ignore_errors=True)


def run_remove(theme_id: str):
    if not theme_id:
        return {"ok": False, "error": "Missing theme ID to remove"}

    # Security check: theme_id must be safe
    if not theme_id.startswith("CursorSwitcher-Imported-") or "/" in theme_id or ".." in theme_id:
        return {"ok": False, "error": "Refusing to remove theme: not a valid imported theme ID"}

    home = os.environ.get("HOME", "")
    data_home = os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local/share"))
    icons_dir = os.path.join(data_home, "icons")
    target = os.path.join(icons_dir, theme_id)

    if not os.path.isdir(target):
        return {"ok": False, "error": f"Imported theme directory not found: {target}"}

    marker = os.path.join(target, ".omarchy-cursor-switcher-imported")
    if not os.path.isfile(marker):
        return {"ok": False, "error": f"Directory is not managed by Cursor Switcher import: {target}"}

    # Remove converted Hyprcursor if present
    if os.path.isdir(icons_dir):
        for entry in os.listdir(icons_dir):
            if entry.startswith(f"CursorSwitcher-XCursor-{theme_id}-"):
                conv_path = os.path.join(icons_dir, entry)
                if os.path.isdir(conv_path):
                    shutil.rmtree(conv_path, ignore_errors=True)

    # Remove theme directory
    shutil.rmtree(target)

    # Clean preview cache if present
    cache_home = os.environ.get("XDG_CACHE_HOME", os.path.join(home, ".cache"))
    preview_cache = os.path.join(cache_home, "omarchy-cursor-switcher", "previews", f"{theme_id}.png")
    if os.path.exists(preview_cache):
        try:
            os.unlink(preview_cache)
        except Exception:
            pass

    return {"ok": True, "removed": theme_id}


def run_rename(theme_id: str, new_name: str):
    if not theme_id or not new_name:
        return {"ok": False, "error": "Missing theme ID or new name"}

    clean_name = re.sub(r'[\r\n\t]+', ' ', new_name).strip()
    if not clean_name or len(clean_name) > 100:
        return {"ok": False, "error": "Invalid theme name"}

    # Security check: theme_id must be safe
    if not theme_id.startswith("CursorSwitcher-Imported-") or "/" in theme_id or ".." in theme_id:
        return {"ok": False, "error": "Refusing to rename theme: not a valid imported theme ID"}

    home = os.environ.get("HOME", "")
    data_home = os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local/share"))
    icons_dir = os.path.join(data_home, "icons")
    target = os.path.join(icons_dir, theme_id)

    if not os.path.isdir(target):
        return {"ok": False, "error": f"Imported theme directory not found: {target}"}

    marker = os.path.join(target, ".omarchy-cursor-switcher-imported")
    if not os.path.isfile(marker):
        return {"ok": False, "error": f"Directory is not managed by Cursor Switcher import: {target}"}

    # Update index.theme if present
    idx_path = os.path.join(target, "index.theme")
    if os.path.isfile(idx_path):
        try:
            lines = []
            with open(idx_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip().startswith("Name="):
                        lines.append(f"Name={clean_name}\n")
                    else:
                        lines.append(line)
            with open(idx_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception as e:
            return {"ok": False, "error": f"Failed to update index.theme: {e}"}

    # Update manifest.hl / manifest.toml if present
    for mname in ["manifest.hl", "manifest.toml"]:
        mpath = os.path.join(target, mname)
        if os.path.isfile(mpath):
            try:
                lines = []
                with open(mpath, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.strip().startswith("name =") or line.strip().startswith("name="):
                            lines.append(f"name = {clean_name}\n")
                        else:
                            lines.append(line)
                with open(mpath, "w", encoding="utf-8") as f:
                    f.writelines(lines)
            except Exception:
                pass

    return {"ok": True, "theme_id": theme_id, "displayName": clean_name}


def main():
    parser = argparse.ArgumentParser(description="Cursor Switcher Import Engine")
    subparsers = parser.add_subparsers(dest="action", required=True)

    # import
    p_import = subparsers.add_parser("import")
    p_import.add_argument("--source", required=True, help="Path to directory or archive")
    p_import.add_argument("--name", default="", help="Optional display name override")

    # remove
    p_remove = subparsers.add_parser("remove")
    p_remove.add_argument("--id", required=True, help="Imported theme ID")

    # rename
    p_rename = subparsers.add_parser("rename")
    p_rename.add_argument("--id", required=True, help="Imported theme ID")
    p_rename.add_argument("--name", required=True, help="New theme display name")

    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    if args.action == "import":
        result = run_import(args.source, args.name, script_dir)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("ok") else 1)
    elif args.action == "remove":
        result = run_remove(args.id)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("ok") else 1)
    elif args.action == "rename":
        result = run_rename(args.id, args.name)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("ok") else 1)



if __name__ == "__main__":
    main()
