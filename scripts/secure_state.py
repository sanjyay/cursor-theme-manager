#!/usr/bin/env python3
"""
Secure State & Snapshot Storage Engine for Cursor Theme Manager.
Implements descriptor-held private state directory (mode 0700), descriptor-relative
atomic replacement with fsync, O_NOFOLLOW, strict schema validation, and safe migration.
"""

import sys
import os
import stat
import json
import uuid
from typing import Dict, Any, Optional, Tuple

SUPPORTED_SIZES = [16, 20, 24, 28, 32, 40, 48, 64, 80, 96, 128, 160, 192, 224, 256]
DEFAULT_SIZE = 16
MAX_STATE_BYTES = 64 * 1024  # 64 KiB
MAX_IMPORTED_THEMES = 1024


def get_state_dir_path() -> str:
    """Returns the dedicated private state directory path."""
    state_home = os.environ.get("XDG_STATE_HOME")
    if not state_home:
        home = os.environ.get("HOME", os.path.expanduser("~"))
        state_home = os.path.join(home, ".local", "state")
    return os.path.join(state_home, "cursor-theme-manager")


def open_held_state_dir() -> Tuple[int, str]:
    """
    Creates/validates and opens the dedicated private state directory.
    Ensures directory is mode 0700, owned by current UID, and not a symlink.
    Returns (dir_fd, dir_path). The caller MUST close dir_fd when done.
    """
    dir_path = get_state_dir_path()
    uid = os.getuid()

    # Create directory securely if not existing
    try:
        os.makedirs(dir_path, mode=0o700, exist_ok=True)
    except OSError as e:
        raise OSError(f"Could not create state directory {dir_path}: {e}")

    # Verify path itself is not a symlink
    if os.path.islink(dir_path):
        raise SecurityError(f"State directory path is a symlink: {dir_path}")

    # Open directory fd with O_DIRECTORY and O_NOFOLLOW
    flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0)
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW

    dir_fd = os.open(dir_path, flags)
    try:
        st = os.fstat(dir_fd)
        if not stat.S_ISDIR(st.st_mode):
            raise SecurityError(f"State path is not a directory: {dir_path}")
        if st.st_uid != uid:
            raise SecurityError(f"State directory owned by wrong uid ({st.st_uid} != {uid}): {dir_path}")

        # Ensure mode 0700 (rwx------)
        current_mode = stat.S_IMODE(st.st_mode)
        if (current_mode & 0o077) != 0:
            try:
                os.fchmod(dir_fd, 0o700)
            except OSError:
                pass
    except Exception:
        os.close(dir_fd)
        raise

    return dir_fd, dir_path


class SecurityError(Exception):
    pass


# ==============================================================================
# STRICT STATE SCHEMA VALIDATION
# ==============================================================================

def validate_theme_object(raw: Any) -> Optional[Dict[str, str]]:
    if not isinstance(raw, dict):
        return None
    allowed_keys = {"id", "displayName", "family", "subtitle", "hyprcursor", "xcursor", "path", "previewPath", "formats", "imported", "sourceType", "license", "contentHash", "importedAt", "previewable"}
    res = {}
    for k, v in raw.items():
        if k not in allowed_keys:
            continue
        if isinstance(v, str):
            res[k] = v[:4096] if k in ("path", "previewPath") else v[:256]
        elif isinstance(v, bool):
            res[k] = v
        elif isinstance(v, list) and k == "formats":
            res[k] = [str(x)[:32] for x in v if str(x) in ("hyprcursor", "xcursor")]
    if not res.get("displayName") and not res.get("hyprcursor") and not res.get("xcursor") and not res.get("id"):
        return None
    return res


def validate_state_dict(data: Any) -> Dict[str, Any]:
    """Validates state against strict schema, returns clean dictionary."""
    fallback = {
        "version": 2,
        "theme": None,
        "size": DEFAULT_SIZE,
        "importedThemes": [],
        "integrationConsent": False,
        "integrationInstalled": False
    }
    if not isinstance(data, dict):
        return fallback

    # Check version
    ver = data.get("version")
    if ver not in (1, 2):
        return fallback

    theme = None
    if "theme" in data:
        theme = validate_theme_object(data["theme"])
    elif "manualTheme" in data:
        theme = validate_theme_object(data["manualTheme"])

    # Validate size
    size_raw = data.get("size", data.get("manualSize", DEFAULT_SIZE))
    try:
        size_int = int(size_raw)
        size = size_int if size_int in SUPPORTED_SIZES else DEFAULT_SIZE
    except (ValueError, TypeError):
        size = DEFAULT_SIZE

    # Validate importedThemes
    imported_themes = []
    raw_imported = data.get("importedThemes", [])
    if isinstance(raw_imported, list):
        for item in raw_imported[:MAX_IMPORTED_THEMES]:
            if isinstance(item, str):
                imported_themes.append(item[:256])
            elif isinstance(item, dict):
                clean_item = validate_theme_object(item)
                if clean_item:
                    imported_themes.append(clean_item)

    consent = bool(data.get("integrationConsent", False))
    installed = bool(data.get("integrationInstalled", False))

    return {
        "version": 2,
        "theme": theme,
        "size": size,
        "importedThemes": imported_themes,
        "integrationConsent": consent,
        "integrationInstalled": installed
    }


# ==============================================================================
# DESCRIPTOR-RELATIVE DURABLE READ & WRITE
# ==============================================================================

def read_state_from_fd(dir_fd: int) -> Dict[str, Any]:
    """Reads state.json relative to held dir_fd with O_NOFOLLOW and bounds checking."""
    flags = os.O_RDONLY
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW

    try:
        file_fd = os.open("state.json", flags, dir_fd=dir_fd)
    except FileNotFoundError:
        migrated = _try_legacy_migration(dir_fd)
        if migrated is not None:
            return migrated
        return validate_state_dict(None)
    except OSError as e:
        return validate_state_dict(None)

    try:
        st = os.fstat(file_fd)
        if not stat.S_ISREG(st.st_mode):
            return validate_state_dict(None)
        if st.st_size > MAX_STATE_BYTES:
            return validate_state_dict(None)
        if st.st_uid != os.getuid():
            return validate_state_dict(None)

        content = os.read(file_fd, MAX_STATE_BYTES + 1)
        if len(content) > MAX_STATE_BYTES:
            return validate_state_dict(None)

        parsed = json.loads(content.decode("utf-8", errors="strict"))
        return validate_state_dict(parsed)
    except Exception:
        return validate_state_dict(None)
    finally:
        os.close(file_fd)


def write_state_to_fd(dir_fd: int, state_dict: Dict[str, Any]) -> bool:
    """Atomically and durably writes state.json relative to held dir_fd."""
    validated = validate_state_dict(state_dict)
    data_bytes = json.dumps(validated, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"

    if len(data_bytes) > MAX_STATE_BYTES:
        raise ValueError(f"State data exceeds max size of {MAX_STATE_BYTES} bytes")

    temp_filename = f".state.tmp.{os.getpid()}_{uuid.uuid4().hex[:8]}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW

    temp_fd = os.open(temp_filename, flags, 0o600, dir_fd=dir_fd)
    try:
        # Verify created file is owned by user
        st = os.fstat(temp_fd)
        if st.st_uid != os.getuid() or not stat.S_ISREG(st.st_mode):
            raise SecurityError("Temp state file failed ownership/type validation")

        total_written = 0
        while total_written < len(data_bytes):
            written = os.write(temp_fd, data_bytes[total_written:])
            if written == 0:
                raise OSError("Write returned 0 bytes")
            total_written += written

        os.fsync(temp_fd)
    except Exception:
        os.close(temp_fd)
        try:
            os.unlink(temp_filename, dir_fd=dir_fd)
        except OSError:
            pass
        raise
    else:
        os.close(temp_fd)

    # Atomic rename relative to the SAME held parent directory fd
    try:
        os.replace(temp_filename, "state.json", src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        # fsync parent directory descriptor
        os.fsync(dir_fd)
        return True
    except Exception:
        try:
            os.unlink(temp_filename, dir_fd=dir_fd)
        except OSError:
            pass
        raise


def _try_legacy_migration(dir_fd: int) -> Optional[Dict[str, Any]]:
    """Securely checks legacy state file, validates, and migrates once if valid."""
    home = os.environ.get("HOME", os.path.expanduser("~"))
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config"))
    legacy_path = os.path.join(config_home, "omarchy", "cursor-switcher.json")

    if not os.path.exists(legacy_path):
        return None

    # Validate legacy file securely BEFORE parsing
    try:
        if os.path.islink(legacy_path):
            return None

        flags = os.O_RDONLY
        if hasattr(os, 'O_NONBLOCK'):
            flags |= os.O_NONBLOCK
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW

        fd = os.open(legacy_path, flags)
        try:
            st = os.fstat(fd)
            # Must be a regular file owned by current user and bounded in size
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_size > MAX_STATE_BYTES or st.st_size == 0:
                return None
            raw_bytes = os.read(fd, MAX_STATE_BYTES + 1)
            if len(raw_bytes) > MAX_STATE_BYTES or not raw_bytes:
                return None
            parsed = json.loads(raw_bytes.decode("utf-8", errors="strict"))
            if not isinstance(parsed, dict) or parsed.get("version") not in (1, 2):
                return None
            validated = validate_state_dict(parsed)
            # Write into new secure location
            write_state_to_fd(dir_fd, validated)
            return validated
        finally:
            os.close(fd)
    except Exception:
        return None


def read_state() -> Dict[str, Any]:
    """Convenience function to open held state directory, read state, and close."""
    dir_fd, _ = open_held_state_dir()
    try:
        return read_state_from_fd(dir_fd)
    finally:
        os.close(dir_fd)


def write_state(state_dict: Dict[str, Any]) -> bool:
    """Convenience function to open held state directory, write state, and close."""
    dir_fd, _ = open_held_state_dir()
    try:
        return write_state_to_fd(dir_fd, state_dict)
    finally:
        os.close(dir_fd)


# ==============================================================================
# SNAPSHOT READ & WRITE
# ==============================================================================

def read_snapshot_from_fd(dir_fd: int) -> Optional[Dict[str, Any]]:
    """Reads snapshot.json relative to held dir_fd with O_NOFOLLOW and validation."""
    flags = os.O_RDONLY
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW

    try:
        file_fd = os.open("snapshot.json", flags, dir_fd=dir_fd)
    except FileNotFoundError:
        # Check legacy snapshot path if any
        return _try_legacy_snapshot_migration(dir_fd)
    except OSError:
        return None

    try:
        st = os.fstat(file_fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_STATE_BYTES or st.st_uid != os.getuid():
            return None
        content = os.read(file_fd, MAX_STATE_BYTES + 1)
        if len(content) > MAX_STATE_BYTES:
            return None
        data = json.loads(content.decode("utf-8", errors="strict"))
        if isinstance(data, dict) and data.get("version") in (1, 2):
            return data
        return None
    except Exception:
        return None
    finally:
        os.close(file_fd)


def write_snapshot_to_fd(dir_fd: int, snapshot_dict: Dict[str, Any]) -> bool:
    """Atomically and durably writes snapshot.json relative to held dir_fd."""
    if not isinstance(snapshot_dict, dict) or snapshot_dict.get("version") not in (1, 2):
        raise ValueError("Invalid snapshot structure or version")

    data_bytes = json.dumps(snapshot_dict, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    if len(data_bytes) > MAX_STATE_BYTES:
        raise ValueError(f"Snapshot data exceeds max size of {MAX_STATE_BYTES} bytes")

    temp_filename = f".snapshot.tmp.{os.getpid()}_{uuid.uuid4().hex[:8]}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW

    temp_fd = os.open(temp_filename, flags, 0o600, dir_fd=dir_fd)
    try:
        st = os.fstat(temp_fd)
        if st.st_uid != os.getuid() or not stat.S_ISREG(st.st_mode):
            raise SecurityError("Temp snapshot file failed ownership/type validation")

        total_written = 0
        while total_written < len(data_bytes):
            written = os.write(temp_fd, data_bytes[total_written:])
            if written == 0:
                raise OSError("Write returned 0 bytes")
            total_written += written
        os.fsync(temp_fd)
    except Exception:
        os.close(temp_fd)
        try:
            os.unlink(temp_filename, dir_fd=dir_fd)
        except OSError:
            pass
        raise
    else:
        os.close(temp_fd)

    try:
        os.replace(temp_filename, "snapshot.json", src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        os.fsync(dir_fd)
        return True
    except Exception:
        try:
            os.unlink(temp_filename, dir_fd=dir_fd)
        except OSError:
            pass
        raise


def _try_legacy_snapshot_migration(dir_fd: int) -> Optional[Dict[str, Any]]:
    home = os.environ.get("HOME", os.path.expanduser("~"))
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config"))
    legacy_path = os.path.join(config_home, "omarchy", "cursor-switcher-original-state.json")

    if not os.path.exists(legacy_path):
        return None
    try:
        if os.path.islink(legacy_path):
            return None
        flags = os.O_RDONLY
        if hasattr(os, 'O_NONBLOCK'):
            flags |= os.O_NONBLOCK
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        fd = os.open(legacy_path, flags)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_size > MAX_STATE_BYTES:
                return None
            raw_bytes = os.read(fd, MAX_STATE_BYTES + 1)
            if len(raw_bytes) > MAX_STATE_BYTES:
                return None
            data = json.loads(raw_bytes.decode("utf-8", errors="strict"))
            if isinstance(data, dict) and data.get("version") in (1, 2):
                write_snapshot_to_fd(dir_fd, data)
                return data
            return None
        finally:
            os.close(fd)
    except Exception:
        return None


def read_snapshot() -> Optional[Dict[str, Any]]:
    dir_fd, _ = open_held_state_dir()
    try:
        return read_snapshot_from_fd(dir_fd)
    finally:
        os.close(dir_fd)


def write_snapshot(snapshot_dict: Dict[str, Any]) -> bool:
    dir_fd, _ = open_held_state_dir()
    try:
        return write_snapshot_to_fd(dir_fd, snapshot_dict)
    finally:
        os.close(dir_fd)


def delete_snapshot() -> bool:
    dir_fd, _ = open_held_state_dir()
    try:
        try:
            os.unlink("snapshot.json", dir_fd=dir_fd)
            os.fsync(dir_fd)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            return False
    finally:
        os.close(dir_fd)
