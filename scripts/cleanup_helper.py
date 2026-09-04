#!/usr/bin/python3
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
import hashlib
import fcntl
import signal
import time
import selectors
import subprocess
import shutil
import secrets
from pathlib import Path
from typing import Dict, Optional

PLUGIN_ID = "sanjyay.cursor-theme-manager"
OWNERSHIP_MARKER = "X-CursorThemeManager-Owned=true"

NAME_RE = re.compile(r'^[a-zA-Z0-9_\-\.\ ]+$')


def valid_name(name: str) -> bool:
    if not name or ".." in name:
        return False
    return bool(NAME_RE.match(name))


MAX_CONFIG_BYTES = 131072  # 128 KiB


def open_held_parent_dir(path: str, create: bool = False, create_mode: int = 0o755) -> Optional[int]:
    """
    Safely opens and holds a directory file descriptor for the parent directory of `path`.
    Walks from root '/' component-by-component with O_NOFOLLOW | O_DIRECTORY.
    Validates ownership and permissions of each component:
    - Root or current-user ownership
    - No group/world-writable components (unless root-owned with sticky bit, e.g. /tmp)
    - Final parent directory must be owned by the current user.
    Never follows symlinks. Returns the held directory fd, or None on failure.
    """
    try:
        abs_path = os.path.abspath(path)
        parent_path = os.path.dirname(abs_path)
        parts = Path(parent_path).parts
        if not parts or parts[0] != "/":
            return None

        flags = os.O_RDONLY | os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC

        current_fd = os.open("/", flags)
        try:
            st = os.fstat(current_fd)
            if not stat.S_ISDIR(st.st_mode) or st.st_uid not in (0, os.getuid()):
                os.close(current_fd)
                return None
        except Exception:
            os.close(current_fd)
            return None

        for comp in parts[1:]:
            next_fd = -1
            try:
                try:
                    next_fd = os.open(comp, flags, dir_fd=current_fd)
                except FileNotFoundError:
                    if not create:
                        os.close(current_fd)
                        return None
                    try:
                        os.mkdir(comp, mode=create_mode, dir_fd=current_fd)
                    except FileExistsError:
                        pass
                    except OSError:
                        os.close(current_fd)
                        return None
                    try:
                        next_fd = os.open(comp, flags, dir_fd=current_fd)
                    except OSError:
                        os.close(current_fd)
                        return None
                except OSError:
                    os.close(current_fd)
                    return None

                st = os.fstat(next_fd)
                if not stat.S_ISDIR(st.st_mode):
                    os.close(next_fd)
                    os.close(current_fd)
                    return None

                if st.st_uid not in (0, os.getuid()):
                    os.close(next_fd)
                    os.close(current_fd)
                    return None

                mode = st.st_mode & 0o7777
                if st.st_uid == os.getuid() and (mode & 0o022):
                    os.close(next_fd)
                    os.close(current_fd)
                    return None
                if st.st_uid == 0 and (mode & 0o022) and not (mode & stat.S_ISVTX):
                    os.close(next_fd)
                    os.close(current_fd)
                    return None

                os.close(current_fd)
                current_fd = next_fd
                next_fd = -1
            except Exception:
                if next_fd >= 0:
                    try: os.close(next_fd)
                    except OSError: pass
                if current_fd >= 0:
                    try: os.close(current_fd)
                    except OSError: pass
                return None

        # Verify final parent directory is owned by current user
        try:
            st = os.fstat(current_fd)
            if st.st_uid != os.getuid():
                os.close(current_fd)
                return None
        except Exception:
            os.close(current_fd)
            return None

        return current_fd
    except Exception:
        return None


def safe_read_config_file(parent_fd: int, basename: str, max_bytes: int = MAX_CONFIG_BYTES) -> Optional[str]:
    """
    Safely reads a regular configuration file relative to held parent directory descriptor.
    Enforces non-blocking, non-following descriptor open, regular file check,
    current-user ownership, and strict byte size bounding.
    """
    if parent_fd is None or parent_fd < 0 or not basename or "/" in basename:
        return None

    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    try:
        fd = os.open(basename, flags, dir_fd=parent_fd)
    except OSError:
        return None

    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_size > max_bytes:
            return None
        raw = os.read(fd, max_bytes + 1)
        if len(raw) > max_bytes:
            return None
        return raw.decode("utf-8", errors="replace")
    except (OSError, UnicodeError):
        return None
    finally:
        os.close(fd)


def safe_write_config_file(parent_fd: int, basename: str, content: str, mode: int = 0o644) -> bool:
    """
    Safely writes a regular configuration file relative to held parent directory descriptor.
    Prevents overwriting symlinks or foreign-owned files, writes via private temp file
    relative to held parent, fsyncs data, and replaces atomically.
    """
    if parent_fd is None or parent_fd < 0 or not basename or "/" in basename:
        return False

    data = content.encode("utf-8")
    if len(data) > MAX_CONFIG_BYTES:
        return False

    # Check existing target without following symlinks
    try:
        st_target = os.stat(basename, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(st_target.st_mode) or st_target.st_uid != os.getuid():
            return False
        target_mode = stat.S_IMODE(st_target.st_mode) & 0o666
        if target_mode:
            mode = target_mode
    except FileNotFoundError:
        pass
    except OSError:
        return False

    tmp_name = f".{basename}.tmp.{os.getpid()}_{secrets.token_hex(8)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    try:
        tmp_fd = os.open(tmp_name, flags, mode, dir_fd=parent_fd)
    except OSError:
        return False

    try:
        st_tmp = os.fstat(tmp_fd)
        if not stat.S_ISREG(st_tmp.st_mode) or st_tmp.st_uid != os.getuid():
            raise OSError("Temp file failed ownership or type validation")
        os.fchmod(tmp_fd, mode)
        total = 0
        while total < len(data):
            w = os.write(tmp_fd, data[total:])
            if w == 0:
                raise OSError("Write returned 0 bytes")
            total += w
        os.fsync(tmp_fd)
    except Exception:
        os.close(tmp_fd)
        try:
            os.unlink(tmp_name, dir_fd=parent_fd)
        except OSError:
            pass
        return False
    else:
        os.close(tmp_fd)

    try:
        # Re-check target file is not a symlink or foreign-owned right before replace
        try:
            st_target = os.stat(basename, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISREG(st_target.st_mode) or st_target.st_uid != os.getuid():
                raise OSError("Target file validation failed before replacement")
        except FileNotFoundError:
            pass

        os.replace(tmp_name, basename, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
        return True
    except Exception:
        try:
            os.unlink(tmp_name, dir_fd=parent_fd)
        except OSError:
            pass
        return False


def safe_unlink_config_file(parent_fd: int, basename: str, required_marker: Optional[str] = None) -> bool:
    """
    Safely unlinks a file relative to held parent directory descriptor.
    Verifies that target is a regular file owned by the current user (refusing to unlink symlinks),
    and optionally validates that required_marker is present in content before unlinking.
    """
    if parent_fd is None or parent_fd < 0 or not basename or "/" in basename:
        return False

    try:
        st = os.stat(basename, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
            return False
        if required_marker is not None:
            content = safe_read_config_file(parent_fd, basename)
            if not content or required_marker not in content:
                return False
        os.unlink(basename, dir_fd=parent_fd)
        os.fsync(parent_fd)
        return True
    except Exception:
        return False


TRUSTED_BIN_DIRS = (
    "/usr/bin",
    "/usr/sbin",
    "/usr/local/bin",
    "/usr/local/sbin",
    "/bin",
    "/sbin"
)

SAFE_SYSTEM_PATH = "/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:/bin:/sbin"

ALLOWLISTED_ENV_VARS = (
    "HOME", "USER", "LOGNAME",
    "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_DATA_DIRS",
    "WAYLAND_DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE",
    "DBUS_SESSION_BUS_ADDRESS",
    "LANG", "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "LC_COLLATE", "LC_NUMERIC", "LC_TIME"
)

DANGEROUS_ENV_VARS = {
    "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONOPTIMIZE", "PYTHONDEBUG", "PYTHONEXECUTABLE", "PYTHONUSERBASE",
    "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "LD_DEBUG", "LD_ORIGIN_PATH",
    "BASH_ENV", "ENV", "SHELLOPTS", "BASH_OPTS", "PROMPT_COMMAND",
    "PERL5LIB", "PERLLIB", "RUBYLIB", "NODE_OPTIONS", "IFS"
}

_RESOLVED_TOOL_CACHE: Dict[str, Optional[str]] = {}


def _cleanup_checkpoint(_stage: str) -> None:
    """No-op lifecycle boundary used by deterministic interruption tests."""
    return


def _trusted_directory(path: str) -> bool:
    try:
        st = os.stat(path, follow_symlinks=False)
        return stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and not (st.st_mode & 0o022)
    except OSError:
        return False


def resolve_system_executable(name: str) -> Optional[str]:
    """
    Resolves an external system executable from fixed system directories only.
    Zero environment overrides. Never examines PATH or any environment variable.
    Verifies:
      - regular file
      - executable permissions
      - root-owned (UID 0)
      - not group- or world-writable
      - resolved canonical target also resides under trusted system roots and is root-owned
    Returns canonical path or None if unavailable/invalid.
    """
    if not name or not isinstance(name, str):
        return None

    resolved_path: Optional[str] = None
    canonical_roots = []
    for root in TRUSTED_BIN_DIRS:
        real_root = os.path.realpath(root)
        root_is_trusted = _trusted_directory(real_root) and all(
            _trusted_directory(str(parent)) for parent in Path(real_root).parents
        )
        if real_root not in canonical_roots and root_is_trusted:
            canonical_roots.append(real_root)
    if name.startswith("/"):
        candidates = [name]
    else:
        candidates = [os.path.join(d, name) for d in TRUSTED_BIN_DIRS]

    for candidate in candidates:
        try:
            real_path = os.path.realpath(candidate)
            containing_root = next((d for d in canonical_roots if real_path.startswith(d + "/")), None)
            if containing_root is None:
                continue
            relative_parent = os.path.relpath(os.path.dirname(real_path), containing_root)
            current = containing_root
            valid_parent = True
            if relative_parent != ".":
                for component in relative_parent.split(os.sep):
                    current = os.path.join(current, component)
                    if not _trusted_directory(current):
                        valid_parent = False
                        break
            if not valid_parent:
                continue
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            fd = os.open(real_path, flags)
            try:
                st = os.fstat(fd)
            finally:
                os.close(fd)
            if not stat.S_ISREG(st.st_mode):
                continue
            if not (st.st_mode & 0o111) or not os.access(real_path, os.X_OK):
                continue
            if st.st_uid != 0:
                continue
            if st.st_mode & 0o022:
                continue

            resolved_path = real_path
            break
        except (OSError, PermissionError):
            continue

    _RESOLVED_TOOL_CACHE[name] = resolved_path
    return resolved_path


def get_secure_subprocess_env(extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    clean_env: Dict[str, str] = {"PATH": SAFE_SYSTEM_PATH}
    for var in ALLOWLISTED_ENV_VARS:
        val = os.environ.get(var)
        if val is not None:
            clean_env[var] = val

    if extra_env:
        for k, v in extra_env.items():
            if k not in ALLOWLISTED_ENV_VARS or k in DANGEROUS_ENV_VARS:
                continue
            clean_env[k] = str(v)

    return clean_env


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


class CommandResult:
    def __init__(self, ok=False, exit_code=1, stdout="", stderr="", timed_out=False,
                 limit_exceeded=False, argv=None, error=""):
        self.ok = ok
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.limit_exceeded = limit_exceeded
        self.argv = argv or []
        self.error = error


def run_cmd(args, env_override=None, timeout=3.0, stdout_limit=65536, stderr_limit=65536):
    if not args:
        return CommandResult(error="Empty arguments")
    raw_cmd = str(args[0])
    resolved = resolve_system_executable(raw_cmd)
    if resolved is None:
        error = f"Required system tool '{raw_cmd}' is unavailable or failed validation"
        return CommandResult(exit_code=127, error=error, stderr=error, argv=[raw_cmd])
    cmd_args = [resolved] + [str(a) for a in args[1:]]
    secure_env = get_secure_subprocess_env(env_override)
    proc = None
    stdout_chunks = []
    stderr_chunks = []
    stdout_size = 0
    stderr_size = 0
    timed_out = False
    limit_exceeded = False
    error = ""
    try:
        proc = subprocess.Popen(
            cmd_args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=secure_env, start_new_session=True
        )
        sel = selectors.DefaultSelector()
        for stream, name in ((proc.stdout, "stdout"), (proc.stderr, "stderr")):
            os.set_blocking(stream.fileno(), False)
            sel.register(stream, selectors.EVENT_READ, name)
        deadline = time.monotonic() + max(0.1, float(timeout))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                error = f"command timed out after {timeout}s"
                break
            for key, _ in sel.select(min(0.1, remaining)):
                try:
                    chunk = key.fileobj.read(16384)
                except OSError:
                    chunk = b""
                if not chunk:
                    try: sel.unregister(key.fileobj)
                    except Exception: pass
                    continue
                if key.data == "stdout":
                    stdout_size += len(chunk)
                    if stdout_size > stdout_limit:
                        limit_exceeded = True
                        error = "command stdout exceeded limit"
                        break
                    stdout_chunks.append(chunk)
                else:
                    stderr_size += len(chunk)
                    if stderr_size > stderr_limit:
                        limit_exceeded = True
                        error = "command stderr exceeded limit"
                        break
                    stderr_chunks.append(chunk)
            if limit_exceeded or (proc.poll() is not None and not sel.get_map()):
                break
        sel.close()
    except Exception as e:
        error = str(e)
    finally:
        if proc is not None:
            if timed_out or limit_exceeded or proc.poll() is None:
                try: os.killpg(proc.pid, signal.SIGTERM)
                except OSError: pass
                deadline = time.monotonic() + 0.2
                while proc.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                if proc.poll() is None:
                    try: os.killpg(proc.pid, signal.SIGKILL)
                    except OSError: pass
            try: proc.wait(timeout=0.5)
            except Exception: pass
            for stream in (proc.stdout, proc.stderr):
                if stream:
                    try: stream.close()
                    except OSError: pass
    code = proc.returncode if proc and proc.returncode is not None else 1
    if timed_out:
        code = 124
    elif limit_exceeded:
        code = 125
    stdout = b"".join(stdout_chunks).decode("utf-8", errors="replace")
    stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")
    return CommandResult(
        ok=code == 0 and not timed_out and not limit_exceeded,
        exit_code=code, stdout=stdout, stderr=stderr, timed_out=timed_out,
        limit_exceeded=limit_exceeded, argv=cmd_args, error=error
    )


def log_command_result(stage: str, result: CommandResult) -> None:
    sys.stderr.write(f"cursorctl cleanup: {stage} argv={json.dumps(result.argv)}\n")
    sys.stderr.write(
        f"cursorctl cleanup: {stage} exit={result.exit_code} "
        f"timeout={str(result.timed_out).lower()} output_limit={str(result.limit_exceeded).lower()}\n"
    )
    sys.stderr.write(f"cursorctl cleanup: {stage} stdout={result.stdout.strip()!r}\n")
    sys.stderr.write(f"cursorctl cleanup: {stage} stderr={(result.stderr.strip() or result.error)!r}\n")


def find_hyprland_instance():
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    hypr_dir = Path(xdg_runtime) / "hypr"
    if hypr_dir.is_dir():
        candidates = [
            d.name for d in hypr_dir.iterdir()
            if d.is_dir() and not d.is_symlink() and (d / ".socket.sock").is_socket()
        ]
        # Never guess between multiple compositor sessions.
        if len(candidates) == 1:
            return candidates[0]
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


def read_instance_marker(marker_path: str) -> Optional[str]:
    if not os.path.exists(marker_path):
        return None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(marker_path, flags)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_size > 256:
                return None
            raw = os.read(fd, 256).decode("utf-8", errors="ignore").strip()
            if re.match(r'^[a-fA-F0-9]{16,64}$', raw):
                return raw
            return None
        finally:
            os.close(fd)
    except Exception:
        return None


def read_installation_token(plugin_path: str) -> Optional[str]:
    """Read the same durable per-install token used by the live plugin."""
    dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        dir_flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        dir_flags |= os.O_CLOEXEC
    try:
        dir_fd = os.open(plugin_path, dir_flags)
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


def get_plugin_installation_fingerprint(plugin_path: str) -> Optional[str]:
    token = read_installation_token(plugin_path)
    if token:
        return hashlib.sha256(token.encode("ascii")).hexdigest()
    # Legacy installations did not have a token; retain their inode identity
    # only as a compatibility fallback.
    try:
        st = os.lstat(plugin_path)
        if not (stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode)):
            return None
        identity = f"{st.st_dev}:{st.st_ino}".encode("ascii")
        return hashlib.sha256(identity).hexdigest()
    except OSError:
        return None


def is_file_owned_by_us(filepath: str, expected_instance: Optional[str] = None) -> bool:
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


def marker_contains(path: str, required: str, max_bytes: int = 65536) -> bool:
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_size > max_bytes:
                return False
            content = os.read(fd, max_bytes + 1).decode("utf-8", errors="strict")
            return len(content.encode("utf-8")) <= max_bytes and required in content
        finally:
            os.close(fd)
    except Exception:
        return False


def open_secure_state_dir() -> Optional[int]:
    """Open the existing state directory without following any path symlink."""
    paths = get_paths()
    state_dir = os.path.abspath(paths["state_dir"])
    parts = Path(state_dir).parts
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    current_fd = -1
    try:
        current_fd = os.open("/", flags)
        for i, component in enumerate(parts[1:], 1):
            next_fd = os.open(component, flags, dir_fd=current_fd)
            st = os.fstat(next_fd)
            if not stat.S_ISDIR(st.st_mode) or st.st_uid not in (0, os.getuid()):
                os.close(next_fd)
                raise OSError("untrusted state path component")
            mode = st.st_mode & 0o7777
            if i == len(parts) - 1:
                if st.st_uid != os.getuid() or (mode & 0o777) != 0o700:
                    os.close(next_fd)
                    raise OSError("untrusted state directory")
            elif ((st.st_uid == os.getuid() and mode & 0o022) or
                  (st.st_uid == 0 and mode & 0o022 and not mode & stat.S_ISVTX)):
                os.close(next_fd)
                raise OSError("writable state path component")
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except OSError:
        if current_fd >= 0:
            os.close(current_fd)
        return None


def read_secure_state_snapshot():
    dir_fd = open_secure_state_dir()
    if dir_fd is None:
        return None, None
    try:
        file_flags = os.O_RDONLY | os.O_NONBLOCK
        if hasattr(os, "O_NOFOLLOW"):
            file_flags |= os.O_NOFOLLOW

        file_fd = os.open("state.json", file_flags, dir_fd=dir_fd)
        try:
            fst = os.fstat(file_fd)
            if not stat.S_ISREG(fst.st_mode) or fst.st_uid != os.getuid() or fst.st_size > 65536:
                return None, None
            raw = os.read(file_fd, 65537)
            if len(raw) > 65536:
                return None, None
            data = json.loads(raw.decode("utf-8", errors="strict"))
            return (data, (fst.st_dev, fst.st_ino)) if isinstance(data, dict) else (None, None)
        finally:
            os.close(file_fd)
    except Exception:
        return None, None
    finally:
        os.close(dir_fd)


def read_secure_state():
    state, _identity = read_secure_state_snapshot()
    return state


def state_owned_by_cleanup(state: dict, expected_instance: Optional[str],
                           expected_plugin_fingerprint: Optional[str]) -> bool:
    state_fingerprint = state.get("integrationPluginFingerprint") if state else None
    state_instance = state.get("integrationInstanceId") if state else None
    if expected_plugin_fingerprint and state_fingerprint:
        return state_fingerprint == expected_plugin_fingerprint
    if expected_instance:
        return state_instance == expected_instance
    # Legacy cleanup services did not pass ownership arguments. They may clean
    # the one verified CTM state document only when no newer caller identity
    # was supplied for comparison.
    return True


def remove_secure_state_dir(expected_instance: Optional[str] = None,
                            expected_plugin_fingerprint: Optional[str] = None,
                            expected_identity=None) -> bool:
    """Locked compare-and-delete of only a state document owned by cleanup.

    The inode is diagnostic, not generation ownership. A same-generation
    writer may atomically replace state.json after cleanup's initial read; the
    replacement is still safe to delete when its embedded fingerprint/instance
    remains the expected old owner. A new generation has a different embedded
    fingerprint and is preserved.
    """
    paths = get_paths()
    dir_fd = open_secure_state_dir()
    if dir_fd is None:
        return False
    try:
        fcntl.flock(dir_fd, fcntl.LOCK_EX)
        file_flags = os.O_RDONLY | os.O_NONBLOCK
        if hasattr(os, "O_NOFOLLOW"):
            file_flags |= os.O_NOFOLLOW
        try:
            file_fd = os.open("state.json", file_flags, dir_fd=dir_fd)
        except FileNotFoundError:
            return False
        try:
            fst = os.fstat(file_fd)
            if (not stat.S_ISREG(fst.st_mode) or fst.st_uid != os.getuid() or
                    fst.st_size > 65536):
                return False
            identity = (fst.st_dev, fst.st_ino)
            raw = os.read(file_fd, 65537)
            if len(raw) > 65536:
                return False
            current_state = json.loads(raw.decode("utf-8", errors="strict"))
            if not isinstance(current_state, dict) or not state_owned_by_cleanup(
                    current_state, expected_instance, expected_plugin_fingerprint):
                return False
            if expected_identity is not None and identity != tuple(expected_identity):
                sys.stderr.write(
                    "cursorctl cleanup: state inode changed but remains owned by the old installation; deleting replacement\n"
                )
            current = os.stat("state.json", dir_fd=dir_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != identity:
                return False
            os.unlink("state.json", dir_fd=dir_fd)
        finally:
            os.close(file_fd)
        os.fsync(dir_fd)
        held = os.fstat(dir_fd)
        current = os.lstat(paths["state_dir"])
        if (current.st_dev, current.st_ino) == (held.st_dev, held.st_ino):
            os.rmdir(paths["state_dir"])
        return True
    except OSError:
        return False
    except (UnicodeError, json.JSONDecodeError):
        return False
    finally:
        try:
            fcntl.flock(dir_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(dir_fd)


def recovery_actor_active() -> bool:
    """Return true only if cursor-theme-manager-cleanup.service is actively executing or indeterminate."""
    res = run_cmd(["systemctl", "--user", "is-active", "cursor-theme-manager-cleanup.service"], timeout=1.0)
    if res.timed_out or res.limit_exceeded:
        return True
    return bool(res.ok and res.stdout.strip() in ("active", "activating"))


def recovery_artifacts_present(expected_instance: Optional[str]) -> bool:
    """Return true when an installed cleanup actor can still process recovery."""
    paths = get_paths()
    candidates = (paths["cleanup_exe"], paths["path_unit"], paths["service_unit"])
    has_files = any(
        os.path.exists(path) and is_file_owned_by_us(path, expected_instance)
        for path in candidates
    )
    return has_files and recovery_actor_active()


def safe_unlink_owned_artifact(path: str, expected_instance: Optional[str] = None) -> bool:
    """Safely unlinks a CTM artifact via held parent descriptor, refusing symlinks and unowned files."""
    if not os.path.lexists(path):
        return True
    if not is_file_owned_by_us(path, expected_instance):
        return False
    parent_fd = open_held_parent_dir(path, create=False)
    if parent_fd is None:
        return False
    try:
        basename = os.path.basename(path)
        marker = f"X-CursorThemeManager-Instance={expected_instance}" if expected_instance else OWNERSHIP_MARKER
        if not safe_unlink_config_file(parent_fd, basename, required_marker=marker):
            return safe_unlink_config_file(parent_fd, basename, required_marker=OWNERSHIP_MARKER)
        return True
    finally:
        os.close(parent_fd)


def safe_rmdir_path(dirpath: str) -> bool:
    """Safely removes an empty directory via held parent descriptor, refusing symlinks."""
    if not os.path.lexists(dirpath):
        return True
    parent_fd = open_held_parent_dir(dirpath, create=False)
    if parent_fd is None:
        return False
    try:
        basename = os.path.basename(dirpath)
        st = os.stat(basename, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
            return False
        os.rmdir(basename, dir_fd=parent_fd)
        os.fsync(parent_fd)
        return True
    except OSError:
        return False
    finally:
        os.close(parent_fd)


def retire_old_instance_artifacts(expected_instance: Optional[str] = None) -> None:
    """Safely retire persistent artifacts left behind by an uninstalled or failed installation."""
    paths = get_paths()
    if os.path.lexists(paths["path_unit"]):
        run_cmd(["systemctl", "--user", "stop", "cursor-theme-manager-cleanup.path"])
        run_cmd(["systemctl", "--user", "disable", "cursor-theme-manager-cleanup.path"])
        safe_unlink_owned_artifact(paths["path_unit"], expected_instance)

    if os.path.lexists(paths["service_unit"]):
        safe_unlink_owned_artifact(paths["service_unit"], expected_instance)

    run_cmd(["systemctl", "--user", "daemon-reload"])
    run_cmd(["systemctl", "--user", "reset-failed", "cursor-theme-manager-cleanup.service"])

    if os.path.lexists(paths["cleanup_exe"]):
        safe_unlink_owned_artifact(paths["cleanup_exe"], expected_instance)

    if os.path.lexists(paths["libexec_dir"]):
        safe_rmdir_path(paths["libexec_dir"])

    if os.path.lexists(paths["desktop_file"]):
        if safe_unlink_owned_artifact(paths["desktop_file"], expected_instance):
            if resolve_system_executable("update-desktop-database"):
                run_cmd(["update-desktop-database", "-q", os.path.dirname(paths["desktop_file"])])


def reconcile_orphaned_state(current_plugin_fingerprint: str) -> dict:
    """Finish verified recovery when no old cleanup actor remains.

    This is called by the newly installed plugin while its UI is quarantined.
    It never adopts old state. It restores the immutable old baseline first,
    then compare-deletes only that old generation's state document.
    """
    paths = get_paths()
    current_fingerprint = get_plugin_installation_fingerprint(paths["plugin_dir"])
    if (not re.fullmatch(r"[a-f0-9]{64}", str(current_plugin_fingerprint or "")) or
            current_fingerprint != current_plugin_fingerprint):
        return {"ok": False, "error": "Current installation identity changed during recovery."}

    state, state_identity = read_secure_state_snapshot()
    if not state:
        return {"ok": True, "reconciled": False, "reason": "no-state"}
    old_fingerprint = state.get("integrationPluginFingerprint")
    old_instance = state.get("integrationInstanceId")
    if not old_fingerprint or old_fingerprint == current_plugin_fingerprint:
        return {"ok": True, "reconciled": False, "reason": "current-state"}
    if recovery_artifacts_present(old_instance):
        return {
            "ok": False, "recoveryPending": True,
            "error": "The previous installation cleanup is still available."
        }

    cursor_modified = bool(state.get("cursorModifiedByCtm"))
    baseline = state.get("preCtmCursor") or state.get("originalCursor")
    if cursor_modified and not (isinstance(baseline, dict) and baseline.get("captured")):
        return {
            "ok": False,
            "error": "The previous installation changed the cursor but its recovery baseline is incomplete."
        }
    if cursor_modified and not restore_cursor(baseline):
        return {"ok": False, "error": "Could not restore the previous installation's cursor baseline."}

    if not remove_secure_state_dir(old_instance, old_fingerprint, state_identity):
        latest, _ = read_secure_state_snapshot()
        if latest and state_owned_by_cleanup(latest, old_instance, old_fingerprint):
            return {"ok": False, "error": "Could not retire the previous installation's recovery state."}
        # A concurrently published current-generation document must never be
        # deleted. Its presence means reconciliation already completed.
        if latest and latest.get("integrationPluginFingerprint") == current_plugin_fingerprint:
            return {"ok": True, "reconciled": False, "reason": "current-state-published"}
        if latest:
            return {"ok": False, "recoveryPending": True, "error": "Recovery ownership changed; retry shortly."}

    retire_old_instance_artifacts(old_instance)

    return {"ok": True, "reconciled": True, "retiredPluginFingerprint": old_fingerprint}


def restore_cursor(orig) -> bool:
    """Restore every required persistent stage, then the live compositor."""
    if not isinstance(orig, dict) or not orig.get("captured"):
        return False

    live_theme = orig.get("liveRestoreTheme") or orig.get("liveTheme")
    live_size = orig.get("liveRestoreSize") or orig.get("liveSize") or 24
    live_backend = orig.get("liveRestoreBackend") or orig.get("liveBackend") or "unknown"
    sys.stderr.write("cursorctl cleanup: baseline_state_loaded=true\n")
    sys.stderr.write(f"cursorctl cleanup: baseline_live_backend={live_backend!r}\n")
    sys.stderr.write(f"cursorctl cleanup: baseline_live_theme={live_theme!r}\n")
    sys.stderr.write(f"cursorctl cleanup: baseline_live_size={live_size!r}\n")

    all_persistent_ok = True

    # 1. GTK / gsettings persistent configuration.
    if orig.get("gtkThemeSet") and orig.get("gtkTheme"):
        theme_result = run_cmd(["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", str(orig["gtkTheme"])])
    elif orig.get("xcursorThemeSet") and orig.get("xcursorTheme"):
        theme_result = run_cmd(["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", str(orig["xcursorTheme"])])
    else:
        theme_result = run_cmd(["gsettings", "reset", "org.gnome.desktop.interface", "cursor-theme"])
    log_command_result("gsettings_theme_restore", theme_result)
    all_persistent_ok = all_persistent_ok and theme_result.ok

    if orig.get("gtkSizeSet") and orig.get("gtkSize"):
        size_result = run_cmd(["gsettings", "set", "org.gnome.desktop.interface", "cursor-size", str(orig["gtkSize"])])
    elif orig.get("xcursorSizeSet") and orig.get("xcursorSize"):
        size_result = run_cmd(["gsettings", "set", "org.gnome.desktop.interface", "cursor-size", str(orig["xcursorSize"])])
    else:
        size_result = run_cmd(["gsettings", "reset", "org.gnome.desktop.interface", "cursor-size"])
    log_command_result("gsettings_size_restore", size_result)
    all_persistent_ok = all_persistent_ok and size_result.ok

    # 2. Systemd & DBus user environment (exact original state).
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
        systemd_set = run_cmd(["systemctl", "--user", "set-environment"] + set_env)
        dbus_set = run_cmd(["dbus-update-activation-environment", "--systemd"] + set_env)
        log_command_result("systemd_environment_set", systemd_set)
        log_command_result("dbus_environment_set", dbus_set)
        all_persistent_ok = all_persistent_ok and systemd_set.ok and dbus_set.ok
    if unset_env:
        systemd_unset = run_cmd(["systemctl", "--user", "unset-environment"] + unset_env)
        log_command_result("systemd_environment_unset", systemd_unset)
        all_persistent_ok = all_persistent_ok and systemd_unset.ok

    # 3. Remove only CTM-owned UWSM persistence files.
    paths = get_paths()
    uwsm_ok = True
    for uwsm_path in (paths["uwsm_common"], paths["uwsm_hypr"]):
        if not os.path.lexists(uwsm_path):
            continue
        parent_fd = open_held_parent_dir(uwsm_path, create=False)
        if parent_fd is None:
            uwsm_ok = False
            sys.stderr.write(f"cursorctl cleanup: UWSM restore refused unsafe path {uwsm_path!r}\n")
            continue
        try:
            basename = os.path.basename(uwsm_path)
            if not safe_unlink_config_file(parent_fd, basename, required_marker="Managed by sanjyay.cursor-theme-manager"):
                uwsm_ok = False
                sys.stderr.write(f"cursorctl cleanup: UWSM restore refused unowned file {uwsm_path!r}\n")
        finally:
            os.close(parent_fd)
    sys.stderr.write(f"cursorctl cleanup: uwsm_restore_ok={str(uwsm_ok).lower()}\n")
    all_persistent_ok = all_persistent_ok and uwsm_ok

    # 3b. Restore X11 index.theme, GTK settings.ini, and X11 RESOURCE_MANAGER
    home = paths.get("home", os.path.expanduser("~"))
    data_home = paths.get("data_home", os.path.join(home, ".local", "share"))
    config_home = paths.get("config_home", os.path.join(home, ".config"))

    restore_xcursor = orig.get("xcursorTheme") or orig.get("gtkTheme")
    restore_gtk_size = orig.get("gtkSize") or orig.get("xcursorSize")
    clean_restore_size = None
    if restore_gtk_size:
        try:
            val_size = int(restore_gtk_size)
            if 16 <= val_size <= 256:
                clean_restore_size = val_size
        except (ValueError, TypeError):
            pass

    valid_restore_xcursor = bool(restore_xcursor and valid_name(restore_xcursor))

    for base in [os.path.join(home, ".icons", "default"), os.path.join(data_home, "icons", "default")]:
        theme_file = os.path.join(base, "index.theme")
        parent_fd = open_held_parent_dir(theme_file, create=False)
        if parent_fd is None:
            continue
        try:
            content = safe_read_config_file(parent_fd, "index.theme")
            if content and "Managed by sanjyay.cursor-theme-manager" in content:
                if valid_restore_xcursor:
                    new_content = (
                        "[Icon Theme]\n"
                        "Name=Default\n"
                        "Comment=Default Cursor Theme\n"
                        f"Inherits={restore_xcursor}\n"
                    )
                    safe_write_config_file(parent_fd, "index.theme", new_content, 0o644)
                else:
                    safe_unlink_config_file(parent_fd, "index.theme", required_marker="Managed by sanjyay.cursor-theme-manager")
        finally:
            os.close(parent_fd)

    for gtk_dir in ["gtk-3.0", "gtk-4.0"]:
        settings_file = os.path.join(config_home, gtk_dir, "settings.ini")
        parent_fd = open_held_parent_dir(settings_file, create=False)
        if parent_fd is None:
            continue
        try:
            content = safe_read_config_file(parent_fd, "settings.ini")
            if content is not None:
                lines = content.splitlines(keepends=True)
                new_lines = []
                in_settings = False
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith("[") and stripped.endswith("]"):
                        in_settings = (stripped.lower() == "[settings]")
                    elif in_settings:
                        if stripped.startswith("gtk-cursor-theme-name") and valid_restore_xcursor:
                            new_lines.append(f"gtk-cursor-theme-name={restore_xcursor}\n")
                            continue
                        elif stripped.startswith("gtk-cursor-theme-size") and clean_restore_size:
                            new_lines.append(f"gtk-cursor-theme-size={clean_restore_size}\n")
                            continue
                    new_lines.append(line)
                safe_write_config_file(parent_fd, "settings.ini", "".join(new_lines), 0o644)
        finally:
            os.close(parent_fd)

    gtk2_file = os.path.join(home, ".gtkrc-2.0")
    parent_fd = open_held_parent_dir(gtk2_file, create=False)
    if parent_fd is not None:
        try:
            content = safe_read_config_file(parent_fd, ".gtkrc-2.0")
            if content is not None:
                lines = content.splitlines(keepends=True)
                new_lines = []
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith("gtk-cursor-theme-name") and valid_restore_xcursor:
                        new_lines.append(f'gtk-cursor-theme-name="{restore_xcursor}"\n')
                        continue
                    elif stripped.startswith("gtk-cursor-theme-size") and clean_restore_size:
                        new_lines.append(f'gtk-cursor-theme-size={clean_restore_size}\n')
                        continue
                    new_lines.append(line)
                safe_write_config_file(parent_fd, ".gtkrc-2.0", "".join(new_lines), 0o644)
        finally:
            os.close(parent_fd)

    display = os.environ.get("DISPLAY")
    if display:
        try:
            import ctypes
            x11 = ctypes.CDLL("libX11.so.6")
            x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            x11.XOpenDisplay.restype = ctypes.c_void_p
            x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            x11.XDefaultRootWindow.restype = ctypes.c_ulong
            x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
            x11.XInternAtom.restype = ctypes.c_ulong
            x11.XChangeProperty.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
                ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int
            ]
            x11.XChangeProperty.restype = ctypes.c_int
            x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
            x11.XSync.restype = ctypes.c_int
            x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
            x11.XCloseDisplay.restype = ctypes.c_int

            dpy = x11.XOpenDisplay(None)
            if dpy:
                try:
                    root = x11.XDefaultRootWindow(dpy)
                    prop = x11.XInternAtom(dpy, b"RESOURCE_MANAGER", 0)
                    string_atom = x11.XInternAtom(dpy, b"STRING", 0)
                    res_parts = []
                    if valid_restore_xcursor:
                        res_parts.append(f"Xcursor.theme: {restore_xcursor}\n")
                    if clean_restore_size:
                        res_parts.append(f"Xcursor.size: {clean_restore_size}\n")
                    data = "".join(res_parts).encode("utf-8")
                    x11.XChangeProperty(dpy, root, prop, string_atom, 8, 0, data, len(data))
                    x11.XSync(dpy, 0)
                finally:
                    x11.XCloseDisplay(dpy)
        except Exception:
            pass

    # 4. LIVE transition is mandatory and deliberately last. Persistent
    # environment values are not a substitute for changing the visible cursor.
    inherited_sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    sig = find_hyprland_instance()
    hyprctl_path = resolve_system_executable("hyprctl")
    for env_name in ("HOME", "XDG_RUNTIME_DIR", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS"):
        sys.stderr.write(f"cursorctl cleanup: env_{env_name}={os.environ.get(env_name)!r}\n")
    sys.stderr.write(f"cursorctl cleanup: env_HYPRLAND_INSTANCE_SIGNATURE={inherited_sig!r}\n")
    sig_source = "inherited" if sig and inherited_sig else ("runtime-scan" if sig else "missing")
    sys.stderr.write(f"cursorctl cleanup: HYPRLAND_INSTANCE_SIGNATURE_available={str(bool(sig)).lower()} source={sig_source}\n")
    sys.stderr.write(f"cursorctl cleanup: trusted_hyprctl={hyprctl_path!r}\n")

    if not isinstance(live_theme, str) or not re.fullmatch(r"[a-zA-Z0-9_. +\-]{1,128}", live_theme):
        sys.stderr.write("cursorctl cleanup: invalid or missing live restore theme; preserving recovery state\n")
        return False
    try:
        live_size = int(live_size)
    except (TypeError, ValueError):
        live_size = 0
    if not 16 <= live_size <= 256:
        sys.stderr.write("cursorctl cleanup: invalid live restore size; preserving recovery state\n")
        return False
    if not has_cursor_data(live_theme):
        sys.stderr.write(f"cursorctl cleanup: original live theme {live_theme!r} is unavailable; preserving recovery state\n")
        return False
    if not sig or not hyprctl_path:
        sys.stderr.write("cursorctl cleanup: live Hyprland target unavailable; preserving recovery state\n")
        return False

    live_result = run_cmd(
        [hyprctl_path, "setcursor", live_theme, str(live_size)],
        env_override={"HYPRLAND_INSTANCE_SIGNATURE": sig}
    )
    log_command_result("hyprctl_live_restore", live_result)
    live_ok = live_result.ok
    sys.stderr.write(f"cursorctl cleanup: persistent_restore_ok={str(all_persistent_ok).lower()}\n")
    sys.stderr.write(f"cursorctl cleanup: live_restore_ok={str(live_ok).lower()}\n")
    return all_persistent_ok and live_ok


def execute_cleanup(expected_instance: Optional[str] = None,
                    expected_plugin_fingerprint: Optional[str] = None):
    paths = get_paths()
    plugin_exists = os.path.exists(paths["plugin_dir"])

    if plugin_exists:
        current_fingerprint = get_plugin_installation_fingerprint(paths["plugin_dir"])
        if expected_plugin_fingerprint and current_fingerprint == expected_plugin_fingerprint:
            # Same installation is alive and active; watcher event was for another plugin
            sys.exit(0)
        elif not expected_plugin_fingerprint:
            # Backward compatibility for cleanup services installed by a
            # marker-based CTM release.
            marker_path = os.path.join(paths["plugin_dir"], ".installation_instance")
            current_marker = read_instance_marker(marker_path)
            if (expected_instance and current_marker == expected_instance) or (
                    not expected_instance and current_marker is not None):
                sys.exit(0)

        # If plugin_exists BUT current_marker != expected_instance:
        # The installation that scheduled this cleanup was removed, and a new installation appeared!
        # Proceed with cleanup of old instance persistent artifacts.

    # Read state
    state, state_identity = read_secure_state_snapshot()
    _cleanup_checkpoint("after-state-load")

    # If state is missing because cleanup already ran, exit cleanly
    if state is None and not os.path.exists(paths["desktop_file"]) and not os.path.exists(paths["path_unit"]):
        sys.exit(0)

    # State belongs to this cleanup if:
    # 1. No expected_instance was specified, OR
    # 2. State has no instance or matches expected_instance, OR
    # 3. Plugin directory is completely absent.
    state_belongs_to_this_cleanup = bool(
        state and state_owned_by_cleanup(state, expected_instance, expected_plugin_fingerprint)
    )

    if state_belongs_to_this_cleanup:
        cursor_modified = state.get("cursorModifiedByCtm", False) if state else False
        orig_c = (state.get("preCtmCursor") or state.get("originalCursor")) if state else None

        if cursor_modified:
            if not orig_c or not orig_c.get("captured"):
                sys.stderr.write("cursorctl: critical error: CTM modified cursor but preCtmCursor baseline is missing or uncaptured. Preserving state and helper for recovery.\n")
                sys.exit(1)

        if orig_c and orig_c.get("captured"):
            restore_ok = restore_cursor(orig_c)
            if not restore_ok:
                sys.stderr.write("cursorctl: critical failure restoring cursor baseline; preserving state for retry.\n")
                sys.exit(1)

        # Remove state directory (state.json)
        _cleanup_checkpoint("before-compare-delete")
        if not remove_secure_state_dir(expected_instance, expected_plugin_fingerprint, state_identity):
            latest_state, _latest_identity = read_secure_state_snapshot()
            if latest_state and state_owned_by_cleanup(
                    latest_state, expected_instance, expected_plugin_fingerprint):
                sys.stderr.write("cursorctl: cleanup could not retire its owned recovery state; preserving helper for retry\n")
                sys.exit(1)
            sys.stderr.write("cursorctl cleanup: state ownership changed before deletion; preserving current installation state\n")
        _cleanup_checkpoint("after-compare-delete")

    _cleanup_checkpoint("before-artifact-cleanup")
    # Remove marker-owned desktop file (if matching expected_instance or stale)
    if os.path.lexists(paths["desktop_file"]):
        if safe_unlink_owned_artifact(paths["desktop_file"], expected_instance):
            if resolve_system_executable("update-desktop-database"):
                run_cmd(["update-desktop-database", "-q", os.path.dirname(paths["desktop_file"])])

    # Self-cleanup: remove systemd units and cleanup executable
    if os.path.lexists(paths["path_unit"]):
        run_cmd(["systemctl", "--user", "stop", "cursor-theme-manager-cleanup.path"])
        run_cmd(["systemctl", "--user", "disable", "cursor-theme-manager-cleanup.path"])
        safe_unlink_owned_artifact(paths["path_unit"], expected_instance)

    if os.path.lexists(paths["service_unit"]):
        safe_unlink_owned_artifact(paths["service_unit"], expected_instance)

    run_cmd(["systemctl", "--user", "daemon-reload"])

    # Unlink own executable and remove libexec directory
    if os.path.lexists(paths["cleanup_exe"]):
        safe_unlink_owned_artifact(paths["cleanup_exe"], expected_instance)

    if os.path.lexists(paths["libexec_dir"]):
        safe_rmdir_path(paths["libexec_dir"])

    # Clean up CTM-generated internal conversion caches
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
                    if marker_contains(imp_marker1, '"kind": "imported-user-theme"') or marker_contains(imp_marker2, '"kind": "imported-user-theme"'):
                        continue

                    # Delete ONLY if verified as CTM-generated internal conversion cache
                    managed_name = (entry.startswith("CursorSwitcher-XCursor-") or
                                    entry.startswith("CursorSwitcher-Themed-"))
                    if managed_name and (marker_contains(gen_marker, "kind=conversion-cache") or
                                         marker_contains(legacy_conv, "1.0")):
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
    expected_instance = None
    expected_plugin_fingerprint = None
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--instance" and i + 1 < len(sys.argv):
            expected_instance = sys.argv[i+1]
            i += 2
        elif sys.argv[i] == "--plugin-fingerprint" and i + 1 < len(sys.argv):
            expected_plugin_fingerprint = sys.argv[i+1]
            i += 2
        else:
            i += 1
    execute_cleanup(
        expected_instance=expected_instance,
        expected_plugin_fingerprint=expected_plugin_fingerprint
    )
