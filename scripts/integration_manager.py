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
import re
import stat
import json
import hashlib
import errno
import secrets
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

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

LEGACY_PATH_UNIT_CONTENT = """[Unit]
Description=Watch for Cursor Theme Manager removal

[Path]
PathChanged=%h/.config/omarchy/plugins
Unit=cursor-theme-manager-cleanup.service

[Install]
WantedBy=default.target
"""

PATH_UNIT_CONTENT = """# X-CursorThemeManager-Owned=true
# sanjyay.cursor-theme-manager
[Unit]
Description=Watch for Cursor Theme Manager removal

[Path]
PathChanged=%h/.config/omarchy/plugins
Unit=cursor-theme-manager-cleanup.service

[Install]
WantedBy=default.target
"""


def get_paths() -> Dict[str, str]:
    home = os.environ.get("HOME", os.path.expanduser("~"))
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config"))
    data_home = os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local", "share"))
    plugin_dir = os.path.join(config_home, "omarchy", "plugins", PLUGIN_ID)

    return {
        "desktop": os.path.join(data_home, "applications", "cursor-theme-manager.desktop"),
        "libexec_dir": os.path.join(home, ".local", "libexec", "cursor-theme-manager"),
        "cleanup": os.path.join(home, ".local", "libexec", "cursor-theme-manager", "cleanup"),
        "systemd_user": os.path.join(config_home, "systemd", "user"),
        "path_unit": os.path.join(config_home, "systemd", "user", "cursor-theme-manager-cleanup.path"),
        "service_unit": os.path.join(config_home, "systemd", "user", "cursor-theme-manager-cleanup.service"),
        "plugin_dir": plugin_dir if os.path.isdir(plugin_dir) else str(SCRIPT_DIR.parent)
    }


def get_plugin_installation_path() -> str:
    home = os.environ.get("HOME", os.path.expanduser("~"))
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config"))
    installed_plugin_dir = os.path.join(config_home, "omarchy", "plugins", PLUGIN_ID)
    return installed_plugin_dir if os.path.lexists(installed_plugin_dir) else str(SCRIPT_DIR.parent)


def get_plugin_installation_fingerprint(plugin_path: Optional[str] = None) -> Optional[str]:
    """Return the installation-token fingerprint, with inode identity for legacy installs."""
    target = plugin_path or get_plugin_installation_path()
    marker = read_installation_token(target)
    if marker:
        return hashlib.sha256(marker.encode("ascii")).hexdigest()
    try:
        st = os.lstat(target)
        if not (stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode)):
            return None
        identity = f"{st.st_dev}:{st.st_ino}".encode("ascii")
        return hashlib.sha256(identity).hexdigest()
    except OSError:
        return None


def read_installation_token(plugin_path: Optional[str] = None) -> Optional[str]:
    target = plugin_path or get_plugin_installation_path()
    dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        dir_flags |= os.O_NOFOLLOW
    try:
        dir_fd = os.open(target, dir_flags)
    except OSError:
        return None
    try:
        dst = os.fstat(dir_fd)
        if not stat.S_ISDIR(dst.st_mode) or dst.st_uid != os.getuid():
            return None
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(".installation_instance", flags, dir_fd=dir_fd)
        except OSError:
            return None
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or
                    stat.S_IMODE(st.st_mode) != 0o600 or st.st_size > 65):
                return None
            raw = os.read(fd, 65).decode("ascii", errors="strict").strip()
            return raw if re.fullmatch(r"[a-f0-9]{32}", raw) else None
        except (OSError, UnicodeError):
            return None
        finally:
            os.close(fd)
    finally:
        os.close(dir_fd)


def ensure_installation_identity() -> Dict[str, Any]:
    """Create the per-install token before any external state is read or adopted."""
    target = get_plugin_installation_path()
    dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        dir_flags |= os.O_NOFOLLOW
    try:
        dir_fd = os.open(target, dir_flags)
    except OSError as exc:
        return {"ok": False, "error": f"Could not securely open the plugin installation: {exc}"}
    try:
        dst = os.fstat(dir_fd)
        if not stat.S_ISDIR(dst.st_mode) or dst.st_uid != os.getuid():
            return {"ok": False, "error": "The plugin installation directory is not owned by the current user."}
        existing = read_installation_token(target)
        if existing:
            return {"ok": True, "instanceToken": existing, "pluginFingerprint": hashlib.sha256(existing.encode("ascii")).hexdigest()}

        token = secrets.token_hex(16)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(".installation_instance", flags, 0o600, dir_fd=dir_fd)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                return {"ok": False, "error": "The installation identity file is invalid or unsafe."}
            return {"ok": False, "error": f"Could not create the installation identity: {exc}"}
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
                raise RuntimeError("The installation identity target is not a safe regular file.")
            os.fchmod(fd, 0o600)
            os.write(fd, (token + "\n").encode("ascii"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(dir_fd)
        return {"ok": True, "instanceToken": token, "pluginFingerprint": hashlib.sha256(token.encode("ascii")).hexdigest()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        os.close(dir_fd)


def read_legacy_instance_marker() -> Optional[str]:
    """Read, but never create, the marker used by pre-fingerprint releases."""
    marker_path = os.path.join(get_plugin_installation_path(), ".installation_instance")
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(marker_path, flags)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_size > 256:
                return None
            raw = os.read(fd, 256).decode("ascii", errors="ignore").strip()
            return raw if re.fullmatch(r"[a-fA-F0-9]{16,64}", raw) else None
        finally:
            os.close(fd)
    except OSError:
        return None


def is_file_owned_by_us(filepath: str, expected_instance: Optional[str] = None) -> bool:
    if not os.path.exists(filepath):
        return False
    try:
        flags = os.O_RDONLY | os.O_NONBLOCK
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(filepath, flags)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_size > 131072:
                return False
            content = os.read(fd, 131072).decode("utf-8", errors="ignore")
            if (OWNERSHIP_MARKER not in content) or (PLUGIN_ID not in content):
                return False
            if expected_instance:
                return f"X-CursorThemeManager-Instance={expected_instance}" in content
            return True
        finally:
            os.close(fd)
    except Exception:
        return False


def read_regular_user_file(filepath: str, max_bytes: int = 131072) -> Optional[str]:
    try:
        flags = os.O_RDONLY | os.O_NONBLOCK
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(filepath, flags)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_size > max_bytes:
                return None
            raw = os.read(fd, max_bytes + 1)
            if len(raw) > max_bytes:
                return None
            return raw.decode("utf-8", errors="strict")
        finally:
            os.close(fd)
    except (OSError, UnicodeError):
        return None


def is_owned_artifact(filepath: str, kind: str, expected_instance: Optional[str] = None) -> bool:
    """Recognize current instance markers plus narrowly defined legacy CTM files."""
    if is_file_owned_by_us(filepath, expected_instance):
        return True
    content = read_regular_user_file(filepath)
    if content is None:
        return False
    if kind == "cleanup":
        # Pre-header cleanup copies still contain both constants in executable
        # Python source. The instance remains bound by the companion service.
        return ("Standalone Removal Cleanup Helper for Cursor Theme Manager" in content and
                f'PLUGIN_ID = "{PLUGIN_ID}"' in content and OWNERSHIP_MARKER in content)
    if kind == "path_unit":
        return content == LEGACY_PATH_UNIT_CONTENT
    if kind == "service_unit" and expected_instance:
        expected_prefix = "%h/.local/libexec/cursor-theme-manager/cleanup --instance "
        match = re.search(r"^ExecStart=(.+)$", content, re.MULTILINE)
        return bool(match and match.group(1).startswith(expected_prefix + expected_instance + " ") and
                    re.fullmatch(
                        re.escape(expected_prefix) + re.escape(expected_instance) +
                        r" --plugin-fingerprint [a-f0-9]{64}", match.group(1)
                    ))
    return False


def restore_owned_artifact(filepath: str, snapshot: Tuple[bytes, int]) -> None:
    """Atomically restore an earlier owned artifact after a failed transaction."""
    data, mode = snapshot
    tmp_path = f"{filepath}.restore.{secrets.token_hex(12)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(tmp_path, flags, mode)
    try:
        os.fchmod(fd, mode)
        offset = 0
        while offset < len(data):
            offset += os.write(fd, data[offset:])
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.replace(tmp_path, filepath)
    except Exception:
        try: os.unlink(tmp_path)
        except OSError: pass
        raise


def get_status() -> Dict[str, Any]:
    paths = get_paths()
    st = secure_state.read_state()
    st_instance = st.get("integrationInstanceId")
    stored_fingerprint = st.get("integrationPluginFingerprint")
    current_fingerprint = get_plugin_installation_fingerprint()
    foreign_state = bool(
        stored_fingerprint and current_fingerprint and
        stored_fingerprint != current_fingerprint
    )

    # A generation mismatch has two materially different meanings. Matching
    # cleanup artifacts mean the previous installation still has a recovery
    # actor and the new installation must wait. No actor means the state
    # document was orphaned (for example an Integration-disabled installation
    # was removed); the new installation must reconcile it rather than poll
    # forever for a service that does not exist.
    recovery_artifacts = {
        "cleanup": is_owned_artifact(paths["cleanup"], "cleanup", st_instance),
        "pathUnit": is_owned_artifact(paths["path_unit"], "path_unit", st_instance),
        "serviceUnit": is_owned_artifact(paths["service_unit"], "service_unit", st_instance),
    }
    recovery_actor_present = any(recovery_artifacts.values())
    recovery_orphaned = foreign_state and not recovery_actor_present
    recovery_pending = foreign_state

    if stored_fingerprint:
        has_instance = bool(st_instance and current_fingerprint == stored_fingerprint)
    else:
        has_instance = bool(st_instance and read_legacy_instance_marker() == st_instance)
    desktop_exists = os.path.isfile(paths["desktop"]) and is_file_owned_by_us(
        paths["desktop"], expected_instance=st_instance if has_instance else None
    )
    cleanup_exists = bool(st_instance and is_owned_artifact(paths["cleanup"], "cleanup", st_instance) and os.access(paths["cleanup"], os.X_OK))
    path_unit_exists = bool(st_instance and is_owned_artifact(paths["path_unit"], "path_unit", st_instance))
    service_unit_exists = bool(st_instance and is_owned_artifact(paths["service_unit"], "service_unit", st_instance))

    all_artifacts = desktop_exists and cleanup_exists and path_unit_exists and service_unit_exists
    state_enabled = bool(st.get("integrationEnabled", st.get("launcherAdded", False)))

    path_unit_active = False
    if all_artifacts and state_enabled and has_instance:
        res = run_bounded(["systemctl", "--user", "is-active", "cursor-theme-manager-cleanup.path"], timeout=1.0)
        path_unit_active = res.ok and ("active" in res.stdout.strip())

    effective_enabled = all_artifacts and state_enabled and has_instance
    prompt_seen = effective_enabled

    return {
        "ok": True,
        "enabled": effective_enabled,
        "promptSeen": prompt_seen,
        "stateEnabled": state_enabled,
        "instanceId": st_instance if has_instance else None,
        # Always expose the current installation identity so a fresh, disabled
        # QML instance can bind its first mutation/consent request to it.
        "pluginFingerprint": current_fingerprint,
        "recoveryPending": recovery_pending,
        "recoveryOrphaned": recovery_orphaned,
        "recoveryActorPresent": recovery_actor_present,
        "recoveryArtifacts": recovery_artifacts,
        "artifacts": {
            "desktop": desktop_exists,
            "cleanup": cleanup_exists,
            "pathUnit": path_unit_exists,
            "serviceUnit": service_unit_exists,
            "pathUnitActive": path_unit_active,
            "instanceMatched": has_instance
        },
        "paths": paths
    }


def dismiss_prompt() -> Dict[str, Any]:
    # In-memory / session-only dismissal — never write durable files solely for prompt dismissal
    return {"ok": True, "promptSeen": False}


def enable_integration(expected_plugin_fingerprint: Optional[str] = None) -> Dict[str, Any]:
    """
    Transactionally installs all integration artifacts bound to a cryptographically
    random installation instance token.
    If any step fails, rolls back all installed files.
    """
    paths = get_paths()
    desktop_file = paths["desktop"]
    libexec_dir = paths["libexec_dir"]
    cleanup_file = paths["cleanup"]
    systemd_user = paths["systemd_user"]
    path_unit = paths["path_unit"]
    service_unit = paths["service_unit"]

    instance_id = secrets.token_hex(16)
    plugin_fingerprint = get_plugin_installation_fingerprint()
    if not plugin_fingerprint:
        return {"ok": False, "error": "Could not identify the installed plugin directory."}
    if expected_plugin_fingerprint is not None and expected_plugin_fingerprint != plugin_fingerprint:
        return {
            "ok": False,
            "error": "This request belongs to a removed Cursor Theme Manager installation. Reopen CTM and try again."
        }

    # 1. Validation phase: never overwrite a foreign file at any integration target.
    artifact_kinds = {
        desktop_file: "desktop", cleanup_file: "cleanup",
        path_unit: "path_unit", service_unit: "service_unit"
    }
    current_state = secure_state.read_state()
    stored_fingerprint = current_state.get("integrationPluginFingerprint")
    if stored_fingerprint and stored_fingerprint != plugin_fingerprint:
        return {
            "ok": False,
            "error": "A previous installation is still restoring the cursor. Wait for cleanup to finish, then try again.",
            "recoveryPending": True,
        }
    previous_instance = current_state.get("integrationInstanceId")
    for existing_path, kind in artifact_kinds.items():
        if os.path.lexists(existing_path) and not is_owned_artifact(existing_path, kind, previous_instance):
            return {
                "ok": False,
                "error": f"An existing file uses an integration filename and was not created by Cursor Theme Manager ({existing_path})."
            }

    previous_artifacts = {}
    for path, kind in artifact_kinds.items():
        if os.path.exists(path):
            content = read_regular_user_file(path)
            if content is not None:
                previous_artifacts[path] = (content.encode("utf-8"), stat.S_IMODE(os.stat(path).st_mode))

    # Ensure parent directories exist
    os.makedirs(os.path.dirname(desktop_file), exist_ok=True)
    os.makedirs(libexec_dir, exist_ok=True)
    os.makedirs(systemd_user, exist_ok=True)

    cleanup_helper_source = SCRIPT_DIR / "cleanup_helper.py"
    if not cleanup_helper_source.is_file():
        return {"ok": False, "error": "Missing cleanup_helper.py in scripts directory."}
    cleanup_content = cleanup_helper_source.read_text(encoding="utf-8")
    cleanup_content = cleanup_content.replace(
        "\n", f"\n# {OWNERSHIP_MARKER}\n# {PLUGIN_ID}\n# X-CursorThemeManager-Instance={instance_id}\n", 1
    )

    desktop_content = f"""[Desktop Entry]
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
X-CursorThemeManager-Instance={instance_id}
"""

    path_unit_content = f"# X-CursorThemeManager-Instance={instance_id}\n{PATH_UNIT_CONTENT}"

    service_content = f"""# {OWNERSHIP_MARKER}
# {PLUGIN_ID}
# X-CursorThemeManager-Instance={instance_id}
[Unit]
Description=Cursor Theme Manager removal cleanup

[Service]
Type=oneshot
ExecStart=%h/.local/libexec/cursor-theme-manager/cleanup --instance {instance_id} --plugin-fingerprint {plugin_fingerprint}
"""

    # 2. Staging phase: write all files to temporary names
    staged_files: List[Tuple[str, str, int]] = []
    # (tmp_path, final_path, mode)

    nonce = secrets.token_hex(12)
    desktop_tmp = f"{desktop_file}.tmp.{nonce}"
    cleanup_tmp = f"{cleanup_file}.tmp.{nonce}"
    path_tmp = f"{path_unit}.tmp.{nonce}"
    service_tmp = f"{service_unit}.tmp.{nonce}"

    tmp_manifest = [
        (desktop_tmp, desktop_file, desktop_content, 0o644),
        (cleanup_tmp, cleanup_file, cleanup_content, 0o755),
        (path_tmp, path_unit, path_unit_content, 0o644),
        (service_tmp, service_unit, service_content, 0o644)
    ]

    installed_targets: List[str] = []
    previous_state: Optional[Dict[str, Any]] = None
    state_committed = False

    try:
        # Write and fsync each temporary file with descriptor-held permissions
        for tmp_path, final_path, content, mode in tmp_manifest:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
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

        # 5. Commit state before touching the live plugin directory. Omarchy
        # reloads local plugins on any directory change and may terminate this
        # helper as soon as the instance marker is published.
        st = secure_state.read_state()
        previous_state = dict(st)
        st["integrationEnabled"] = True
        st["integrationPromptSeen"] = True
        st["launcherAdded"] = True
        st["launcherPromptSeen"] = True
        st["integrationInstanceId"] = instance_id
        st["integrationPluginFingerprint"] = plugin_fingerprint
        secure_state.write_state(st)
        state_committed = True

        return {
            "ok": True, "enabled": True, "instanceId": instance_id,
            "pluginFingerprint": plugin_fingerprint, "paths": paths
        }

    except Exception as e:
        # Transactional Rollback: clean up all temporary and installed files
        for tmp_path, _, _, _ in tmp_manifest:
            if os.path.exists(tmp_path):
                try: os.unlink(tmp_path)
                except OSError: pass

        for target in installed_targets:
            previous = previous_artifacts.get(target)
            try:
                if previous is not None:
                    restore_owned_artifact(target, previous)
                elif os.path.exists(target):
                    os.unlink(target)
            except OSError:
                pass
        if os.path.isdir(libexec_dir):
            try: os.rmdir(libexec_dir)
            except OSError: pass

        if state_committed and previous_state is not None:
            try:
                secure_state.write_state(previous_state)
            except Exception:
                pass

        run_bounded(["systemctl", "--user", "daemon-reload"], timeout=2.0)
        return {"ok": False, "error": f"Integration installation failed and was rolled back: {e}"}


def disable_integration(expected_plugin_fingerprint: Optional[str] = None) -> Dict[str, Any]:
    """
    Idempotently removes all integration artifacts and disables systemd units.
    """
    paths = get_paths()
    if (expected_plugin_fingerprint is not None and
            expected_plugin_fingerprint != get_plugin_installation_fingerprint()):
        return {
            "ok": False,
            "error": "This request belongs to a removed Cursor Theme Manager installation. Reopen CTM and try again."
        }
    desktop_file = paths["desktop"]
    libexec_dir = paths["libexec_dir"]
    cleanup_file = paths["cleanup"]
    path_unit = paths["path_unit"]
    service_unit = paths["service_unit"]

    # Stop and disable systemd path unit
    run_bounded(["systemctl", "--user", "stop", "cursor-theme-manager-cleanup.path"], timeout=2.0)
    run_bounded(["systemctl", "--user", "disable", "cursor-theme-manager-cleanup.path"], timeout=2.0)

    st = secure_state.read_state()
    expected_instance = st.get("integrationInstanceId")

    # Remove only instance-bound files created by this integration.
    if os.path.exists(path_unit) and is_owned_artifact(path_unit, "path_unit", expected_instance):
        try: os.unlink(path_unit)
        except OSError: pass

    if os.path.exists(service_unit) and is_owned_artifact(service_unit, "service_unit", expected_instance):
        try: os.unlink(service_unit)
        except OSError: pass

    run_bounded(["systemctl", "--user", "daemon-reload"], timeout=2.0)

    # Remove cleanup helper
    if os.path.exists(cleanup_file) and is_owned_artifact(cleanup_file, "cleanup", expected_instance):
        try: os.unlink(cleanup_file)
        except OSError: pass
    if os.path.isdir(libexec_dir):
        try: os.rmdir(libexec_dir)
        except OSError: pass

    # Remove desktop file if owned by us
    if os.path.exists(desktop_file):
        if is_owned_artifact(desktop_file, "desktop", expected_instance):
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
    st["integrationEnabled"] = False
    st["integrationPromptSeen"] = True
    st["launcherAdded"] = False
    st["launcherPromptSeen"] = True
    st["integrationInstanceId"] = None
    st["integrationPluginFingerprint"] = None
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
