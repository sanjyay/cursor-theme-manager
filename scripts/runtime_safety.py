#!/usr/bin/python3
"""
Hardened Process Supervisor & Runtime Safety Utilities for Cursor Theme Manager.
Centralizes bounded external tool execution, process-group management,
wall-clock deadlines, I/O byte limits, and output sanitization.
"""

import sys
import os
import stat
import signal
import time
import json
import selectors
import subprocess
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any, Sequence

# ==============================================================================
# OPERATION BUDGET CONSTANTS
# ==============================================================================

# Timeouts in seconds
TIMEOUT_DISCOVERY = 10.0
TIMEOUT_LIST_DIR = 5.0
TIMEOUT_PREVIEW_ROLES = 5.0
TIMEOUT_ALL_PREVIEW_ROLES = 15.0
TIMEOUT_APPLY = 10.0
TIMEOUT_IMPORT = 120.0
TIMEOUT_CONVERT = 30.0
TIMEOUT_RENAME = 10.0
TIMEOUT_REMOVE = 10.0
TIMEOUT_OPEN_FOLDER = 5.0
TIMEOUT_INTEGRATION = 10.0
TIMEOUT_STATE = 5.0
TIMEOUT_SNAPSHOT = 10.0
TIMEOUT_RESTORE = 10.0

# Hard byte limits for helper output streams
LIMIT_STDOUT_DEFAULT = 1024 * 1024       # 1 MiB
LIMIT_STDERR_DEFAULT = 64 * 1024         # 64 KiB
LIMIT_STDOUT_SMALL = 64 * 1024           # 64 KiB
LIMIT_STDOUT_MEDIUM = 256 * 1024         # 256 KiB
LIMIT_STDOUT_LARGE = 1024 * 1024         # 1 MiB

# Data collection limits
MAX_DISCOVERED_THEMES = 1024
MAX_DIRECTORY_ENTRIES = 2048
MAX_STATE_BYTES = 64 * 1024              # 64 KiB
MAX_SNAPSHOT_BYTES = 64 * 1024           # 64 KiB

# String length limits
MAX_LEN_THEME_ID = 256
MAX_LEN_DISPLAY_NAME = 256
MAX_LEN_SUBTITLE = 1024
MAX_LEN_LICENSE = 128
MAX_LEN_PATH = 4096
MAX_LEN_FILENAME = 255
MAX_LEN_ERROR = 512

# ==============================================================================
# PROCESS GROUP TRACKING & CLEANUP REGISTRY
# ==============================================================================

_active_process_groups = set()
_registry_lock = threading.Lock()
_cleanup_callbacks = []


def register_cleanup_callback(cb):
    with _registry_lock:
        _cleanup_callbacks.append(cb)


def _kill_process_group(pgid: int, grace_period: float = 0.5):
    """Sends SIGTERM, waits grace period, then sends SIGKILL to entire process group."""
    if pgid <= 0:
        return
    try:
        # Avoid killing own group if somehow matching
        if pgid == os.getpgid(0):
            return
    except Exception:
        pass

    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return

    deadline = time.monotonic() + grace_period
    while time.monotonic() < deadline:
        try:
            # Check if any process remains in group
            os.killpg(pgid, 0)
            time.sleep(0.05)
        except (ProcessLookupError, PermissionError, OSError):
            return

    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _signal_handler(signum, frame):
    with _registry_lock:
        pgids = list(_active_process_groups)
        cbs = list(_cleanup_callbacks)
    for pgid in pgids:
        _kill_process_group(pgid, grace_period=0.1)
    for cb in cbs:
        try:
            cb()
        except Exception:
            pass
    sys.exit(128 + signum)


# Register signal handlers once for safety
try:
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
except (ValueError, AttributeError):
    pass  # In non-main thread or unsupported environment


# ==============================================================================
# TRUSTED EXECUTABLE RESOLUTION & SECURE SUBPROCESS ENVIRONMENT
# ==============================================================================

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


def _trusted_directory(path: str, allow_non_root: bool) -> bool:
    """Return True only for a stable, non-writable executable directory."""
    try:
        st = os.stat(path, follow_symlinks=False)
        if not stat.S_ISDIR(st.st_mode):
            return False
        if not allow_non_root and st.st_uid != 0:
            return False
        if allow_non_root and st.st_uid not in (0, os.getuid()):
            return False
        return not bool(st.st_mode & 0o022)
    except OSError:
        return False


def _resolve_executable_from_roots(name: str, roots: Sequence[str] = TRUSTED_BIN_DIRS, allow_non_root: bool = False) -> Optional[str]:
    """
    Internal root-bounded resolver helper.
    Tests may dependency-inject custom roots; production callers always use fixed system roots.
    """
    if not name or not isinstance(name, str):
        return None

    canonical_roots = []
    for root in roots:
        real_root = os.path.realpath(root)
        root_is_trusted = _trusted_directory(real_root, allow_non_root)
        if root_is_trusted and not allow_non_root:
            root_is_trusted = all(
                _trusted_directory(str(parent), False)
                for parent in Path(real_root).parents
            )
        if real_root not in canonical_roots and root_is_trusted:
            canonical_roots.append(real_root)

    if name.startswith("/"):
        candidates = [name]
    else:
        candidates = [os.path.join(d, name) for d in roots]

    for candidate in candidates:
        try:
            real_path = os.path.realpath(candidate)
            containing_root = next((d for d in canonical_roots if real_path.startswith(d + "/")), None)
            if containing_root is None:
                continue
            # Validate any subdirectories below the trusted root too. Returning
            # the canonical target avoids a later lookup through a mutable link.
            relative_parent = os.path.relpath(os.path.dirname(real_path), containing_root)
            current = containing_root
            if relative_parent != ".":
                valid_parent = True
                for component in relative_parent.split(os.sep):
                    current = os.path.join(current, component)
                    if not _trusted_directory(current, allow_non_root):
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
            if not allow_non_root and st.st_uid != 0:
                continue
            if st.st_mode & 0o022:
                continue

            return real_path
        except (OSError, PermissionError):
            continue

    return None


def resolve_system_executable(name: str) -> Optional[str]:
    """
    Production API: Resolves an external system executable from fixed system directories only.
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

    # Revalidate on every launch. A cached pathname is not an executable
    # identity and must never bypass ownership/mode checks after replacement.
    resolved_path = _resolve_executable_from_roots(name, TRUSTED_BIN_DIRS, allow_non_root=False)
    _RESOLVED_TOOL_CACHE[name] = resolved_path
    return resolved_path


def resolve_executable(cmd: str) -> Optional[str]:
    """
    Resolves and validates any executable invoked by CTM.
    If bare name -> resolves via resolve_system_executable.
    If absolute path -> validates against trusted system binary or trusted Python interpreter / plugin script.
    """
    if not cmd or not isinstance(cmd, str):
        return None
    if not cmd.startswith("/"):
        return resolve_system_executable(cmd)

    sys_res = resolve_system_executable(cmd)
    if sys_res is not None:
        return sys_res

    # Check active Python interpreter
    try:
        if os.path.samefile(cmd, sys.executable):
            st = os.stat(cmd)
            if stat.S_ISREG(st.st_mode) and os.access(cmd, os.X_OK):
                if not (st.st_mode & 0o002):
                    return cmd
    except (OSError, ValueError):
        pass

    # Check script strictly within plugin's scripts directory
    try:
        script_dir = str(Path(__file__).resolve().parent)
        real_cmd = os.path.realpath(cmd)
        if real_cmd.startswith(script_dir + "/"):
            st = os.stat(real_cmd)
            if stat.S_ISREG(st.st_mode) and os.access(real_cmd, os.X_OK):
                if st.st_uid in (0, os.getuid()) and not (st.st_mode & 0o022):
                    return real_cmd
    except (OSError, ValueError):
        pass

    return None


def get_secure_subprocess_env(extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Constructs a minimal explicit environment for subprocesses.
    Allowlists only necessary session variables, enforces a safe fixed system PATH,
    and strips dangerous code-injection variables.
    """
    clean_env: Dict[str, str] = {"PATH": SAFE_SYSTEM_PATH}
    for var in ALLOWLISTED_ENV_VARS:
        val = os.environ.get(var)
        if val is not None:
            clean_env[var] = val

    if extra_env:
        for k, v in extra_env.items():
            # Callers may override only variables already in the explicit
            # session allowlist. Unknown loader/runtime knobs stay stripped.
            if k not in ALLOWLISTED_ENV_VARS or k in DANGEROUS_ENV_VARS:
                continue
            clean_env[k] = str(v)

    return clean_env


# ==============================================================================
# BOUNDED SUBPROCESS EXECUTION PRIMITIVE
# ==============================================================================

class BoundedResult:
    def __init__(self, exit_code: int, stdout: bytes, stderr: bytes,
                 timed_out: bool = False, limit_exceeded: bool = False, error: str = ""):
        self.exit_code = exit_code
        self.stdout_bytes = stdout
        self.stderr_bytes = stderr
        self.timed_out = timed_out
        self.limit_exceeded = limit_exceeded
        self.error = error

    @property
    def stdout(self) -> str:
        return self.stdout_bytes.decode("utf-8", errors="replace")

    @property
    def stderr(self) -> str:
        return self.stderr_bytes.decode("utf-8", errors="replace")

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.limit_exceeded


def run_bounded(
    argv: List[str],
    timeout: float = TIMEOUT_APPLY,
    stdout_limit: int = LIMIT_STDOUT_DEFAULT,
    stderr_limit: int = LIMIT_STDERR_DEFAULT,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    input_data: Optional[bytes] = None,
    grace_period: float = 0.5
) -> BoundedResult:
    """
    Executes an external command array inside its own process group with
    strict wall-clock deadline, hard byte limit on stdout/stderr, guaranteed
    process tree cleanup, and reap.
    """
    if not isinstance(argv, (list, tuple)) or not argv:
        raise ValueError("argv must be a non-empty list of strings")
    raw_cmd = str(argv[0])
    resolved_cmd = resolve_executable(raw_cmd)
    if resolved_cmd is None:
        err_text = f"Required system tool '{raw_cmd}' is unavailable or failed validation"
        return BoundedResult(
            exit_code=127,
            stdout=b"",
            stderr=err_text.encode("utf-8"),
            error=err_text
        )

    argv_str = [resolved_cmd] + [str(a) for a in argv[1:]]
    secure_env = get_secure_subprocess_env(env)

    proc = None
    pgid = None
    timed_out = False
    limit_exceeded = False
    error_msg = ""

    stdout_chunks = []
    stderr_chunks = []
    stdout_size = 0
    stderr_size = 0

    try:
        proc = subprocess.Popen(
            argv_str,
            stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=secure_env,
            start_new_session=True  # Creates a new process group/session
        )
        pgid = proc.pid
        with _registry_lock:
            _active_process_groups.add(pgid)

        # Use non-blocking I/O selector
        sel = selectors.DefaultSelector()
        os.set_blocking(proc.stdout.fileno(), False)
        os.set_blocking(proc.stderr.fileno(), False)
        sel.register(proc.stdout, selectors.EVENT_READ, data="stdout")
        sel.register(proc.stderr, selectors.EVENT_READ, data="stderr")
        input_offset = 0
        if input_data is not None and proc.stdin:
            os.set_blocking(proc.stdin.fileno(), False)
            sel.register(proc.stdin, selectors.EVENT_WRITE, data="stdin")

        deadline = time.monotonic() + max(0.1, float(timeout))

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                error_msg = f"Command timed out after {timeout}s: {argv_str[0]}"
                break

            events = sel.select(timeout=min(0.2, max(0.01, remaining)))
            for key, mask in events:
                stream_type = key.data
                if stream_type == "stdin":
                    try:
                        written = os.write(key.fileobj.fileno(), input_data[input_offset:input_offset + 65536])
                        input_offset += written
                    except (BrokenPipeError, OSError):
                        input_offset = len(input_data)
                    if input_offset >= len(input_data):
                        try: sel.unregister(key.fileobj)
                        except Exception: pass
                        try: key.fileobj.close()
                        except Exception: pass
                    continue
                try:
                    chunk = key.fileobj.read(65536)
                except Exception:
                    chunk = b""

                if chunk:
                    if stream_type == "stdout":
                        stdout_size += len(chunk)
                        if stdout_size > stdout_limit:
                            limit_exceeded = True
                            error_msg = f"Command stdout exceeded limit of {stdout_limit} bytes: {argv_str[0]}"
                            break
                        stdout_chunks.append(chunk)
                    elif stream_type == "stderr":
                        stderr_size += len(chunk)
                        if stderr_size > stderr_limit:
                            limit_exceeded = True
                            error_msg = f"Command stderr exceeded limit of {stderr_limit} bytes: {argv_str[0]}"
                            break
                        stderr_chunks.append(chunk)
                else:
                    # Stream closed
                    try:
                        sel.unregister(key.fileobj)
                    except Exception:
                        pass

            if limit_exceeded:
                break

            # Check if process exited and all streams closed
            if proc.poll() is not None and not sel.get_map():
                break

        sel.close()

    except Exception as exc:
        error_msg = f"Subprocess execution error ({argv_str[0]}): {exc}"
    finally:
        if proc is not None:
            if timed_out or limit_exceeded or proc.poll() is None:
                if pgid is not None:
                    _kill_process_group(pgid, grace_period=grace_period)
                try:
                    proc.kill()
                except Exception:
                    pass

            try:
                proc.wait(timeout=1.0)
            except Exception:
                pass

            if proc.stdout:
                try: proc.stdout.close()
                except Exception: pass
            if proc.stderr:
                try: proc.stderr.close()
                except Exception: pass
            if proc.stdin:
                try: proc.stdin.close()
                except Exception: pass

            if pgid is not None:
                with _registry_lock:
                    _active_process_groups.discard(pgid)

    exit_code = proc.returncode if proc and proc.returncode is not None else 1
    if timed_out or limit_exceeded:
        exit_code = 124 if timed_out else 125

    return BoundedResult(
        exit_code=exit_code,
        stdout=b"".join(stdout_chunks),
        stderr=b"".join(stderr_chunks),
        timed_out=timed_out,
        limit_exceeded=limit_exceeded,
        error=error_msg
    )


# ==============================================================================
# SANITIZATION AND BOUNDED JSON EMISSION
# ==============================================================================

def sanitize_text(value: Any, max_len: int = MAX_LEN_DISPLAY_NAME, allow_newlines: bool = False) -> str:
    """Sanitizes dynamic text: removes NUL, replaces control characters, caps length."""
    if value is None:
        return ""
    s = str(value)
    chars = []
    for ch in s:
        code = ord(ch)
        if code == 0:
            continue
        if not allow_newlines and ch in ('\r', '\n', '\t'):
            chars.append(' ')
        elif allow_newlines and ch in ('\r', '\n', '\t'):
            chars.append(ch)
        elif code < 32 or (127 <= code <= 159):
            continue  # Drop control chars
        else:
            chars.append(ch)
    cleaned = "".join(chars).strip()
    if len(cleaned) > max_len:
        return cleaned[:max_len]
    return cleaned


def emit_bounded_json(data: Any, max_bytes: int = LIMIT_STDOUT_DEFAULT, exit_code: int = 0) -> None:
    """
    Serializes data to JSON, verifies byte size BEFORE emitting,
    and returns a small structured error if the limit is exceeded.
    """
    try:
        serialized = json.dumps(data, ensure_ascii=False)
        encoded = serialized.encode("utf-8")
        if len(encoded) > max_bytes:
            err_payload = json.dumps({
                "ok": False,
                "error": "output_limit_exceeded",
                "message": f"Generated output ({len(encoded)} bytes) exceeded budget of {max_bytes} bytes"
            })
            sys.stdout.write(err_payload + "\n")
            sys.stdout.flush()
            sys.exit(1)
        sys.stdout.write(serialized + "\n")
        sys.stdout.flush()
        sys.exit(exit_code)
    except Exception as exc:
        err_payload = json.dumps({
            "ok": False,
            "error": "serialization_error",
            "message": str(exc)
        })
        sys.stdout.write(err_payload + "\n")
        sys.stdout.flush()
        sys.exit(1)
