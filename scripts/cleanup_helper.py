#!/usr/bin/env python3
"""
Standalone Removal Cleanup Helper for Cursor Theme Manager.
Invoked by systemd user service `cursor-theme-manager-cleanup.service` when the
plugins directory changes.

1. Checks if `~/.config/omarchy/plugins/sanjyay.cursor-theme-manager` exists:
   - If it exists -> exits 0 immediately (cheap no-op).
2. If absent -> verifies integration was armed, validates secure state, restores
   original cursor configuration (persistent + LIVE Hyprland cursor manager),
   verifies success, removes marker-owned desktop file, deletes state, preserves
   imported cursor themes, and performs self-cleanup.
3. If restoration fails: preserves state & cleanup helper for retry.
"""

import sys
import os
import re
import stat
import json
import subprocess
import shutil
from pathlib import Path

PLUGIN_ID = "sanjyay.cursor-theme-manager"
OWNERSHIP_MARKER = "X-CursorThemeManager-Owned=true"

def get_paths() -> dict:
    home = os.environ.get("HOME", os.path.expanduser("~"))
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config"))
    data_home = os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local", "share"))
    state_home = os.environ.get("XDG_STATE_HOME", os.path.join(home, ".local", "state"))

    return {
        "home": home,
        "config_home": config_home,
        "data_home": data_home,
        "state_home": state_home,
        "plugin_dir": os.path.join(config_home, "omarchy", "plugins", PLUGIN_ID),
        "desktop_file": os.path.join(data_home, "applications", "cursor-theme-manager.desktop"),
        "state_dir": os.path.join(state_home, "cursor-theme-manager"),
        "state_file": os.path.join(state_home, "cursor-theme-manager", "state.json"),
        "systemd_user_dir": os.path.join(config_home, "systemd", "user"),
        "path_unit": os.path.join(config_home, "systemd", "user", "cursor-theme-manager-cleanup.path"),
        "service_unit": os.path.join(config_home, "systemd", "user", "cursor-theme-manager-cleanup.service"),
        "libexec_dir": os.path.join(home, ".local", "libexec", "cursor-theme-manager"),
        "cleanup_exe": os.path.join(home, ".local", "libexec", "cursor-theme-manager", "cleanup"),
        "uwsm_common": os.path.join(config_home, "uwsm", "env.d", "90-omarchy-cursor-switcher"),
        "uwsm_hypr": os.path.join(config_home, "uwsm", "env-hyprland.d", "90-omarchy-cursor-switcher")
    }


def run_cmd(args, env_override=None, timeout=3.0):
    try:
        env = dict(os.environ)
        if env_override:
            env.update(env_override)
        res = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)
        return res.returncode == 0, res.stdout, res.stderr
    except Exception as e:
        return False, "", str(e)


def find_hyprland_instance():
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    hypr_dir = Path(xdg_runtime) / "hypr"
    if hypr_dir.is_dir():
        for d in hypr_dir.iterdir():
            if d.is_dir() and (d / ".socket.sock").exists():
                return d.name
    return None



def has_cursor_data(theme_name: str) -> bool:
    if not theme_name or not re.match(r'^[a-zA-Z0-9_\-\.\ ]+$', str(theme_name)):
        return False
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
    for root in roots:
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


def is_file_owned_by_us(filepath: str) -> bool:
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


def read_secure_state():
    paths = get_paths()
    state_dir = paths["state_dir"]
    if not os.path.isdir(state_dir):
        return None
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        dir_fd = os.open(state_dir, flags)
        try:
            st = os.fstat(dir_fd)
            if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or (st.st_mode & 0o777) != 0o700:
                return None

            file_flags = os.O_RDONLY | os.O_NONBLOCK
            if hasattr(os, "O_NOFOLLOW"):
                file_flags |= os.O_NOFOLLOW

            file_fd = os.open("state.json", file_flags, dir_fd=dir_fd)
            try:
                fst = os.fstat(file_fd)
                if not stat.S_ISREG(fst.st_mode) or fst.st_uid != os.getuid() or fst.st_size > 65536:
                    return None
                raw = os.read(file_fd, 65536).decode("utf-8", errors="ignore")
                data = json.loads(raw)
                return data if isinstance(data, dict) else None
            finally:
                os.close(file_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        return None


def restore_cursor(orig) -> bool:
    """Restores both persistent and live compositor cursor configurations."""
    if not isinstance(orig, dict) or not orig.get("captured"):
        return False

    live_success = True

    # 1. LIVE Hyprland compositor transition
    if shutil.which("hyprctl"):
        hypr_env = {}
        sig = find_hyprland_instance()
        if sig:
            hypr_env["HYPRLAND_INSTANCE_SIGNATURE"] = sig

        live_theme = orig.get("liveRestoreTheme")
        live_size = orig.get("liveRestoreSize") or 24

        # Fallback if liveRestoreTheme not explicitly present
        if not live_theme:
            if orig.get("hyprcursorThemeSet") and orig.get("hyprcursorTheme"):
                live_theme = orig["hyprcursorTheme"]
            elif orig.get("xcursorThemeSet") and orig.get("xcursorTheme"):
                live_theme = orig["xcursorTheme"]
            elif orig.get("gtkThemeSet") and orig.get("gtkTheme") and orig["gtkTheme"] != "default":
                live_theme = orig["gtkTheme"]
            else:
                live_theme = "Adwaita"

        if live_theme:
            if not has_cursor_data(live_theme):
                sys.stderr.write(f"cursorctl: original live theme '{live_theme}' no longer exists on disk; preserving cleanup state for retry.\n")
                return False
            ok, out, err = run_cmd(["hyprctl", "setcursor", str(live_theme), str(live_size)], env_override=hypr_env)
            if not ok:
                live_success = False
                sys.stderr.write(f"cursorctl: live restore via hyprctl failed: {err}\n")

    # 2. GTK / gsettings (persistent)
    if orig.get("gtkThemeSet") and orig.get("gtkTheme"):
        run_cmd(["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", str(orig["gtkTheme"])])
    elif orig.get("xcursorThemeSet") and orig.get("xcursorTheme"):
        run_cmd(["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", str(orig["xcursorTheme"])])
    else:
        run_cmd(["gsettings", "reset", "org.gnome.desktop.interface", "cursor-theme"])

    if orig.get("gtkSizeSet") and orig.get("gtkSize"):
        run_cmd(["gsettings", "set", "org.gnome.desktop.interface", "cursor-size", str(orig["gtkSize"])])
    elif orig.get("xcursorSizeSet") and orig.get("xcursorSize"):
        run_cmd(["gsettings", "set", "org.gnome.desktop.interface", "cursor-size", str(orig["xcursorSize"])])
    else:
        run_cmd(["gsettings", "reset", "org.gnome.desktop.interface", "cursor-size"])

    # 3. Systemd & DBus user environment (exact original state)
    set_env = []
    unset_env = []

    if orig.get("hyprcursorThemeSet") and orig.get("hyprcursorTheme"):
        set_env.append(f"HYPRCURSOR_THEME={orig['hyprcursorTheme']}")
    else:
        unset_env.append("HYPRCURSOR_THEME")

    if orig.get("hyprcursorSizeSet") and orig.get("hyprcursorSize"):
        set_env.append(f"HYPRCURSOR_SIZE={orig['hyprcursorSize']}")
    else:
        unset_env.append("HYPRCURSOR_SIZE")

    if orig.get("xcursorThemeSet") and orig.get("xcursorTheme"):
        set_env.append(f"XCURSOR_THEME={orig['xcursorTheme']}")
    else:
        unset_env.append("XCURSOR_THEME")

    if orig.get("xcursorSizeSet") and orig.get("xcursorSize"):
        set_env.append(f"XCURSOR_SIZE={orig['xcursorSize']}")
    else:
        unset_env.append("XCURSOR_SIZE")

    if set_env:
        run_cmd(["systemctl", "--user", "set-environment"] + set_env)
        run_cmd(["dbus-update-activation-environment", "--systemd"] + set_env)
    if unset_env:
        run_cmd(["systemctl", "--user", "unset-environment"] + unset_env)

    # 4. Remove UWSM drop-in files
    paths = get_paths()
    if os.path.exists(paths["uwsm_common"]):
        try: os.unlink(paths["uwsm_common"])
        except OSError: pass
    if os.path.exists(paths["uwsm_hypr"]):
        try: os.unlink(paths["uwsm_hypr"])
        except OSError: pass

    return live_success


def execute_cleanup():
    paths = get_paths()
    # 1. Check if plugin directory still exists
    if os.path.exists(paths["plugin_dir"]):
        # Plugin is still present; watcher event was for another plugin change.
        sys.exit(0)

    # 2. Plugin is absent! Read secure state
    state = read_secure_state()

    # If state is missing because cleanup already ran, exit cleanly
    if state is None and not os.path.exists(paths["desktop_file"]) and not os.path.exists(paths["path_unit"]):
        sys.exit(0)

    # 3. Validate cursorModifiedByCtm and baseline presence
    cursor_modified = state.get("cursorModifiedByCtm", False) if state else False
    orig_c = (state.get("preCtmCursor") or state.get("originalCursor")) if state else None

    if cursor_modified:
        if not orig_c or not orig_c.get("captured"):
            sys.stderr.write("cursorctl: critical error: CTM modified cursor but preCtmCursor baseline is missing or uncaptured. Preserving state and helper for recovery.\n")
            sys.exit(1)

    # 4. Restore original cursor if captured
    if orig_c and orig_c.get("captured"):
        restore_ok = restore_cursor(orig_c)
        if not restore_ok:
            sys.stderr.write("cursorctl: critical failure restoring cursor baseline; preserving state for retry.\n")
            sys.exit(1)

    # 5. Remove marker-owned desktop file
    if os.path.exists(paths["desktop_file"]) and is_file_owned_by_us(paths["desktop_file"]):
        try:
            os.unlink(paths["desktop_file"])
            if shutil.which("update-desktop-database"):
                run_cmd(["update-desktop-database", "-q", os.path.dirname(paths["desktop_file"])])
        except OSError:
            pass

    # 6. Remove state directory (state.json)
    if os.path.isdir(paths["state_dir"]):
        try:
            shutil.rmtree(paths["state_dir"], ignore_errors=True)
        except OSError:
            pass

    # 7. Self-cleanup: remove systemd units and cleanup executable
    if os.path.exists(paths["path_unit"]):
        try:
            run_cmd(["systemctl", "--user", "stop", "cursor-theme-manager-cleanup.path"])
            run_cmd(["systemctl", "--user", "disable", "cursor-theme-manager-cleanup.path"])
            os.unlink(paths["path_unit"])
        except OSError:
            pass

    if os.path.exists(paths["service_unit"]):
        try:
            os.unlink(paths["service_unit"])
        except OSError:
            pass

    run_cmd(["systemctl", "--user", "daemon-reload"])

    # Unlink own executable and remove libexec directory
    if os.path.exists(paths["cleanup_exe"]):
        try:
            os.unlink(paths["cleanup_exe"])
        except OSError:
            pass
    if os.path.isdir(paths["libexec_dir"]):
        try:
            os.rmdir(paths["libexec_dir"])
        except OSError:
            pass

    # 8. Clean up CTM-generated internal conversion caches
    user_icons = os.path.join(paths["data_home"], "icons")
    if os.path.isdir(user_icons):
        try:
            for entry in os.listdir(user_icons):
                entry_path = os.path.join(user_icons, entry)
                if not os.path.isdir(entry_path) or os.path.islink(entry_path):
                    continue
                try:
                    st = os.stat(entry_path, follow_symlinks=False)
                    if st.st_uid != os.getuid():
                        continue
                    gen_marker = os.path.join(entry_path, ".cursor-theme-manager-generated")
                    legacy_conv = os.path.join(entry_path, ".omarchy-cursor-switcher-converted")
                    imp_marker1 = os.path.join(entry_path, ".cursor-theme-manager-imported")
                    imp_marker2 = os.path.join(entry_path, ".omarchy-cursor-switcher-imported")

                    # NEVER delete imported user themes
                    if os.path.isfile(imp_marker1) or os.path.isfile(imp_marker2):
                        continue

                    # Delete ONLY if verified as CTM-generated internal conversion cache
                    if os.path.isfile(gen_marker) or os.path.isfile(legacy_conv):
                        shutil.rmtree(entry_path, ignore_errors=True)
                except Exception:
                    pass
        except Exception:
            pass

    # Note: Imported cursor themes in ~/.local/share/icons/ are preserved.
    print("Cursor Theme Manager removed.")
    print("Previous cursor configuration restored.")
    print("Imported cursor themes were preserved.")
    sys.exit(0)


if __name__ == "__main__":
    execute_cleanup()
