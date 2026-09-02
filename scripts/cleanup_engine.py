#!/usr/bin/env python3
"""
Hardened Cleanup, Snapshot, and Desktop Integration Engine for Cursor Theme Manager.
Implements bounded subprocess execution, transactional rollback for integration install,
descriptor-relative durable writes, and safe restoration of allowlisted cursor variables.
"""

import sys
import os
import glob
import shutil
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from runtime_safety import (
    run_bounded, sanitize_text, emit_bounded_json,
    TIMEOUT_SNAPSHOT, TIMEOUT_RESTORE, TIMEOUT_INTEGRATION,
    LIMIT_STDOUT_SMALL, LIMIT_STDERR_DEFAULT
)
import secure_state

CURSOR_VARS = ("HYPRCURSOR_THEME", "HYPRCURSOR_SIZE", "XCURSOR_THEME", "XCURSOR_SIZE")


def _get_home_dirs() -> Tuple[str, str, str, str]:
    home = os.environ.get("HOME", os.path.expanduser("~"))
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config"))
    data_home = os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local", "share"))
    cache_home = os.environ.get("XDG_CACHE_HOME", os.path.join(home, ".cache"))
    return home, config_home, data_home, cache_home


# ==============================================================================
# SNAPSHOT ORIGINAL STATE
# ==============================================================================

def snapshot_original_state() -> Dict[str, Any]:
    """Captures original GTK cursor, systemd environment, and UWSM drop-in state."""
    home, config_home, data_home, _ = _get_home_dirs()

    # If snapshot already exists and is valid, preserve it (first capture wins)
    existing = secure_state.read_snapshot()
    if existing:
        return {"ok": True, "snapshot": existing, "already_existed": True}

    # 1. Capture GTK theme & size via gsettings
    gtk_theme_present = False
    gtk_theme_val = ""
    res = run_bounded(["gsettings", "get", "org.gnome.desktop.interface", "cursor-theme"],
                      timeout=2.0, stdout_limit=LIMIT_STDOUT_SMALL)
    if res.ok and res.stdout.strip():
        val = res.stdout.strip().strip("'").strip('"')
        if val:
            gtk_theme_present = True
            gtk_theme_val = sanitize_text(val, max_len=128)

    gtk_size_present = False
    gtk_size_val = 24
    res = run_bounded(["gsettings", "get", "org.gnome.desktop.interface", "cursor-size"],
                      timeout=2.0, stdout_limit=LIMIT_STDOUT_SMALL)
    if res.ok and res.stdout.strip():
        val = res.stdout.strip()
        if val.isdigit():
            gtk_size_present = True
            try:
                gtk_size_val = int(val)
            except ValueError:
                pass

    # 2. Capture systemd user environment (strictly bounded, only 4 cursor vars)
    sysd_env = {}
    systemd_probe_succeeded = False
    res = run_bounded(["systemctl", "--user", "show-environment"],
                      timeout=2.0, stdout_limit=16 * 1024)
    if res.ok:
        systemd_probe_succeeded = True
        for line in res.stdout.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                k_clean = k.strip()
                if k_clean in CURSOR_VARS:
                    sysd_env[k_clean] = sanitize_text(v.strip(), max_len=256)

    def capture_env(mapping, name):
        val = mapping.get(name, "")
        return {"present": name in mapping and bool(val), "value": sanitize_text(val, max_len=256)}

    # 3. Check plugin-owned UWSM drop-in files
    uwsm_common = os.path.join(config_home, "uwsm", "env.d", "90-omarchy-cursor-switcher")
    uwsm_hypr = os.path.join(config_home, "uwsm", "env-hyprland.d", "90-omarchy-cursor-switcher")

    def capture_file(path):
        if not os.path.isfile(path) or os.path.islink(path):
            return {"present": False}
        try:
            if os.path.getsize(path) > 8192:
                return {"present": True, "readError": "File too large"}
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(8192)
            mode = os.stat(path).st_mode & 0o777
            return {"present": True, "content": content, "mode": mode}
        except Exception as exc:
            return {"present": True, "readError": sanitize_text(str(exc), max_len=128)}

    data = {
        "version": 2,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "gtkTheme": {
            "present": gtk_theme_present,
            "value": gtk_theme_val
        },
        "gtkSize": {
            "present": gtk_size_present,
            "value": gtk_size_val
        },
        "systemdProbeSucceeded": systemd_probe_succeeded,
        "systemdEnvironment": {name: capture_env(sysd_env, name) for name in CURSOR_VARS},
        "processEnvironment": {name: capture_env(os.environ, name) for name in CURSOR_VARS},
        "uwsmEnvCommon": capture_file(uwsm_common),
        "uwsmEnvHyprland": capture_file(uwsm_hypr)
    }

    try:
        secure_state.write_snapshot(data)
        return {"ok": True, "snapshot": data, "already_existed": False}
    except Exception as exc:
        return {"ok": False, "error": f"Failed to save snapshot: {exc}"}


# ==============================================================================
# RESTORE ORIGINAL STATE
# ==============================================================================

def get_system_default_cursor() -> str:
    home, _, data_home, _ = _get_home_dirs()
    candidates = [
        "/usr/share/icons/default/index.theme",
        os.path.join(data_home, "icons", "default", "index.theme"),
        os.path.join(home, ".icons", "default", "index.theme")
    ]
    for p in candidates:
        if os.path.isfile(p) and not os.path.islink(p):
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.strip().startswith("Inherits="):
                            inh = line.strip().split("=", 1)[1].strip()
                            if inh:
                                return sanitize_text(inh, max_len=128)
            except Exception:
                pass
    for cand in ["Bibata-Catppuccin-Mocha", "Adwaita", "Tokyonight-Dark"]:
        if os.path.isdir(f"/usr/share/icons/{cand}"):
            return cand
    return "Adwaita"


def restore_original_state() -> Dict[str, Any]:
    """Restores pre-plugin cursor settings and environment safely."""
    home, config_home, _, _ = _get_home_dirs()
    snap = secure_state.read_snapshot()

    is_valid_snap = False
    if snap and isinstance(snap, dict) and snap.get("version") == 2:
        gtk_theme = snap.get("gtkTheme", {})
        gtk_size = snap.get("gtkSize", {})
        systemd_env = snap.get("systemdEnvironment", {})
        uwsm_common_state = snap.get("uwsmEnvCommon", {"present": False})
        uwsm_hypr_state = snap.get("uwsmEnvHyprland", {"present": False})
        is_valid_snap = True
    elif snap and isinstance(snap, dict) and snap.get("version") == 1:
        gtk_theme = snap.get("gtkTheme", {})
        gtk_size = snap.get("gtkSize", {})
        systemd_env = {
            "HYPRCURSOR_THEME": snap.get("hyprcursorTheme", {}),
            "HYPRCURSOR_SIZE": snap.get("hyprcursorSize", {}),
            "XCURSOR_THEME": snap.get("xcursorTheme", {}),
            "XCURSOR_SIZE": snap.get("xcursorSize", {}),
        }
        uwsm_common_state = {"present": bool(snap.get("uwsmEnvCommonExisted", False))}
        uwsm_hypr_state = {"present": bool(snap.get("uwsmEnvHyprlandExisted", False))}
        is_valid_snap = True

    if not is_valid_snap:
        # Invalid snapshot: preserve current state without broad configuration overwrite
        uwsm_common = os.path.join(config_home, "uwsm", "env.d", "90-omarchy-cursor-switcher")
        uwsm_hypr = os.path.join(config_home, "uwsm", "env-hyprland.d", "90-omarchy-cursor-switcher")
        for p in (uwsm_common, uwsm_hypr):
            if os.path.isfile(p) and not os.path.islink(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        hdr = f.readline()
                    if "Managed by sanjyay.cursor-theme-manager" in hdr or "Managed by " in hdr:
                        os.unlink(p)
                except Exception:
                    pass
        return {
            "ok": False,
            "error": "No valid snapshot found; preserved current environment without configuration overwrite."
        }

    # 1. Restore GTK / GSettings
    if gtk_theme.get("present") and gtk_theme.get("value"):
        run_bounded(["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", str(gtk_theme["value"])], timeout=2.0)
    else:
        run_bounded(["gsettings", "reset", "org.gnome.desktop.interface", "cursor-theme"], timeout=2.0)

    if gtk_size.get("present") and gtk_size.get("value"):
        run_bounded(["gsettings", "set", "org.gnome.desktop.interface", "cursor-size", str(gtk_size["value"])], timeout=2.0)
    else:
        run_bounded(["gsettings", "reset", "org.gnome.desktop.interface", "cursor-size"], timeout=2.0)

    # 2. Restore systemd user environment & DBus activation environment
    set_assignments = []
    unset_names = []
    for key in CURSOR_VARS:
        obj = systemd_env.get(key, {})
        if obj.get("present") and obj.get("value") is not None and str(obj.get("value")) != "":
            set_assignments.append(f"{key}={obj['value']}")
        else:
            unset_names.append(key)

    if set_assignments:
        run_bounded(["systemctl", "--user", "set-environment"] + set_assignments, timeout=2.0)
        run_bounded(["dbus-update-activation-environment", "--systemd"] + set_assignments, timeout=2.0)

    if unset_names:
        run_bounded(["systemctl", "--user", "unset-environment"] + unset_names, timeout=2.0)
        dbus_clears = [f"{k}=" for k in unset_names]
        run_bounded(["dbus-update-activation-environment", "--systemd"] + dbus_clears, timeout=2.0)

    # 3. Restore live compositor cursor via hyprctl
    target_theme = str(gtk_theme.get("value") or get_system_default_cursor())
    try:
        target_size = int(gtk_size.get("value") or 24)
    except (ValueError, TypeError):
        target_size = 24
    run_bounded(["hyprctl", "setcursor", target_theme, str(target_size)], timeout=2.0)

    # 4. Restore exact pre-plugin UWSM fragment state
    uwsm_common = os.path.join(config_home, "uwsm", "env.d", "90-omarchy-cursor-switcher")
    uwsm_hypr = os.path.join(config_home, "uwsm", "env-hyprland.d", "90-omarchy-cursor-switcher")

    def restore_fragment(path, state):
        try:
            if state.get("present") and "content" in state:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                tmp = path + f".restore.{os.getpid()}"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(state["content"])
                os.chmod(tmp, int(state.get("mode", 0o600)))
                os.replace(tmp, path)
            elif not state.get("present") and os.path.lexists(path):
                os.unlink(path)
        except Exception as exc:
            sys.stderr.write(f"Warning: failed restoring UWSM fragment {path}: {exc}\n")

    restore_fragment(uwsm_common, uwsm_common_state)
    restore_fragment(uwsm_hypr, uwsm_hypr_state)

    return {"ok": True, "restored_theme": target_theme, "restored_size": target_size}


# ==============================================================================
# TRANSACTIONAL INTEGRATION INSTALL & REMOVE
# ==============================================================================

def install_integration(source_dir: str) -> Dict[str, Any]:
    """
    Transactionally installs optional desktop integration artifacts:
    - Stage 1: Snapshot original state
    - Stage 2: Install launcher, desktop file, scalable/pixmap icons, cleanup helper
    - Stage 3: Best-effort update-desktop-database / gtk-update-icon-cache
    Rolls back partially installed artifacts if any stage fails.
    """
    if not source_dir or not os.path.isdir(source_dir):
        return {"ok": False, "stage": "validation", "rolled_back": False, "error": f"Invalid source directory: {source_dir}"}

    home, _, data_home, _ = _get_home_dirs()
    bin_dir = os.path.join(home, ".local", "bin")
    app_dir = os.path.join(data_home, "applications")
    scalable_dir = os.path.join(data_home, "icons", "hicolor", "scalable", "apps")
    pixmaps_dir = os.path.join(data_home, "pixmaps")
    cleanup_dir = os.path.join(data_home, "omarchy-cursor-switcher")

    launcher_src = os.path.join(source_dir, "scripts", "omarchy-cursor-switcher")
    desktop_src = os.path.join(source_dir, "desktop", "omarchy-cursor-switcher.desktop")
    icon_src = os.path.join(source_dir, "icons", "omarchy-cursor-switcher.svg")
    cleanup_src = os.path.join(source_dir, "scripts", "omarchy-cursor-switcher-cleanup")

    for req_file in (launcher_src, desktop_src, icon_src, cleanup_src):
        if not os.path.isfile(req_file):
            return {"ok": False, "stage": "validation", "rolled_back": False, "error": f"Missing required asset: {req_file}"}

    # Stage 1: Snapshot original state
    snap_res = snapshot_original_state()
    if not snap_res.get("ok"):
        return {"ok": False, "stage": "snapshot", "rolled_back": False, "error": snap_res.get("error", "Snapshot capture failed")}
    newly_snapshotted = not snap_res.get("already_existed", False)

    # Track installed files for transactional rollback
    installed_files = []
    try:
        os.makedirs(bin_dir, exist_ok=True)
        os.makedirs(app_dir, exist_ok=True)
        os.makedirs(scalable_dir, exist_ok=True)
        os.makedirs(pixmaps_dir, exist_ok=True)
        os.makedirs(cleanup_dir, exist_ok=True)

        def copy_atomic(src, dst, mode):
            tmp = dst + f".tmp.{os.getpid()}"
            shutil.copy2(src, tmp)
            os.chmod(tmp, mode)
            os.replace(tmp, dst)
            installed_files.append(dst)

        # 1. Launcher script
        launcher_dst = os.path.join(bin_dir, "omarchy-cursor-switcher")
        copy_atomic(launcher_src, launcher_dst, 0o755)

        # 2. Desktop entry
        desktop_dst = os.path.join(app_dir, "omarchy-cursor-switcher.desktop")
        copy_atomic(desktop_src, desktop_dst, 0o644)

        # 3. Scalable SVG icon
        svg_dst = os.path.join(scalable_dir, "omarchy-cursor-switcher.svg")
        copy_atomic(icon_src, svg_dst, 0o644)

        # 4. Pixmaps icon
        pix_svg_dst = os.path.join(pixmaps_dir, "omarchy-cursor-switcher.svg")
        shutil.copy2(icon_src, pix_svg_dst)
        installed_files.append(pix_svg_dst)

        # 5. Raster PNG icons if present
        for sz in (48, 64, 128, 256):
            png_src = os.path.join(source_dir, "icons", f"omarchy-cursor-switcher-{sz}.png")
            if os.path.isfile(png_src):
                png_dir = os.path.join(data_home, "icons", "hicolor", f"{sz}x{sz}", "apps")
                os.makedirs(png_dir, exist_ok=True)
                png_dst = os.path.join(png_dir, "omarchy-cursor-switcher.png")
                shutil.copy2(png_src, png_dst)
                installed_files.append(png_dst)
                if sz in (48, 256):
                    pix_png = os.path.join(pixmaps_dir, "omarchy-cursor-switcher.png")
                    shutil.copy2(png_src, pix_png)
                    installed_files.append(pix_png)

        # 6. Cleanup helper and self-contained runtime modules
        for mod_name, mod_mode in [
            ("omarchy-cursor-switcher-cleanup", 0o755),
            ("cleanup_engine.py", 0o644),
            ("runtime_safety.py", 0o644),
            ("secure_state.py", 0o644)
        ]:
            src_f = os.path.join(source_dir, "scripts", mod_name)
            if os.path.isfile(src_f):
                dst_f = os.path.join(cleanup_dir, mod_name)
                copy_atomic(src_f, dst_f, mod_mode)

    except Exception as exc:
        # Rollback all installed files
        for path in installed_files:
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except Exception:
                pass
        if newly_snapshotted:
            secure_state.delete_snapshot()
        return {
            "ok": False,
            "stage": "install_files",
            "rolled_back": True,
            "error": f"Failed writing integration files: {exc}"
        }

    # Stage 3: Refresh caches (best effort)
    run_bounded(["update-desktop-database", "-q", app_dir], timeout=3.0)
    run_bounded(["gtk-update-icon-cache", "-q", os.path.join(data_home, "icons", "hicolor")], timeout=3.0)

    # Record integration state
    state = secure_state.read_state()
    state["integrationConsent"] = True
    state["integrationInstalled"] = True
    secure_state.write_state(state)

    return {
        "ok": True,
        "installed": installed_files
    }


def remove_integration(delete_snapshot: bool = True) -> Dict[str, Any]:
    """
    Safely removes ONLY plugin-owned desktop integration artifacts,
    restores original cursor state, deletes snapshot, and updates state.
    """
    home, config_home, data_home, _ = _get_home_dirs()
    bin_dir = os.path.join(home, ".local", "bin")
    app_dir = os.path.join(data_home, "applications")
    cleanup_dir = os.path.join(data_home, "omarchy-cursor-switcher")
    removed_files = []

    # 1. Launcher: verify header before deleting
    launcher_path = os.path.join(bin_dir, "omarchy-cursor-switcher")
    if os.path.isfile(launcher_path) and not os.path.islink(launcher_path):
        try:
            with open(launcher_path, "r", encoding="utf-8", errors="ignore") as f:
                header = f.readline()
                second = f.readline()
                if "Managed by sanjyay.cursor-theme-manager" in header or "Managed by sanjyay.cursor-theme-manager" in second:
                    os.unlink(launcher_path)
                    removed_files.append(launcher_path)
        except Exception:
            pass

    # 2. Desktop entry: verify content before deleting
    desktop_path = os.path.join(app_dir, "omarchy-cursor-switcher.desktop")
    if os.path.isfile(desktop_path) and not os.path.islink(desktop_path):
        try:
            with open(desktop_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(4096)
                if "X-Omarchy-Plugin=sanjyay.cursor-theme-manager" in content or "omarchy-cursor-switcher" in content:
                    os.unlink(desktop_path)
                    removed_files.append(desktop_path)
        except Exception:
            pass

    # 3. Icons
    for pattern in (
        os.path.join(data_home, "icons", "hicolor", "*", "apps", "omarchy-cursor-switcher.*"),
        os.path.join(data_home, "pixmaps", "omarchy-cursor-switcher.*")
    ):
        for f in glob.glob(pattern):
            if os.path.isfile(f) and not os.path.islink(f):
                try:
                    os.unlink(f)
                    removed_files.append(f)
                except Exception:
                    pass

    # 4. Cleanup helper directory
    if os.path.isdir(cleanup_dir) and not os.path.islink(cleanup_dir):
        try:
            shutil.rmtree(cleanup_dir, ignore_errors=True)
            removed_files.append(cleanup_dir)
        except Exception:
            pass

    # 5. Refresh databases
    run_bounded(["update-desktop-database", "-q", app_dir], timeout=3.0)
    run_bounded(["gtk-update-icon-cache", "-q", os.path.join(data_home, "icons", "hicolor")], timeout=3.0)

    # 6. Restore original state & delete snapshot if requested
    restore_original_state()
    if delete_snapshot:
        secure_state.delete_snapshot()

    # 7. Update state
    state = secure_state.read_state()
    state["integrationInstalled"] = False
    state["integrationConsent"] = False
    secure_state.write_state(state)

    return {
        "ok": True,
        "removed": removed_files
    }


def unregister_app() -> Dict[str, Any]:
    """Alias for removing desktop integration artifacts without state delete."""
    return remove_integration()


def deactivate() -> Dict[str, Any]:
    """Deactivates live settings, restores pre-plugin state, and removes desktop registration."""
    restore_original_state()
    # Remove files but keep snapshot and state
    remove_integration(delete_snapshot=False)
    return {"ok": True}


def purge() -> Dict[str, Any]:
    """Full purge: deactivates, removes all plugin-owned themes, caches, state, and snapshot."""
    deactivate()
    home, config_home, data_home, cache_home = _get_home_dirs()
    icons_dir = os.path.join(data_home, "icons")

    def remove_owned_theme(theme_path: str, marker_name: str):
        if not os.path.isdir(theme_path) or os.path.islink(theme_path):
            return
        marker = os.path.join(theme_path, marker_name)
        if os.path.isfile(marker):
            shutil.rmtree(theme_path, ignore_errors=True)

    if os.path.isdir(icons_dir):
        for entry in os.listdir(icons_dir):
            full = os.path.join(icons_dir, entry)
            if not os.path.isdir(full):
                continue
            remove_owned_theme(full, ".omarchy-cursor-switcher-theme")
            remove_owned_theme(full, ".omarchy-cursor-switcher-converted")
            remove_owned_theme(full, ".omarchy-cursor-switcher-imported")

    # Remove preview cache
    shutil.rmtree(os.path.join(cache_home, "omarchy-cursor-switcher"), ignore_errors=True)

    # Remove dedicated state directory & legacy files
    secure_state.delete_snapshot()
    shutil.rmtree(secure_state.get_state_dir_path(), ignore_errors=True)
    try:
        os.unlink(os.path.join(config_home, "omarchy", "cursor-switcher.json"))
    except OSError:
        pass
    try:
        os.unlink(os.path.join(config_home, "omarchy", "cursor-switcher-original-state.json"))
    except OSError:
        pass

    # Remove legacy and current cleanup helper dirs
    shutil.rmtree(os.path.join(data_home, "omarchy", "cursor-switcher"), ignore_errors=True)
    shutil.rmtree(os.path.join(data_home, "omarchy-cursor-switcher"), ignore_errors=True)

    return {"ok": True}


def on_destroy(plugin_dir: str = "") -> Dict[str, Any]:
    """Handles plugin deactivation/destruction. Purges if plugin checkout was deleted."""
    deactivate()
    is_removed = False
    if plugin_dir:
        import time
        for _ in range(30):
            if not os.path.isdir(plugin_dir):
                is_removed = True
                break
            time.sleep(0.05)
    else:
        is_removed = True

    if is_removed:
        purge()
    return {"ok": True, "purged": is_removed}


def audit_installation() -> Dict[str, Any]:
    """Generates an audit report of all plugin-related files and cleanliness."""
    home, config_home, data_home, cache_home = _get_home_dirs()
    icons_dir = os.path.join(data_home, "icons")
    bundled_themes = []
    converted_themes = []
    imported_themes = []

    if os.path.isdir(icons_dir):
        for d in glob.glob(os.path.join(icons_dir, "*")):
            if os.path.isfile(os.path.join(d, ".omarchy-cursor-switcher-theme")):
                bundled_themes.append(os.path.basename(d))
            elif os.path.isfile(os.path.join(d, ".omarchy-cursor-switcher-converted")):
                converted_themes.append(os.path.basename(d))
            elif os.path.isfile(os.path.join(d, ".omarchy-cursor-switcher-imported")):
                imported_themes.append(os.path.basename(d))

    icon_assets = []
    for pattern in (
        os.path.join(data_home, "icons", "hicolor", "*", "apps", "omarchy-cursor-switcher.*"),
        os.path.join(data_home, "pixmaps", "omarchy-cursor-switcher.*")
    ):
        icon_assets.extend(glob.glob(pattern))

    def managed_fragment(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                first = f.readline().strip()
            return first.startswith("# Managed by ") and ("cursor-theme-manager" in first or "cursor-switcher" in first)
        except OSError:
            return False

    uwsm_common_path = os.path.join(config_home, "uwsm", "env.d", "90-omarchy-cursor-switcher")
    uwsm_hypr_path = os.path.join(config_home, "uwsm", "env-hyprland.d", "90-omarchy-cursor-switcher")

    has_snapshot = (
        os.path.isfile(os.path.join(secure_state.get_state_dir_path(), "snapshot.json")) or
        os.path.isfile(os.path.join(config_home, "omarchy", "cursor-switcher-original-state.json"))
    )
    has_state = (
        os.path.isfile(os.path.join(secure_state.get_state_dir_path(), "state.json")) or
        os.path.isfile(os.path.join(config_home, "omarchy", "cursor-switcher.json"))
    )

    report = {
        "snapshot": has_snapshot,
        "state": has_state,
        "desktop_entry": os.path.isfile(os.path.join(data_home, "applications", "omarchy-cursor-switcher.desktop")),
        "launcher": os.path.isfile(os.path.join(home, ".local", "bin", "omarchy-cursor-switcher")),
        "icon": bool(icon_assets),
        "icon_assets": sorted(icon_assets),
        "uwsm_env_common": managed_fragment(uwsm_common_path),
        "uwsm_env_hyprland": managed_fragment(uwsm_hypr_path),
        "bundled_themes": bundled_themes,
        "converted_themes": converted_themes,
        "imported_themes": imported_themes,
        "cache_previews": os.path.isdir(os.path.join(cache_home, "omarchy-cursor-switcher")),
        "cleanup_helper": os.path.isfile(os.path.join(data_home, "omarchy-cursor-switcher", "omarchy-cursor-switcher-cleanup")),
        "legacy_cleanup_helper": os.path.lexists(os.path.join(data_home, "omarchy", "cursor-switcher"))
    }

    is_clean = not (
        report["snapshot"] or report["state"] or report["desktop_entry"] or
        report["launcher"] or report["icon"] or report["uwsm_env_common"] or
        report["uwsm_env_hyprland"] or bool(report["bundled_themes"]) or
        bool(report["converted_themes"]) or bool(report["imported_themes"]) or
        report["cache_previews"] or report["cleanup_helper"] or report["legacy_cleanup_helper"]
    )
    report["is_clean"] = is_clean
    return report
