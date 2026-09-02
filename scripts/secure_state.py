#!/usr/bin/env python3
"""
Secure State Manager for Cursor Theme Manager.
Implements private, descriptor-held state storage under $XDG_STATE_HOME/cursor-theme-manager/
with strict mode 0700 permissions, atomic POSIX replacement, and schema validation.
"""

import sys
import os
import stat
import json
import uuid
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from runtime_safety import (
    sanitize_text,
    MAX_LEN_THEME_ID,
    MAX_LEN_DISPLAY_NAME,
    MAX_LEN_PATH
)

STATE_DIR_NAME = "cursor-theme-manager"
STATE_FILE_NAME = "state.json"
MAX_STATE_BYTES = 65536  # 64 KiB
DEFAULT_SIZE = 24
SUPPORTED_SIZES = [16, 20, 24, 28, 32, 40, 48, 64, 80, 96, 128, 160, 192, 224, 256]
MAX_IMPORTED_THEMES = 500


class SecurityError(Exception):
    pass


def get_state_dir_path() -> str:
    home = os.environ.get("HOME", os.path.expanduser("~"))
    state_home = os.environ.get("XDG_STATE_HOME", os.path.join(home, ".local", "state"))
    return os.path.join(state_home, STATE_DIR_NAME)


def open_held_state_dir() -> Tuple[int, str]:
    """
    Ensures the private state directory exists with mode 0700, verifies current UID
    and non-symlink status, and returns an open file descriptor held for descriptor-relative operations.
    """
    state_dir = get_state_dir_path()

    # Create directory securely if it doesn't exist
    if not os.path.exists(state_dir):
        os.makedirs(state_dir, mode=0o700, exist_ok=True)

    # Force 0700 mode on existing dir
    try:
        os.chmod(state_dir, 0o700)
    except OSError:
        pass

    # Open directory with O_DIRECTORY and O_NOFOLLOW
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW

    dir_fd = os.open(state_dir, flags)
    try:
        st = os.fstat(dir_fd)
        if not stat.S_ISDIR(st.st_mode):
            raise SecurityError(f"State path '{state_dir}' is not a directory")
        if st.st_uid != os.getuid():
            raise SecurityError(f"State directory '{state_dir}' is not owned by current user (UID {os.getuid()})")
        mode = st.st_mode & 0o777
        if mode != 0o700:
            os.fchmod(dir_fd, 0o700)
    except Exception:
        os.close(dir_fd)
        raise

    return dir_fd, state_dir


# ==============================================================================
# SCHEMA VALIDATION
# ==============================================================================

def validate_theme_object(obj: Any) -> Optional[Dict[str, Any]]:
    """Validates and bounds an individual theme descriptor."""
    if not isinstance(obj, dict):
        return None
    res = {}
    if "displayName" in obj:
        res["displayName"] = sanitize_text(obj["displayName"], MAX_LEN_DISPLAY_NAME)
    if "hyprcursor" in obj and obj["hyprcursor"] is not None:
        res["hyprcursor"] = sanitize_text(obj["hyprcursor"], MAX_LEN_THEME_ID)
    if "xcursor" in obj and obj["xcursor"] is not None:
        res["xcursor"] = sanitize_text(obj["xcursor"], MAX_LEN_THEME_ID)
    if "isImported" in obj:
        res["isImported"] = bool(obj["isImported"])
    if "path" in obj and obj["path"] is not None:
        res["path"] = sanitize_text(obj["path"], MAX_LEN_PATH)
    if "source" in obj and obj["source"] in ("system", "user", "imported"):
        res["source"] = obj["source"]
    return res



def get_trusted_icon_roots(custom_roots: Optional[List[str]] = None) -> List[str]:
    if custom_roots is not None:
        return custom_roots
    home = os.environ.get("HOME", os.path.expanduser("~"))
    data_home = os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local", "share"))
    roots = [
        os.path.join(data_home, "icons"),
        os.path.join(home, ".icons")
    ]
    sys_dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    for d in sys_dirs:
        if d.strip():
            roots.append(os.path.join(d.strip(), "icons"))
    return roots


def read_theme_inherits(theme_dir: str):
    index_theme = os.path.join(theme_dir, "index.theme")
    if not os.path.exists(index_theme):
        return []
    try:
        flags = os.O_RDONLY | os.O_NONBLOCK
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(index_theme, flags)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_size > 16384:
                return []
            content = os.read(fd, 16384).decode("utf-8", errors="ignore")
        finally:
            os.close(fd)
    except Exception:
        return []

    inherits = []
    in_section = False
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_section = (line.lower() == "[icon theme]")
            continue
        if in_section and line.lower().startswith("inherits="):
            val = line.split("=", 1)[1].strip()
            for part in val.split(","):
                part = part.strip()
                if part and re.match(r'^[a-zA-Z0-9_\-\.\ ]+$', part):
                    inherits.append(part)
    return inherits


def has_cursor_data(theme_name: str, roots: Optional[List[str]] = None) -> bool:
    if not theme_name or not re.match(r'^[a-zA-Z0-9_\-\.\ ]+$', theme_name):
        return False
    for root in (roots or get_trusted_icon_roots()):
        td = os.path.join(root, theme_name)
        if not os.path.isdir(td):
            continue
        if os.path.isfile(os.path.join(td, "manifest.hl")) or os.path.isdir(os.path.join(td, "hyprcursors")):
            return True
        cursors_dir = os.path.join(td, "cursors")
        if os.path.isdir(cursors_dir):
            try:
                if any(os.path.isfile(os.path.join(cursors_dir, f)) or os.path.islink(os.path.join(cursors_dir, f)) for f in os.listdir(cursors_dir)):
                    return True
            except OSError:
                pass
    return False


def resolve_default_cursor_theme(roots: Optional[List[str]] = None) -> Optional[str]:
    visited = set()
    queue = ["default"]
    search_roots = roots or get_trusted_icon_roots()

    while queue and len(visited) < 10:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        if current != "default" and has_cursor_data(current, roots=search_roots):
            return current

        for root in search_roots:
            td = os.path.join(root, current)
            if os.path.isdir(td):
                inherits = read_theme_inherits(td)
                for inh in inherits:
                    if inh not in visited:
                        queue.append(inh)
    return None


def validate_original_cursor(obj: Any) -> Optional[Dict[str, Any]]:
    """Validates and bounds the minimal original cursor baseline with explicit set semantics."""
    if not isinstance(obj, dict):
        return None
    captured = bool(obj.get("captured", False))
    if not captured:
        return None

    def clean_str(v, max_l=128):
        if v is None:
            return None
        s = str(v).strip()
        if not s or len(s) > max_l:
            return None
        if not re.match(r'^[a-zA-Z0-9_\-\.\ ]+$', s):
            return None
        return s

    def clean_int(v):
        if v is None:
            return None
        try:
            i = int(v)
            return i if (16 <= i <= 256) else None
        except (ValueError, TypeError):
            return None

    return {
        "captured": True,
        "hyprcursorThemeSet": bool(obj.get("hyprcursorThemeSet", False)),
        "hyprcursorTheme": clean_str(obj.get("hyprcursorTheme")),
        "hyprcursorSizeSet": bool(obj.get("hyprcursorSizeSet", False)),
        "hyprcursorSize": clean_int(obj.get("hyprcursorSize")),
        "xcursorThemeSet": bool(obj.get("xcursorThemeSet", False)),
        "xcursorTheme": clean_str(obj.get("xcursorTheme")),
        "xcursorSizeSet": bool(obj.get("xcursorSizeSet", False)),
        "xcursorSize": clean_int(obj.get("xcursorSize")),
        "gtkThemeSet": bool(obj.get("gtkThemeSet", False)),
        "gtkTheme": clean_str(obj.get("gtkTheme")),
        "gtkSizeSet": bool(obj.get("gtkSizeSet", False)),
        "gtkSize": clean_int(obj.get("gtkSize")),
        "liveRestoreBackend": clean_str(obj.get("liveRestoreBackend") or obj.get("liveBackend", "default_fallback")),
        "liveRestoreTheme": clean_str(obj.get("liveRestoreTheme") or obj.get("liveTheme")),
        "liveRestoreSize": clean_int(obj.get("liveRestoreSize") or obj.get("liveSize", 24)),
        "liveBackend": clean_str(obj.get("liveBackend") or obj.get("liveRestoreBackend", "default_fallback")),
        "liveTheme": clean_str(obj.get("liveTheme") or obj.get("liveRestoreTheme")),
        "liveSize": clean_int(obj.get("liveSize") or obj.get("liveRestoreSize", 24))
    }


def capture_original_cursor() -> Dict[str, Any]:
    """Captures current active cursor values once before CTM modifies them."""
    from runtime_safety import run_bounded

    gtk_theme_set = False
    gtk_theme = None
    res_t = run_bounded(["gsettings", "get", "org.gnome.desktop.interface", "cursor-theme"], timeout=2.0)
    if res_t.ok and res_t.stdout.strip():
        val = res_t.stdout.strip().strip("'\"")
        if val:
            gtk_theme_set = True
            gtk_theme = val

    gtk_size_set = False
    gtk_size = None
    res_s = run_bounded(["gsettings", "get", "org.gnome.desktop.interface", "cursor-size"], timeout=2.0)
    if res_s.ok and res_s.stdout.strip():
        try:
            gtk_size = int(res_s.stdout.strip())
            gtk_size_set = True
        except ValueError:
            pass

    env_hypr_theme_set = False
    env_hypr_theme = None
    env_hypr_size_set = False
    env_hypr_size = None
    env_x_theme_set = False
    env_x_theme = None
    env_x_size_set = False
    env_x_size = None

    res_env = run_bounded(["systemctl", "--user", "show-environment"], timeout=2.0)
    if res_env.ok and res_env.stdout:
        for line in res_env.stdout.splitlines():
            line = line.strip()
            if line.startswith("HYPRCURSOR_THEME="):
                v = line.split("=", 1)[1].strip()
                if v and not v.startswith("CursorSwitcher-XCursor-"):
                    env_hypr_theme_set = True
                    env_hypr_theme = v
            elif line.startswith("HYPRCURSOR_SIZE="):
                try:
                    env_hypr_size = int(line.split("=", 1)[1].strip())
                    env_hypr_size_set = True
                except ValueError:
                    pass
            elif line.startswith("XCURSOR_THEME="):
                v = line.split("=", 1)[1].strip()
                if v:
                    env_x_theme_set = True
                    env_x_theme = v
            elif line.startswith("XCURSOR_SIZE="):
                try:
                    env_x_size = int(line.split("=", 1)[1].strip())
                    env_x_size_set = True
                except ValueError:
                    pass

    # Derive concrete live restore target
    live_backend = "default_fallback"
    live_theme = None
    live_size = 24

    if env_hypr_theme_set and env_hypr_theme and has_cursor_data(env_hypr_theme):
        live_backend = "hyprcursor"
        live_theme = env_hypr_theme
        live_size = env_hypr_size or env_x_size or gtk_size or 24
    elif env_x_theme_set and env_x_theme and has_cursor_data(env_x_theme):
        live_backend = "xcursor"
        live_theme = env_x_theme
        live_size = env_x_size or gtk_size or env_hypr_size or 24
    elif gtk_theme_set and gtk_theme and gtk_theme != "default" and has_cursor_data(gtk_theme):
        live_backend = "gtk"
        live_theme = gtk_theme
        live_size = gtk_size or env_x_size or env_hypr_size or 24
    else:
        live_backend = "default_fallback"
        live_theme = resolve_default_cursor_theme()
        live_size = gtk_size or env_x_size or env_hypr_size or 24

    return {
        "captured": True,
        "hyprcursorThemeSet": env_hypr_theme_set,
        "hyprcursorTheme": env_hypr_theme,
        "hyprcursorSizeSet": env_hypr_size_set,
        "hyprcursorSize": env_hypr_size,
        "xcursorThemeSet": env_x_theme_set,
        "xcursorTheme": env_x_theme,
        "xcursorSizeSet": env_x_size_set,
        "xcursorSize": env_x_size,
        "gtkThemeSet": gtk_theme_set,
        "gtkTheme": gtk_theme,
        "gtkSizeSet": gtk_size_set,
        "gtkSize": gtk_size,
        "liveRestoreBackend": live_backend,
        "liveRestoreTheme": live_theme,
        "liveRestoreSize": live_size,
        "liveBackend": live_backend,
        "liveTheme": live_theme,
        "liveSize": live_size
    }


def ensure_original_baseline() -> bool:
    """Ensures that original baseline cursor values are captured once in state."""
    st = read_state()
    existing = st.get("preCtmCursor") or st.get("originalCursor")
    if existing and existing.get("captured"):
        return True
    baseline = capture_original_cursor()
    st["preCtmCursor"] = baseline
    st["originalCursor"] = baseline
    return write_state(st)


def validate_state_dict(data: Any) -> Dict[str, Any]:
    """Validates state against strict schema, returns clean dictionary."""
    fallback = {
        "version": 2,
        "theme": None,
        "size": DEFAULT_SIZE,
        "importedThemes": [],
        "integrationPromptSeen": False,
        "integrationEnabled": False,
        "launcherPromptSeen": False,
        "launcherAdded": False,
        "originalCursor": None
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

    # Integration preferences (with backward-compatibility migration)
    prompt_seen = bool(data.get("integrationPromptSeen", data.get("launcherPromptSeen", data.get("integrationConsent", False))))
    enabled = bool(data.get("integrationEnabled", data.get("launcherAdded", data.get("integrationInstalled", False))))

    orig_cursor = validate_original_cursor(data.get("preCtmCursor") or data.get("originalCursor"))
    cursor_modified = bool(data.get("cursorModifiedByCtm", False))

    return {
        "version": 2,
        "theme": theme,
        "size": size,
        "importedThemes": imported_themes,
        "integrationPromptSeen": prompt_seen,
        "integrationEnabled": enabled,
        "launcherPromptSeen": prompt_seen,
        "launcherAdded": enabled,
        "cursorModifiedByCtm": cursor_modified,
        "preCtmCursor": orig_cursor,
        "originalCursor": orig_cursor
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
        # If state.json missing, attempt secure legacy migration
        migrated = _try_legacy_migration(dir_fd)
        if migrated is not None:
            return migrated
        return validate_state_dict(None)
    except OSError:
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
    """
    Atomically and durably writes state.json relative to held dir_fd.
    Validates schema before writing, preserves immutable baseline and cursorModifiedByCtm,
    and syncs both file and directory.
    """
    existing = read_state_from_fd(dir_fd)
    clean_dict = validate_state_dict(state_dict)

    # Invariant: If existing state has a captured preCtmCursor, preserve it!
    existing_baseline = existing.get("preCtmCursor") or existing.get("originalCursor")
    if existing_baseline and existing_baseline.get("captured"):
        clean_dict["preCtmCursor"] = existing_baseline
        clean_dict["originalCursor"] = existing_baseline

    # Invariant: If cursor was ever modified by CTM, preserve the flag!
    if existing.get("cursorModifiedByCtm") or (state_dict and state_dict.get("cursorModifiedByCtm")):
        clean_dict["cursorModifiedByCtm"] = True
    else:
        clean_dict["cursorModifiedByCtm"] = bool(clean_dict.get("cursorModifiedByCtm", False))
    data_bytes = json.dumps(clean_dict, indent=2, ensure_ascii=False).encode("utf-8") + b"\n" 

    if len(data_bytes) > MAX_STATE_BYTES:
        raise ValueError(f"State payload exceeds maximum size of {MAX_STATE_BYTES} bytes")

    temp_filename = f".state.tmp.{os.getpid()}_{uuid.uuid4().hex[:8]}"

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW

    temp_fd = os.open(temp_filename, flags, 0o600, dir_fd=dir_fd)
    try:
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

    try:
        os.replace(temp_filename, "state.json", src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
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
            try:
                os.unlink(legacy_path)
            except OSError:
                pass
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
