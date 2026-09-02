#!/usr/bin/python3
"""
Integration Manager for Cursor Theme Manager.
Handles transactional installation and removal of:
1. Application Launcher: ~/.local/share/applications/cursor-theme-manager.desktop
2. Cleanup Helper: ~/.local/libexec/cursor-theme-manager/cleanup
3. Systemd Watcher Path: ~/.config/systemd/user/cursor-theme-manager-cleanup.path
4. Systemd Cleanup Service: ~/.config/systemd/user/cursor-theme-manager-cleanup.service

Includes all-or-nothing transactional installation with rollback,
descriptor-based marker validation, and non-nagging state tracking.
"""

import sys
import os
import stat
import json
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from runtime_safety import (
    run_bounded, resolve_system_executable, sanitize_text, emit_bounded_json,
    TIMEOUT_INTEGRATION
)
import secure_state

PLUGIN_ID = "sanjyay.cursor-theme-manager"
OWNERSHIP_MARKER = "X-CursorThemeManager-Owned=true"

DESKTOP_ENTRY_CONTENT = f"""[Desktop Entry]
Type=Application
Name=Cursor Theme Manager
GenericName=Cursor Theme
Comment=Preview and manage cursor themes
Exec=omarchy-shell shell toggle {PLUGIN_ID}
Icon=input-mouse
Terminal=false
Categories=Settings;DesktopSettings;
Keywords=cursor;theme;mouse;pointer;hyprcursor;xcursor;
{OWNERSHIP_MARKER}
"""

PATH_UNIT_CONTENT = """[Unit]
Description=Watch for Cursor Theme Manager removal

[Path]
PathChanged=%h/.config/omarchy/plugins
Unit=cursor-theme-manager-cleanup.service

[Install]
WantedBy=default.target
"""

SERVICE_UNIT_CONTENT = """[Unit]
Description=Cursor Theme Manager removal cleanup

[Service]
Type=oneshot
ExecStart=%h/.local/libexec/cursor-theme-manager/cleanup
"""


def get_paths() -> Dict[str, str]:
    home = os.environ.get("HOME", os.path.expanduser("~"))
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config"))
    data_home = os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local", "share"))

    return {
        "desktop": os.path.join(data_home, "applications", "cursor-theme-manager.desktop"),
        "libexec_dir": os.path.join(home, ".local", "libexec", "cursor-theme-manager"),
        "cleanup": os.path.join(home, ".local", "libexec", "cursor-theme-manager", "cleanup"),
        "systemd_user": os.path.join(config_home, "systemd", "user"),
        "path_unit": os.path.join(config_home, "systemd", "user", "cursor-theme-manager-cleanup.path"),
        "service_unit": os.path.join(config_home, "systemd", "user", "cursor-theme-manager-cleanup.service")
    }


def is_file_owned_by_us(filepath: str) -> bool:
    if not os.path.exists(filepath):
        return False
    try:
        flags = os.O_RDONLY | os.O_NONBLOCK
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(filepath, flags)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_size > 8192:
                return False
            content = os.read(fd, 8192).decode("utf-8", errors="ignore")
            return (OWNERSHIP_MARKER in content) and (PLUGIN_ID in content)
        finally:
            os.close(fd)
    except Exception:
        return False


def get_status() -> Dict[str, Any]:
    paths = get_paths()
    desktop_exists = os.path.isfile(paths["desktop"]) and is_file_owned_by_us(paths["desktop"])
    cleanup_exists = os.path.isfile(paths["cleanup"])
    path_unit_exists = os.path.isfile(paths["path_unit"])
    service_unit_exists = os.path.isfile(paths["service_unit"])

    all_artifacts = desktop_exists and cleanup_exists and path_unit_exists and service_unit_exists

    st = secure_state.read_state()
    state_enabled = bool(st.get("integrationEnabled", st.get("launcherAdded", False)))
    effective_enabled = all_artifacts and state_enabled
    # Prompt is persistently seen ONLY if integration is actually enabled; otherwise setup is required
    prompt_seen = effective_enabled

    return {
        "ok": True,
        "enabled": effective_enabled,
        "promptSeen": prompt_seen,
        "stateEnabled": state_enabled,
        "artifacts": {
            "desktop": desktop_exists,
            "cleanup": cleanup_exists,
            "pathUnit": path_unit_exists,
            "serviceUnit": service_unit_exists
        },
        "paths": paths
    }


def dismiss_prompt() -> Dict[str, Any]:
    # In-memory / session-only dismissal — never write durable files solely for prompt dismissal
    return {"ok": True, "promptSeen": False}


def enable_integration() -> Dict[str, Any]:
    """
    Transactionally installs all integration artifacts.
    If any step fails, rolls back all installed files.
    """
    paths = get_paths()
    desktop_file = paths["desktop"]
    libexec_dir = paths["libexec_dir"]
    cleanup_file = paths["cleanup"]
    systemd_user = paths["systemd_user"]
    path_unit = paths["path_unit"]
    service_unit = paths["service_unit"]

    # 1. Validation phase: check collision with foreign unowned files
    if os.path.exists(desktop_file):
        if not is_file_owned_by_us(desktop_file):
            return {
                "ok": False,
                "error": f"An existing application entry uses this filename and was not created by Cursor Theme Manager ({desktop_file})."
            }

    # Ensure parent directories exist
    os.makedirs(os.path.dirname(desktop_file), exist_ok=True)
    os.makedirs(libexec_dir, exist_ok=True)
    os.makedirs(systemd_user, exist_ok=True)

    cleanup_helper_source = SCRIPT_DIR / "cleanup_helper.py"
    if not cleanup_helper_source.is_file():
        return {"ok": False, "error": "Missing cleanup_helper.py in scripts directory."}
    cleanup_content = cleanup_helper_source.read_text(encoding="utf-8")

    # 2. Staging phase: write all files to temporary names
    pid = os.getpid()
    staged_files: List[Tuple[str, str, int]] = []
    # (tmp_path, final_path, mode)

    desktop_tmp = f"{desktop_file}.tmp.{pid}"
    cleanup_tmp = f"{cleanup_file}.tmp.{pid}"
    path_tmp = f"{path_unit}.tmp.{pid}"
    service_tmp = f"{service_unit}.tmp.{pid}"

    tmp_manifest = [
        (desktop_tmp, desktop_file, DESKTOP_ENTRY_CONTENT, 0o644),
        (cleanup_tmp, cleanup_file, cleanup_content, 0o755),
        (path_tmp, path_unit, PATH_UNIT_CONTENT, 0o644),
        (service_tmp, service_unit, SERVICE_UNIT_CONTENT, 0o644)
    ]

    installed_targets: List[str] = []

    try:
        # Write and fsync each temporary file with descriptor-held permissions
        for tmp_path, final_path, content, mode in tmp_manifest:
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            fd = os.open(tmp_path, flags, mode)
            try:
                os.fchmod(fd, mode)
                with open(fd, "w", encoding="utf-8", closefd=False) as f:
                    f.write(content)
                    f.flush()
                    os.fsync(fd)
            finally:
                os.close(fd)
            staged_files.append((tmp_path, final_path, mode))

        # 3. Commit phase: atomic replacement
        for tmp_path, final_path, _ in staged_files:
            os.replace(tmp_path, final_path)
            installed_targets.append(final_path)

        # 4. Systemd activation phase
        reload_res = run_bounded(["systemctl", "--user", "daemon-reload"], timeout=TIMEOUT_INTEGRATION)
        if not reload_res.ok:
            raise RuntimeError(f"systemctl daemon-reload failed: {reload_res.error}")

        enable_res = run_bounded(["systemctl", "--user", "enable", "--now", "cursor-theme-manager-cleanup.path"], timeout=TIMEOUT_INTEGRATION)
        if not enable_res.ok:
            raise RuntimeError(f"systemctl enable --now cleanup.path failed: {enable_res.error}")

        # Update desktop database best-effort
        if resolve_system_executable("update-desktop-database"):
            run_bounded(["update-desktop-database", "-q", os.path.dirname(desktop_file)], timeout=2.0)

        # 5. State update
        st = secure_state.read_state()
        st["integrationEnabled"] = True
        st["integrationPromptSeen"] = True
        st["launcherAdded"] = True
        st["launcherPromptSeen"] = True
        secure_state.write_state(st)

        return {"ok": True, "enabled": True, "paths": paths}

    except Exception as e:
        # Transactional Rollback: clean up all temporary and installed files
        for tmp_path, _, _, _ in tmp_manifest:
            if os.path.exists(tmp_path):
                try: os.unlink(tmp_path)
                except OSError: pass

        for target in installed_targets:
            if os.path.exists(target):
                try: os.unlink(target)
                except OSError: pass
        if os.path.isdir(libexec_dir):
            try: os.rmdir(libexec_dir)
            except OSError: pass

        run_bounded(["systemctl", "--user", "daemon-reload"], timeout=2.0)
        return {"ok": False, "error": f"Integration installation failed and was rolled back: {e}"}


def disable_integration() -> Dict[str, Any]:
    """
    Idempotently removes all integration artifacts and disables systemd units.
    """
    paths = get_paths()
    desktop_file = paths["desktop"]
    libexec_dir = paths["libexec_dir"]
    cleanup_file = paths["cleanup"]
    path_unit = paths["path_unit"]
    service_unit = paths["service_unit"]

    # Stop and disable systemd path unit
    run_bounded(["systemctl", "--user", "stop", "cursor-theme-manager-cleanup.path"], timeout=2.0)
    run_bounded(["systemctl", "--user", "disable", "cursor-theme-manager-cleanup.path"], timeout=2.0)

    # Remove units
    if os.path.exists(path_unit):
        try: os.unlink(path_unit)
        except OSError: pass

    if os.path.exists(service_unit):
        try: os.unlink(service_unit)
        except OSError: pass

    run_bounded(["systemctl", "--user", "daemon-reload"], timeout=2.0)

    # Remove cleanup helper
    if os.path.exists(cleanup_file):
        try: os.unlink(cleanup_file)
        except OSError: pass
    if os.path.isdir(libexec_dir):
        try: os.rmdir(libexec_dir)
        except OSError: pass

    # Remove desktop file if owned by us
    if os.path.exists(desktop_file):
        if is_file_owned_by_us(desktop_file):
            try:
                os.unlink(desktop_file)
                if resolve_system_executable("update-desktop-database"):
                    run_bounded(["update-desktop-database", "-q", os.path.dirname(desktop_file)], timeout=2.0)
            except OSError:
                pass
        else:
            return {
                "ok": False,
                "error": f"Refusing to remove desktop entry: not owned by Cursor Theme Manager ({desktop_file})."
            }

    # Update state
    st = secure_state.read_state()
    st["integrationEnabled"] = False
    st["integrationPromptSeen"] = True
    st["launcherAdded"] = False
    st["launcherPromptSeen"] = True
    secure_state.write_state(st)

    return {"ok": True, "enabled": False}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        emit_bounded_json(get_status())
    cmd = sys.argv[1]
    if cmd in ("status", "integration-status", "launcher-status"):
        emit_bounded_json(get_status())
    elif cmd in ("enable", "integration-enable", "launcher-add"):
        emit_bounded_json(enable_integration())
    elif cmd in ("disable", "integration-disable", "launcher-remove"):
        emit_bounded_json(disable_integration())
    elif cmd in ("dismiss-prompt", "launcher-dismiss-prompt"):
        emit_bounded_json(dismiss_prompt())
    else:
        emit_bounded_json({"ok": False, "error": f"Unknown integration command: {cmd}"})
