#!/usr/bin/python3
"""
Secure Import and Management Engine for Cursor Theme Manager.
Imports local cursor theme directories or safe archives chosen by the user into ~/.local/share/icons.
All external tool execution is supervised via runtime_safety.run_bounded.
"""

import sys
import os
import re
import stat
import json
import shutil
import tarfile
import zipfile
import hashlib
import tempfile
import argparse
import secrets
from datetime import datetime, timezone
from pathlib import Path

# Add script dir to path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from runtime_safety import (
    run_bounded, sanitize_text, emit_bounded_json,
    TIMEOUT_CONVERT, TIMEOUT_IMPORT, LIMIT_STDOUT_MEDIUM, LIMIT_STDERR_DEFAULT,
    MAX_LEN_DISPLAY_NAME, MAX_LEN_THEME_ID, MAX_LEN_PATH, MAX_LEN_LICENSE
)
import secure_state

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

IMPORTED_ID_RE = re.compile(r"^CursorSwitcher-Imported-[A-Za-z0-9_-]{1,220}$")


def read_managed_import_marker(path: str, expected_id: str = ""):
    """Read a bounded, no-follow import marker and verify its management identity."""
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_size > 65536:
                return None
            raw = os.read(fd, 65537)
            if len(raw) > 65536:
                return None
            meta = json.loads(raw.decode("utf-8", errors="strict"))
        finally:
            os.close(fd)
        if not isinstance(meta, dict) or meta.get("kind") != "imported-user-theme":
            return None
        marker_id = meta.get("id")
        if not isinstance(marker_id, str) or not IMPORTED_ID_RE.fullmatch(marker_id):
            return None
        if expected_id and marker_id != expected_id:
            return None
        return meta
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        return None


def read_managed_text_marker(path: str, required: str):
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_size > 4096:
                return None
            text = os.read(fd, 4097).decode("utf-8", errors="strict")
            return text if len(text.encode("utf-8")) <= 4096 and required in text else None
        finally:
            os.close(fd)
    except (OSError, UnicodeError):
        return None


def safe_read_text_file(filepath: str, max_bytes: int = 65536) -> str | None:
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(filepath, flags)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_size > max_bytes:
                return None
            raw = os.read(fd, max_bytes + 1)
            if len(raw) > max_bytes:
                return None
            return raw.decode("utf-8", errors="ignore")
        finally:
            os.close(fd)
    except Exception:
        return None


def safe_write_text_file(filepath: str, content: str) -> bool:
    """Safely writes a regular text file without following symlinks, using atomic descriptor-relative replacement."""
    try:
        parent = os.path.dirname(filepath)
        fname = os.path.basename(filepath)
        if not parent or not fname or "/" in fname or "\\" in fname:
            return False
        if not os.path.isdir(parent) or os.path.islink(parent):
            return False
        if os.path.islink(filepath):
            return False
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        dir_fd = os.open(parent, flags)
    except Exception:
        return False

    tmp_name = None
    try:
        st = os.fstat(dir_fd)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or (st.st_mode & 0o022):
            return False
        tmp_name = f".tmp-{fname}-{secrets.token_hex(6)}"
        tmp_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            tmp_flags |= os.O_NOFOLLOW
        tmp_fd = os.open(tmp_name, tmp_flags, 0o644, dir_fd=dir_fd)
        try:
            data = content.encode("utf-8")
            total_written = 0
            while total_written < len(data):
                w = os.write(tmp_fd, data[total_written:])
                if w <= 0:
                    raise OSError("write failed")
                total_written += w
            os.fsync(tmp_fd)
        finally:
            os.close(tmp_fd)

        try:
            dst_st = os.stat(fname, dir_fd=dir_fd, follow_symlinks=False)
            if not stat.S_ISREG(dst_st.st_mode) or dst_st.st_uid != os.getuid():
                return False
        except FileNotFoundError:
            pass

        os.replace(tmp_name, fname, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        tmp_name = None
        os.fsync(dir_fd)
        return True
    except Exception:
        return False
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name, dir_fd=dir_fd)
            except OSError:
                pass
        try:
            os.close(dir_fd)
        except OSError:
            pass


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
    try:
        for fname in os.listdir(theme_dir):
            if re.match(r'^(license|copying|copyright)(\.[a-z0-9]+)?$', fname, re.IGNORECASE):
                fpath = os.path.join(theme_dir, fname)
                txt = safe_read_text_file(fpath, max_bytes=8192)
                if txt:
                    detected = detect_license_text(txt)
                    if detected != "Unknown":
                        return detected
    except Exception:
        pass
    return "Unknown"


IGNORED_HASH_FILES = {
    ".cursor-theme-manager-imported",
    ".omarchy-cursor-switcher-imported",
    ".cursor-theme-manager-generated",
    ".omarchy-cursor-switcher-converted",
}


def compute_content_hash(theme_root: str) -> str:
    hasher = hashlib.sha256()
    cursor_files = []
    for root, _, files in os.walk(theme_root):
        for f in files:
            if f in IGNORED_HASH_FILES:
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, theme_root)
            cursor_files.append((rel, full))
    cursor_files.sort()
    for rel, full in cursor_files:
        hasher.update(rel.encode("utf-8"))
        try:
            st = os.lstat(full)
            if stat.S_ISLNK(st.st_mode):
                hasher.update(b"symlink:" + os.readlink(full).encode("utf-8", errors="ignore"))
            elif stat.S_ISREG(st.st_mode):
                with open(full, "rb") as f:
                    while chunk := f.read(65536):
                        hasher.update(chunk)
        except Exception:
            pass
    return hasher.hexdigest()


def compute_legacy_content_hash(theme_root: str) -> str:
    """Computes the legacy content hash used prior to commit 5e321a4 (followed symlinks to read bytes)."""
    hasher = hashlib.sha256()
    cursor_files = []
    for root, _, files in os.walk(theme_root):
        for f in files:
            if f in IGNORED_HASH_FILES:
                continue
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
                    except OSError:
                        continue
                    if header == b"\x7fELF":
                        raise ValueError(f"Forbidden ELF executable binary in theme: {name}")


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
                unix_mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(unix_mode):
                    raise ValueError(f"Symbolic links are forbidden in ZIP archives: {info.filename}")
                if info.flag_bits & 0x1:
                    raise ValueError(f"Encrypted ZIP entries are unsupported: {info.filename}")
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
                    resolved_link = os.path.normpath(os.path.join(os.path.dirname(m.name), m.linkname))
                    if not is_safe_relpath(resolved_link):
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
            if not hasattr(tarfile, 'data_filter'):
                raise ValueError("This Python version lacks safe TAR extraction support")
            tf.extractall(stage_dir, filter='data')
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
        m_path = os.path.join(theme_root, "manifest.hl")
        raw = safe_read_text_file(m_path, max_bytes=65536)
        if raw and not declared_name:
            for line in raw.splitlines():
                m = re.match(r'^\s*name\s*=\s*([^\n\r]+)', line)
                if m and not declared_name:
                    declared_name = m.group(1).strip().strip('"\'')
                    break

    if has_xcursors:
        formats.append("xcursor")
        cursor_files = os.listdir(os.path.join(theme_root, "cursors"))
        if not cursor_files:
            raise ValueError("The cursors/ directory is empty; no cursor images found.")
        index_theme = os.path.join(theme_root, "index.theme")
        if not declared_name:
            raw = safe_read_text_file(index_theme, max_bytes=65536)
            if raw:
                for line in raw.splitlines():
                    m = re.match(r'^\s*Name\s*=\s*([^\n\r]+)', line)
                    if m:
                        declared_name = m.group(1).strip()
                        break

    if not declared_name:
        declared_name = os.path.basename(theme_root)

    license_name = scan_license_in_dir(theme_root)

    return {
        "declared_name": sanitize_text(declared_name, max_len=MAX_LEN_DISPLAY_NAME),
        "formats": formats,
        "license": sanitize_text(license_name, max_len=MAX_LEN_LICENSE)
    }


def copy_theme_atomically(src_dir: str, dst_dir: str):
    parent = os.path.dirname(dst_dir)
    os.makedirs(parent, exist_ok=True)
    temp_dst = tempfile.mkdtemp(prefix=".install-", dir=parent)
    try:
        shutil.copytree(src_dir, temp_dst, dirs_exist_ok=True, symlinks=True)
        if os.path.lexists(dst_dir):
            raise ValueError(f"Refusing to replace existing theme directory: {dst_dir}")
        os.rename(temp_dst, dst_dir)
    finally:
        if os.path.exists(temp_dst):
            shutil.rmtree(temp_dst, ignore_errors=True)


def check_existing_hash(icons_dir: str, content_hash: str, legacy_hash: str = ""):
    """Checks if an imported theme with the same content hash already exists."""
    if not os.path.isdir(icons_dir):
        return None
    short_hash = content_hash[:12] if content_hash else ""
    legacy_short = legacy_hash[:12] if legacy_hash else ""
    for entry in os.listdir(icons_dir):
        full = os.path.join(icons_dir, entry)
        if os.path.isdir(full) and not os.path.islink(full) and IMPORTED_ID_RE.fullmatch(entry):
            marker1 = os.path.join(full, ".omarchy-cursor-switcher-imported")
            marker2 = os.path.join(full, ".cursor-theme-manager-imported")
            meta = read_managed_import_marker(marker1, entry) or read_managed_import_marker(marker2, entry)
            if meta:
                stored = meta.get("contentHash")
                if stored and (stored == content_hash or (legacy_hash and stored == legacy_hash)):
                    return meta
                if (short_hash and entry.endswith(f"-{short_hash}")) or (legacy_short and entry.endswith(f"-{legacy_short}")):
                    return meta
                try:
                    disk_hash = compute_content_hash(full)
                    if disk_hash == content_hash or (legacy_hash and disk_hash == legacy_hash):
                        return meta
                    disk_legacy = compute_legacy_content_hash(full)
                    if (disk_legacy and disk_legacy == content_hash) or (legacy_hash and disk_legacy == legacy_hash):
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

    try:
        real_source = os.path.realpath(source_path)
        real_icons = os.path.realpath(icons_dir)
        if real_source == real_icons or real_source.startswith(real_icons + os.sep):
            rel = os.path.relpath(real_source, real_icons)
            entry = rel.split(os.sep)[0]
            cand = os.path.join(real_icons, entry)
            if IMPORTED_ID_RE.fullmatch(entry) and os.path.isdir(cand) and not os.path.islink(cand):
                m1 = os.path.join(cand, ".cursor-theme-manager-imported")
                m2 = os.path.join(cand, ".omarchy-cursor-switcher-imported")
                existing_meta = read_managed_import_marker(m1, entry) or read_managed_import_marker(m2, entry)
                if existing_meta:
                    return {
                        "ok": True,
                        "alreadyImported": True,
                        "theme": existing_meta
                    }
    except Exception:
        pass

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
        legacy_hash = compute_legacy_content_hash(theme_root)

        existing = check_existing_hash(icons_dir, content_hash, legacy_hash)
        if existing:
            if existing.get("contentHash") != content_hash:
                try:
                    existing_path = existing.get("path") or os.path.join(icons_dir, existing["id"])
                    if os.path.isdir(existing_path) and not os.path.islink(existing_path):
                        existing["contentHash"] = content_hash
                        m1 = os.path.join(existing_path, ".cursor-theme-manager-imported")
                        m2 = os.path.join(existing_path, ".omarchy-cursor-switcher-imported")
                        for m in (m1, m2):
                            safe_write_text_file(m, json.dumps(existing, indent=2))
                except Exception:
                    pass
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
            "contentHash": content_hash,
            "importedAt": datetime.now(timezone.utc).isoformat(),
            "formats": meta["formats"],
            "xcursor": internal_id if "xcursor" in meta["formats"] else "",
            "hyprcursor": internal_id if "hyprcursor" in meta["formats"] else "",
            "path": install_path,
            "license": meta["license"],
            "subtitle": meta["license"] if meta["license"] and meta["license"] != "Unknown" else ""
        }

        marker_file = os.path.join(install_path, ".cursor-theme-manager-imported")
        legacy_marker = os.path.join(install_path, ".omarchy-cursor-switcher-imported")
        theme_record["version"] = 1
        theme_record["kind"] = "imported-user-theme"

        if "xcursor" in meta["formats"] and "hyprcursor" not in meta["formats"]:
            cursorctl_bin = os.path.join(script_dir or os.path.dirname(__file__), "cursorctl")
            if os.path.isfile(cursorctl_bin):
                try:
                    res = run_bounded([
                        cursorctl_bin, "ensure-hyprcursor",
                        "--xcursor", internal_id,
                        "--theme-path", install_path
                    ], timeout=TIMEOUT_CONVERT, stdout_limit=LIMIT_STDOUT_MEDIUM, stderr_limit=LIMIT_STDERR_DEFAULT)
                    if res.ok:
                        out = res.stdout.strip()
                        if out:
                            theme_record["hyprcursor"] = out
                            theme_record["runtimeTheme"] = out
                            theme_record["runtimePrepared"] = True
                            if "hyprcursor" not in theme_record["formats"]:
                                theme_record["formats"].append("hyprcursor")
                except Exception as e:
                    sys.stderr.write(f"Conversion note: {e}\n")

        marker_text = json.dumps(theme_record, indent=2)
        safe_write_text_file(marker_file, marker_text)
        safe_write_text_file(legacy_marker, marker_text)

        return {
            "ok": True,
            "alreadyImported": False,
            "theme": theme_record
        }

    except Exception as e:
        return {"ok": False, "error": sanitize_text(str(e), max_len=256)}
    finally:
        if os.path.exists(stage_temp):
            shutil.rmtree(stage_temp, ignore_errors=True)


def run_remove(theme_id: str):
    if not theme_id:
        return {"ok": False, "error": "Missing theme ID"}

    if not IMPORTED_ID_RE.fullmatch(theme_id):
        return {"ok": False, "error": "Refusing to remove theme: not a valid imported theme ID"}

    home = os.environ.get("HOME", "")
    data_home = os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local/share"))
    icons_dir = os.path.join(data_home, "icons")
    target = os.path.join(icons_dir, theme_id)

    if not os.path.isdir(target) or os.path.islink(target):
        return {"ok": False, "error": f"Imported theme directory not found: {target}"}

    marker1 = os.path.join(target, ".cursor-theme-manager-imported")
    meta = read_managed_import_marker(marker1, theme_id) or read_managed_import_marker(marker2, theme_id)
    if not meta:
        return {"ok": False, "error": f"Directory is not managed by Cursor Theme Manager import: {target}"}

    content_hash = meta.get("contentHash")
    display_name = meta.get("displayName")

    shutil.rmtree(target)

    # Clean up any positively identified managed duplicate imports with identical hash or display name
    for entry in os.listdir(icons_dir):
        if entry == theme_id:
            continue
        full = os.path.join(icons_dir, entry)
        if not os.path.isdir(full) or os.path.islink(full) or not IMPORTED_ID_RE.fullmatch(entry):
            continue
        m1 = os.path.join(full, ".cursor-theme-manager-imported")
        m2 = os.path.join(full, ".omarchy-cursor-switcher-imported")
        other_meta = read_managed_import_marker(m1, entry) or read_managed_import_marker(m2, entry)
        if other_meta:
            is_dup = False
            if content_hash and other_meta.get("contentHash") == content_hash:
                is_dup = True
            elif display_name and other_meta.get("displayName") == display_name:
                is_dup = True
            if is_dup:
                shutil.rmtree(full, ignore_errors=True)
                for sub in os.listdir(icons_dir):
                    sub_full = os.path.join(icons_dir, sub)
                    if not os.path.isdir(sub_full) or os.path.islink(sub_full):
                        continue
                    if sub.startswith(f"CursorSwitcher-XCursor-{entry}") or sub.startswith(f"CursorSwitcher-Themed-{entry}"):
                        shutil.rmtree(sub_full, ignore_errors=True)

    for entry in os.listdir(icons_dir):
        full = os.path.join(icons_dir, entry)
        if not os.path.isdir(full) or os.path.islink(full):
            continue
        gen_marker = os.path.join(full, ".cursor-theme-manager-generated")
        conv_marker = os.path.join(full, ".omarchy-cursor-switcher-converted")
        gen_text = read_managed_text_marker(gen_marker, "kind=conversion-cache")
        legacy_text = read_managed_text_marker(conv_marker, "1.0")
        if gen_text or legacy_text:
            if (
                entry.startswith(f"CursorSwitcher-XCursor-{theme_id}") or
                entry.startswith(f"CursorSwitcher-Themed-{theme_id}")
            ):
                shutil.rmtree(full, ignore_errors=True)
            elif gen_text and f"sourceTheme={theme_id}" in gen_text:
                shutil.rmtree(full, ignore_errors=True)

    cache_home = os.environ.get("XDG_CACHE_HOME", os.path.join(home, ".cache"))
    theme_cache = os.path.join(cache_home, "omarchy", "cursor-previews", theme_id)
    if os.path.isdir(theme_cache):
        shutil.rmtree(theme_cache, ignore_errors=True)

    return {"ok": True, "removed": theme_id}


def run_rename(theme_id: str, new_name: str):
    if not theme_id or not new_name:
        return {"ok": False, "error": "Missing theme ID or new name"}

    clean_name = sanitize_text(new_name, max_len=100)
    if not clean_name:
        return {"ok": False, "error": "Invalid theme name"}

    if not IMPORTED_ID_RE.fullmatch(theme_id):
        return {"ok": False, "error": "Refusing to rename theme: not a valid imported theme ID"}

    home = os.environ.get("HOME", "")
    data_home = os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local/share"))
    icons_dir = os.path.join(data_home, "icons")
    target = os.path.join(icons_dir, theme_id)

    if not os.path.isdir(target) or os.path.islink(target):
        return {"ok": False, "error": f"Imported theme directory not found: {target}"}

    marker1 = os.path.join(target, ".cursor-theme-manager-imported")
    marker2 = os.path.join(target, ".omarchy-cursor-switcher-imported")
    meta = read_managed_import_marker(marker1, theme_id) or read_managed_import_marker(marker2, theme_id)
    if not meta:
        return {"ok": False, "error": f"Directory is not managed by Cursor Theme Manager import: {target}"}

    try:
        meta["displayName"] = clean_name
        marker_data = json.dumps(meta, indent=2)
        safe_write_text_file(marker1, marker_data)
        safe_write_text_file(marker2, marker_data)
    except Exception as e:
        return {"ok": False, "error": f"Failed to update metadata marker: {e}"}

    idx_path = os.path.join(target, "index.theme")
    idx_content = safe_read_text_file(idx_path, max_bytes=65536)
    if idx_content is not None:
        try:
            lines = []
            found = False
            for line in idx_content.splitlines(keepends=True):
                if line.strip().startswith("Name="):
                    lines.append(f"Name={clean_name}\n")
                    found = True
                else:
                    lines.append(line)
            if not found:
                lines.insert(0, f"Name={clean_name}\n")
            safe_write_text_file(idx_path, "".join(lines))
        except Exception as e:
            return {"ok": False, "error": f"Failed to update index.theme: {e}"}

    for mname in ["manifest.hl", "manifest.toml"]:
        mpath = os.path.join(target, mname)
        mcontent = safe_read_text_file(mpath, max_bytes=65536)
        if mcontent is not None:
            try:
                lines = []
                found = False
                for line in mcontent.splitlines(keepends=True):
                    if line.strip().startswith("name =") or line.strip().startswith("name="):
                        lines.append(f"name = {clean_name}\n")
                        found = True
                    else:
                        lines.append(line)
                if not found:
                    lines.insert(0, f"name = {clean_name}\n")
                safe_write_text_file(mpath, "".join(lines))
            except Exception:
                pass

    # Update secure state if currently active theme is this theme
    try:
        st = secure_state.read_state()
        if st.get("theme") and isinstance(st["theme"], dict) and st["theme"].get("id") == theme_id:
            st["theme"]["displayName"] = clean_name
            secure_state.write_state(st)
    except Exception:
        pass

    return {
        "ok": True,
        "id": theme_id,
        "displayName": clean_name
    }


def main():
    parser = argparse.ArgumentParser(description="Cursor Switcher User Theme Import & Management Engine")
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
        emit_bounded_json(result, max_bytes=LIMIT_STDOUT_MEDIUM, exit_code=0 if result.get("ok") else 1)
    elif args.action == "remove":
        result = run_remove(args.id)
        emit_bounded_json(result, max_bytes=LIMIT_STDOUT_MEDIUM, exit_code=0 if result.get("ok") else 1)
    elif args.action == "rename":
        result = run_rename(args.id, args.name)
        emit_bounded_json(result, max_bytes=LIMIT_STDOUT_MEDIUM, exit_code=0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
