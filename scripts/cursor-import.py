#!/usr/bin/env python3
"""
Secure Import and Bundled Theme Materialization Engine for Omarchy Cursor Switcher.
Imports local cursor theme directories or safe archives into ~/.local/share/icons,
and safely materializes verified bundled theme archives from catalog.json.
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
from pathlib import Path

MAX_ARCHIVE_BYTES = 100 * 1024 * 1024   # 100 MB
MAX_EXTRACTED_BYTES = 750 * 1024 * 1024  # 750 MB
MAX_FILE_COUNT = 10000

ARCHIVE_EXTENSIONS = {
    ".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2", ".tar", ".zip"
}

FORBIDDEN_EXTENSIONS = {
    ".sh", ".bash", ".zsh", ".csh", ".ksh", ".exe", ".bat", ".cmd", ".ps1",
    ".bin", ".elf", ".so", ".dll", ".dylib", ".app", ".msi", ".com", ".scr"
}

FORBIDDEN_NAMES = {
    "install.sh", "setup.sh", "install", "setup", "configure", "postinstall.sh"
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


def verify_archive_sha256(archive_path: str, expected_sha256: str) -> bool:
    if not os.path.isfile(archive_path):
        raise FileNotFoundError(f"Archive file not found: {archive_path}")
    hasher = hashlib.sha256()
    with open(archive_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    actual_sha = hasher.hexdigest()
    if expected_sha256 and actual_sha.lower() != expected_sha256.lower():
        raise ValueError(
            f"Integrity check failed for {os.path.basename(archive_path)}: expected SHA-256 {expected_sha256}, got {actual_sha}"
        )
    return True


def validate_theme_security(theme_root: str):
    """Ensures no dangerous installer scripts, forbidden extensions, or executable binaries exist in theme."""
    for root, _, files in os.walk(theme_root, followlinks=False):
        for name in files:
            full = os.path.join(root, name)
            lower_name = name.lower()
            if lower_name in FORBIDDEN_NAMES:
                raise ValueError(f"Forbidden executable installer script in theme: {name}")
            ext = os.path.splitext(lower_name)[1]
            if ext in FORBIDDEN_EXTENSIONS:
                raise ValueError(f"Forbidden file extension in theme: {name}")
            rel = os.path.relpath(full, theme_root)
            parts = rel.split(os.sep)
            if parts[0] not in ("cursors", "hyprcursors"):
                if os.path.isfile(full) and not os.path.islink(full):
                    try:
                        with open(full, "rb") as f:
                            header = f.read(4)
                            if header == b"\x7fELF":
                                raise ValueError(f"Forbidden ELF executable binary in theme: {name}")
                    except Exception:
                        pass


def extract_archive_safely(archive_path: str, stage_dir: str):
    if not os.path.isfile(archive_path):
        raise FileNotFoundError(f"Archive file not found: {archive_path}")

    if os.path.getsize(archive_path) > MAX_ARCHIVE_BYTES:
        raise ValueError(f"Archive exceeds maximum allowed size of {MAX_ARCHIVE_BYTES // (1024*1024)} MB")

    total_bytes = 0

    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, 'r') as zf:
            infolist = zf.infolist()
            if len(infolist) > MAX_FILE_COUNT:
                raise ValueError(f"Archive contains too many files ({len(infolist)} > {MAX_FILE_COUNT})")
            for info in infolist:
                if not is_safe_relpath(info.filename):
                    raise ValueError(f"Dangerous path in ZIP archive: {info.filename}")
                base_name = os.path.basename(info.filename).lower()
                if base_name in FORBIDDEN_NAMES:
                    raise ValueError(f"Forbidden installer script in ZIP: {info.filename}")
                ext = os.path.splitext(base_name)[1]
                if ext in FORBIDDEN_EXTENSIONS:
                    raise ValueError(f"Forbidden file extension in ZIP: {info.filename}")
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
                base_name = os.path.basename(m.name).lower()
                if base_name in FORBIDDEN_NAMES:
                    raise ValueError(f"Forbidden installer script in TAR: {m.name}")
                ext = os.path.splitext(base_name)[1]
                if ext in FORBIDDEN_EXTENSIONS:
                    raise ValueError(f"Forbidden file extension in TAR: {m.name}")
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
    if os.path.isfile(os.path.join(stage_dir, "manifest.hl")) or os.path.isdir(os.path.join(stage_dir, "cursors")):
        return stage_dir

    candidates = []
    for entry in os.listdir(stage_dir):
        sub = os.path.join(stage_dir, entry)
        if os.path.isdir(sub):
            if os.path.isfile(os.path.join(sub, "manifest.hl")) or os.path.isdir(os.path.join(sub, "cursors")):
                candidates.append(sub)

    if len(candidates) == 1:
        return candidates[0]
    elif len(candidates) > 1:
        return candidates[0]

    for root, _, _ in os.walk(stage_dir):
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
        if os.path.isfile(source_path):
            extract_archive_safely(source_path, stage_temp)
        elif os.path.isdir(source_path):
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
        validate_theme_security(theme_root)
        meta = detect_theme_metadata(theme_root, display_name_override)
        content_hash = compute_content_hash(theme_root)

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
        display_name = declared_name
        install_path = os.path.join(icons_dir, internal_id)

        copy_theme_atomically(theme_root, install_path)

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
            "subtitle": meta["license"] if meta["license"] and meta["license"] != "Unknown" else ""
        }

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
        return {"ok": False, "error": "Missing theme ID"}

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

    shutil.rmtree(target)

    for entry in os.listdir(icons_dir):
        if entry.startswith("CursorSwitcher-XCursor-" + theme_id) or entry.startswith("CursorSwitcher-Themed-" + theme_id):
            full = os.path.join(icons_dir, entry)
            if os.path.isdir(full):
                shutil.rmtree(full, ignore_errors=True)

    cache_home = os.environ.get("XDG_CACHE_HOME", os.path.join(home, ".cache"))
    theme_cache = os.path.join(cache_home, "omarchy", "cursor-previews", theme_id)
    if os.path.isdir(theme_cache):
        shutil.rmtree(theme_cache, ignore_errors=True)

    return {"ok": True, "removed": theme_id}


def run_rename(theme_id: str, new_name: str):
    if not theme_id or not new_name:
        return {"ok": False, "error": "Missing theme ID or new name"}

    clean_name = re.sub(r'[\r\n\t]+', ' ', new_name).strip()
    if not clean_name or len(clean_name) > 100:
        return {"ok": False, "error": "Invalid theme name"}

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

    try:
        with open(marker, "r", encoding="utf-8") as f:
            meta = json.load(f)
        meta["displayName"] = clean_name
        with open(marker, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
    except Exception as e:
        return {"ok": False, "error": f"Failed to update metadata marker: {e}"}

    idx_path = os.path.join(target, "index.theme")
    if os.path.isfile(idx_path):
        try:
            lines = []
            found = False
            with open(idx_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip().startswith("Name="):
                        lines.append(f"Name={clean_name}\n")
                        found = True
                    else:
                        lines.append(line)
            if not found:
                lines.insert(0, f"Name={clean_name}\n")
            with open(idx_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception as e:
            return {"ok": False, "error": f"Failed to update index.theme: {e}"}

    for mname in ["manifest.hl", "manifest.toml"]:
        mpath = os.path.join(target, mname)
        if os.path.isfile(mpath):
            try:
                lines = []
                found = False
                with open(mpath, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.strip().startswith("name =") or line.strip().startswith("name="):
                            lines.append(f"name = {clean_name}\n")
                            found = True
                        else:
                            lines.append(line)
                if not found:
                    lines.insert(0, f"name = {clean_name}\n")
                with open(mpath, "w", encoding="utf-8") as f:
                    f.writelines(lines)
            except Exception:
                pass

    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config"))
    state_file = os.path.join(config_home, "omarchy", "cursor-switcher.json")
    if os.path.isfile(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                st = json.load(f)
            if st.get("theme") == theme_id:
                st["displayName"] = clean_name
                with open(state_file, "w", encoding="utf-8") as f:
                    json.dump(st, f, indent=2)
        except Exception:
            pass

    return {"ok": True, "theme_id": theme_id, "displayName": clean_name}


# --------------------------------------------------------------------------
# Bundled Theme Materialization & Installation Engine
# --------------------------------------------------------------------------

def install_single_theme_archive(archive_path: str, target_dir: str, version: str = "1.0", expected_sha: str = None, force_error: bool = True):
    if not os.path.isfile(archive_path):
        raise FileNotFoundError(f"Bundled archive not found: {archive_path}")
    if expected_sha:
        verify_archive_sha256(archive_path, expected_sha)

    parent_dir = os.path.dirname(target_dir)
    os.makedirs(parent_dir, exist_ok=True)

    # Collision check: if target directory exists but is unmanaged by cursor-switcher
    if os.path.exists(target_dir):
        marker = os.path.join(target_dir, ".omarchy-cursor-switcher-theme")
        if not os.path.isfile(marker):
            if force_error:
                raise ValueError(f"Target exists and is not managed by cursor-switcher: {target_dir}")
            return {"id": os.path.basename(target_dir), "status": "skipped", "path": target_dir}

    stage_temp = tempfile.mkdtemp(prefix=".install-stage-", dir=parent_dir)
    try:
        extract_archive_safely(archive_path, stage_temp)
        theme_root = find_theme_root(stage_temp)
        validate_symlinks(theme_root)
        validate_theme_security(theme_root)
        meta = detect_theme_metadata(theme_root)
        if not meta["formats"]:
            raise ValueError(f"Theme at {archive_path} contains no valid cursor formats")

        marker_theme = os.path.join(theme_root, ".omarchy-cursor-switcher-theme")
        with open(marker_theme, "w", encoding="utf-8") as f:
            f.write(f"{version}\n")

        if expected_sha:
            marker_sha = os.path.join(theme_root, ".omarchy-cursor-switcher-sha256")
            with open(marker_sha, "w", encoding="utf-8") as f:
                f.write(f"{expected_sha}\n")

        temp_dst = tempfile.mkdtemp(prefix=".theme-atomic-", dir=parent_dir)
        try:
            shutil.copytree(theme_root, temp_dst, dirs_exist_ok=True, symlinks=True)
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            os.rename(temp_dst, target_dir)
        finally:
            if os.path.exists(temp_dst):
                shutil.rmtree(temp_dst, ignore_errors=True)

        return {"id": os.path.basename(target_dir), "status": "installed", "path": target_dir}
    finally:
        if os.path.exists(stage_temp):
            shutil.rmtree(stage_temp, ignore_errors=True)


def install_single_theme_dir(src_dir: str, target_dir: str, version: str = "1.0", force_error: bool = True):
    if not os.path.isdir(src_dir):
        raise ValueError(f"Source directory not found: {src_dir}")
    validate_symlinks(src_dir)
    validate_theme_security(src_dir)

    parent_dir = os.path.dirname(target_dir)
    os.makedirs(parent_dir, exist_ok=True)

    if os.path.exists(target_dir):
        marker = os.path.join(target_dir, ".omarchy-cursor-switcher-theme")
        if not os.path.isfile(marker):
            if force_error:
                raise ValueError(f"Target exists and is not managed by cursor-switcher: {target_dir}")
            return {"id": os.path.basename(target_dir), "status": "skipped", "path": target_dir}
        with open(marker, "r", encoding="utf-8") as f:
            curr_ver = f.read().strip()
        if curr_ver == str(version):
            return {"id": os.path.basename(target_dir), "status": "up-to-date", "path": target_dir}

    temp_dst = tempfile.mkdtemp(prefix=".theme-atomic-", dir=parent_dir)
    try:
        shutil.copytree(src_dir, temp_dst, dirs_exist_ok=True, symlinks=True)
        marker_theme = os.path.join(temp_dst, ".omarchy-cursor-switcher-theme")
        with open(marker_theme, "w", encoding="utf-8") as f:
            f.write(f"{version}\n")
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        os.rename(temp_dst, target_dir)
        return {"id": os.path.basename(target_dir), "status": "installed", "path": target_dir}
    finally:
        if os.path.exists(temp_dst):
            shutil.rmtree(temp_dst, ignore_errors=True)


def install_bundled_themes(catalog_path: str = None, themes_dir: str = None, version: str = None, target_icons_dir: str = None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.dirname(script_dir)

    if not catalog_path:
        candidates = [
            os.path.join(plugin_root, "themes", "bundled", "catalog.json"),
            os.path.join(plugin_root, "themes", "catalog.json"),
        ]
        if themes_dir:
            candidates.insert(0, os.path.join(themes_dir, "bundled", "catalog.json"))
            candidates.insert(1, os.path.join(themes_dir, "catalog.json"))
        for c in candidates:
            if os.path.isfile(c):
                catalog_path = c
                break

    if not catalog_path or not os.path.isfile(catalog_path):
        raise FileNotFoundError(f"Catalog file not found: {catalog_path or 'themes/bundled/catalog.json'}")

    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    home = os.environ.get("HOME", "")
    data_home = os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local/share"))
    if not target_icons_dir:
        target_icons_dir = os.path.join(data_home, "icons")
    os.makedirs(target_icons_dir, exist_ok=True)

    results = []
    catalog_root = os.path.dirname(os.path.abspath(catalog_path))
    repo_root = os.path.dirname(catalog_root) if os.path.basename(catalog_root) == "bundled" else catalog_root

    for entry in catalog:
        theme_id = entry.get("id")
        archive_rel = entry.get("archive")
        expected_sha = entry.get("sha256")
        expected_root = entry.get("expectedRoot", entry.get("displayName", theme_id))
        theme_version = version or entry.get("version", "1.0")

        # Resolve archive full path
        if os.path.isabs(archive_rel):
            archive_path = archive_rel
        else:
            candidates = [
                os.path.join(plugin_root, archive_rel),
                os.path.join(repo_root, archive_rel),
                os.path.join(catalog_root, os.path.basename(archive_rel)),
                os.path.join(plugin_root, "themes", "bundled", os.path.basename(archive_rel))
            ]
            archive_path = None
            for cand in candidates:
                if os.path.isfile(cand):
                    archive_path = cand
                    break
            if not archive_path:
                archive_path = candidates[0]

        target_dir = os.path.join(target_icons_dir, expected_root)

        # Check if already up to date
        marker_theme = os.path.join(target_dir, ".omarchy-cursor-switcher-theme")
        marker_sha = os.path.join(target_dir, ".omarchy-cursor-switcher-sha256")
        if os.path.isdir(target_dir) and os.path.isfile(marker_theme) and os.path.isfile(marker_sha):
            try:
                with open(marker_theme, "r", encoding="utf-8") as f:
                    curr_ver = f.read().strip()
                with open(marker_sha, "r", encoding="utf-8") as f:
                    curr_sha = f.read().strip()
                if curr_ver == str(theme_version) and curr_sha.lower() == expected_sha.lower():
                    if os.path.isfile(os.path.join(target_dir, "manifest.hl")) or os.path.isdir(os.path.join(target_dir, "cursors")):
                        results.append({"id": theme_id, "status": "up-to-date", "path": target_dir})
                        continue
            except Exception:
                pass

        res = install_single_theme_archive(
            archive_path=archive_path,
            target_dir=target_dir,
            version=theme_version,
            expected_sha=expected_sha,
            force_error=False
        )
        results.append(res)

    return {"ok": True, "installed": results}


def main():
    parser = argparse.ArgumentParser(description="Cursor Switcher Import & Bundled Theme Engine")
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

    # install-bundled
    p_bundle = subparsers.add_parser("install-bundled")
    p_bundle.add_argument("--catalog", default=None, help="Path to catalog.json")
    p_bundle.add_argument("--themes-dir", default=None, help="Path to themes directory")
    p_bundle.add_argument("--source", default=None, help="Path to source archive or directory")
    p_bundle.add_argument("--target", default=None, help="Path to target theme directory")
    p_bundle.add_argument("--target-dir", default=None, help="Path to parent icons directory")
    p_bundle.add_argument("--version", default="1.0", help="Theme version string")

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
    elif args.action == "install-bundled":
        try:
            if args.source and args.target:
                if os.path.isfile(args.source):
                    res = install_single_theme_archive(args.source, args.target, args.version, force_error=True)
                elif os.path.isdir(args.source):
                    res = install_single_theme_dir(args.source, args.target, args.version, force_error=True)
                else:
                    raise FileNotFoundError(f"Source not found: {args.source}")
                print(json.dumps({"ok": True, "theme": res}, indent=2))
                sys.exit(0)
            else:
                res = install_bundled_themes(
                    catalog_path=args.catalog,
                    themes_dir=args.themes_dir,
                    version=args.version,
                    target_icons_dir=args.target_dir
                )
                print(json.dumps(res, indent=2))
                sys.exit(0)
        except Exception as e:
            sys.stderr.write(f"install-bundled failed: {e}\n")
            print(json.dumps({"ok": False, "error": str(e)}, indent=2))
            sys.exit(1)


if __name__ == "__main__":
    main()

