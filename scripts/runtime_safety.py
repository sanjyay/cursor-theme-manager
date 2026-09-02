#!/usr/bin/env python3
"""
Hardened Process Supervisor & Runtime Safety Utilities for Cursor Theme Manager.
Centralizes bounded external tool execution, process-group management,
wall-clock deadlines, I/O byte limits, and output sanitization.
"""

import sys
import os
import signal
import time
import json
import selectors
import subprocess
import threading
from typing import List, Dict, Optional, Tuple, Any

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
    argv_str = [str(a) for a in argv]

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
            env=env,
            start_new_session=True  # Creates a new process group/session
        )
        pgid = proc.pid
        with _registry_lock:
            _active_process_groups.add(pgid)

        if input_data is not None and proc.stdin:
            try:
                proc.stdin.write(input_data)
                proc.stdin.close()
            except Exception:
                pass

        # Use non-blocking I/O selector
        sel = selectors.DefaultSelector()
        os.set_blocking(proc.stdout.fileno(), False)
        os.set_blocking(proc.stderr.fileno(), False)
        sel.register(proc.stdout, selectors.EVENT_READ, data="stdout")
        sel.register(proc.stderr, selectors.EVENT_READ, data="stderr")

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
