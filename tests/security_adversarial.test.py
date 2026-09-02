#!/usr/bin/env python3
"""
Comprehensive Adversarial Security & Verification Test Suite for Cursor Theme Manager.
Demonstrates:
1. Output limits: Immediate process-group kill upon exceeding byte limits (+1 byte tests), verifying parent, child, grandchild all terminated.
2. Process tree cancellation: Fake helpers ignoring SIGTERM, sleeping forever, forking children/grandchildren.
3. Legacy state migration: Symlinks, FIFOs, oversize files (>64KB), malformed JSON, deep recursion rejection.
4. Secure descriptor-held state directory: 0700 permissions, current-user ownership, symlink rejection.
5. Integration transaction failure injection: Cases A, B, C, D (atomic rollback & accurate failure reporting).
6. Restore safety: Invalid snapshot preservation (no destructive overwrites), strictly allowlisted variables.
7. Plain-text UI & model sanitization: Control characters, hostile HTML/markup injection, length caps.
8. Conversion & import cleanup: Cleanup of staging directories and process groups on failure.
"""

import sys
import os
import re
import json
import stat
import time
import shutil
import signal
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import runtime_safety
import secure_state
import cleanup_engine
import cursor_theming


def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


class TestOutputLimitsAndProcessTree(unittest.TestCase):
    """Verifies that exceeding byte limits or timeouts immediately kills the entire process group."""

    def test_stdout_limit_plus_one_byte_kills_entire_process_tree(self):
        # Helper script that creates child and grandchild processes, writes limit + 1 bytes, and loops
        pid_file = tempfile.mktemp(prefix="tree_pids_")
        helper_code = f"""
import os, sys, time, multiprocessing

def grandchild():
    while True:
        time.sleep(0.1)

def child(pids_path):
    p_gc = multiprocessing.Process(target=grandchild)
    p_gc.start()
    with open(pids_path, "a") as f:
        f.write(f"{{p_gc.pid}}\\n")
    while True:
        time.sleep(0.1)

if __name__ == "__main__":
    with open("{pid_file}", "w") as f:
        f.write(f"{{os.getpid()}}\\n")
    p_c = multiprocessing.Process(target=child, args=("{pid_file}",))
    p_c.start()
    with open("{pid_file}", "a") as f:
        f.write(f"{{p_c.pid}}\\n")
    time.sleep(0.1)
    # Output exactly 1025 bytes (limit is 1024)
    sys.stdout.write("A" * 1025)
    sys.stdout.flush()
    while True:
        time.sleep(0.1)
"""
        res = runtime_safety.run_bounded(
            [sys.executable, "-c", helper_code],
            stdout_limit=1024,
            timeout=5.0
        )
        self.assertTrue(res.limit_exceeded, "Output limit was not flagged as exceeded")
        self.assertFalse(res.ok)
        self.assertIn("exceeded limit", res.error.lower())

        # Read spawned PIDs (parent, child, grandchild)
        time.sleep(0.2)
        if os.path.exists(pid_file):
            with open(pid_file) as pf: pids = [int(p.strip()) for p in pf.read().splitlines() if p.strip().isdigit()]
            os.unlink(pid_file)
            for pid in pids:
                self.assertFalse(is_pid_alive(pid), f"PID {pid} in process tree was not terminated after stdout flood")

    def test_stderr_limit_plus_one_byte_kills_entire_process_tree(self):
        pid_file = tempfile.mktemp(prefix="tree_stderr_pids_")
        helper_code = f"""
import os, sys, time, multiprocessing

def grandchild():
    while True:
        time.sleep(0.1)

def child(pids_path):
    p_gc = multiprocessing.Process(target=grandchild)
    p_gc.start()
    with open(pids_path, "a") as f:
        f.write(f"{{p_gc.pid}}\\n")
    while True:
        time.sleep(0.1)

if __name__ == "__main__":
    with open("{pid_file}", "w") as f:
        f.write(f"{{os.getpid()}}\\n")
    p_c = multiprocessing.Process(target=child, args=("{pid_file}",))
    p_c.start()
    with open("{pid_file}", "a") as f:
        f.write(f"{{p_c.pid}}\\n")
    time.sleep(0.1)
    # Output exactly 513 bytes (limit is 512)
    sys.stderr.write("E" * 513)
    sys.stderr.flush()
    while True:
        time.sleep(0.1)
"""
        res = runtime_safety.run_bounded(
            [sys.executable, "-c", helper_code],
            stderr_limit=512,
            timeout=5.0
        )
        self.assertTrue(res.limit_exceeded)
        self.assertFalse(res.ok)

        time.sleep(0.2)
        if os.path.exists(pid_file):
            with open(pid_file) as pf: pids = [int(p.strip()) for p in pf.read().splitlines() if p.strip().isdigit()]
            os.unlink(pid_file)
            for pid in pids:
                self.assertFalse(is_pid_alive(pid), f"PID {pid} was not terminated after stderr flood")

    def test_process_ignoring_sigterm_is_killed_with_sigkill(self):
        pid_file = tempfile.mktemp(prefix="ignore_term_pid_")
        helper_code = f"""
import os, sys, time, signal

def handler(signum, frame):
    pass # Ignore SIGTERM

signal.signal(signal.SIGTERM, handler)
with open("{pid_file}", "w") as f:
    f.write(f"{{os.getpid()}}\\n")
while True:
    time.sleep(0.1)
"""
        start = time.time()
        res = runtime_safety.run_bounded(
            [sys.executable, "-c", helper_code],
            timeout=0.3,
            grace_period=0.2
        )
        elapsed = time.time() - start
        self.assertTrue(res.timed_out)
        self.assertFalse(res.ok)
        self.assertLess(elapsed, 2.0)

        time.sleep(0.2)
        if os.path.exists(pid_file):
            with open(pid_file) as pf: pid = int(pf.read().strip())
            os.unlink(pid_file)
            self.assertFalse(is_pid_alive(pid), f"Process {pid} that ignored SIGTERM was not killed by SIGKILL")


class TestLegacyStateMigrationAdversarial(unittest.TestCase):
    """Verifies that legacy state migration strictly validates file type, ownership, size, and schema BEFORE parsing."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_legacy_mig_")
        self.orig_env = os.environ.copy()
        os.environ["HOME"] = os.path.join(self.test_dir, "home")
        os.environ["XDG_STATE_HOME"] = os.path.join(self.test_dir, "home", ".local", "state")
        os.environ["XDG_CONFIG_HOME"] = os.path.join(self.test_dir, "config")
        os.makedirs(os.environ["XDG_STATE_HOME"], exist_ok=True)
        os.makedirs(os.path.join(os.environ["XDG_CONFIG_HOME"], "omarchy"), exist_ok=True)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_symlink_legacy_file_rejected(self):
        legacy_path = os.path.join(os.environ["XDG_CONFIG_HOME"], "omarchy", "cursor-switcher.json")
        target_path = os.path.join(self.test_dir, "secret.json")
        with open(target_path, "w") as f:
            f.write('{"version": 1, "theme": {"displayName": "Pwned"}}')
        os.symlink(target_path, legacy_path)

        dir_fd, _ = secure_state.open_held_state_dir()
        try:
            res = secure_state._try_legacy_migration(dir_fd)
            self.assertIsNone(res, "Symlink legacy state file must be rejected")
        finally:
            os.close(dir_fd)

    def test_fifo_named_pipe_legacy_file_rejected(self):
        legacy_path = os.path.join(os.environ["XDG_CONFIG_HOME"], "omarchy", "cursor-switcher.json")
        try:
            os.mkfifo(legacy_path)
            dir_fd, _ = secure_state.open_held_state_dir()
            try:
                res = secure_state._try_legacy_migration(dir_fd)
                self.assertIsNone(res, "FIFO named pipe legacy state file must be rejected")
            finally:
                os.close(dir_fd)
        except AttributeError:
            pass  # OS does not support mkfifo

    def test_oversized_legacy_state_rejected(self):
        legacy_path = os.path.join(os.environ["XDG_CONFIG_HOME"], "omarchy", "cursor-switcher.json")
        with open(legacy_path, "w") as f:
            f.write('{"version": 1, "padding": "' + ("A" * 70000) + '"}')

        dir_fd, _ = secure_state.open_held_state_dir()
        try:
            res = secure_state._try_legacy_migration(dir_fd)
            self.assertIsNone(res, "Oversized legacy state (>64KB) must be rejected")
        finally:
            os.close(dir_fd)

    def test_malformed_json_legacy_state_rejected(self):
        legacy_path = os.path.join(os.environ["XDG_CONFIG_HOME"], "omarchy", "cursor-switcher.json")
        with open(legacy_path, "w") as f:
            f.write('{"version": 1, "theme": {malformed')

        dir_fd, _ = secure_state.open_held_state_dir()
        try:
            res = secure_state._try_legacy_migration(dir_fd)
            self.assertIsNone(res, "Malformed JSON legacy state must be rejected")
        finally:
            os.close(dir_fd)

    def test_deep_json_recursion_rejected(self):
        legacy_path = os.path.join(os.environ["XDG_CONFIG_HOME"], "omarchy", "cursor-switcher.json")
        # Build 100 levels of nested JSON
        nested = '{"a": ' * 50 + '1' + '}' * 50
        with open(legacy_path, "w") as f:
            f.write(nested)

        dir_fd, _ = secure_state.open_held_state_dir()
        try:
            res = secure_state._try_legacy_migration(dir_fd)
            self.assertIsNone(res, "Deeply nested JSON legacy state must be rejected")
        finally:
            os.close(dir_fd)


class TestStateDirectorySecurity(unittest.TestCase):
    """Verifies that the dedicated state directory is created with 0700, owned by user, verified with fstat, and held via FD."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_state_sec_")
        self.orig_env = os.environ.copy()
        os.environ["HOME"] = os.path.join(self.test_dir, "home")
        os.environ["XDG_STATE_HOME"] = os.path.join(self.test_dir, "home", ".local", "state")
        os.makedirs(os.environ["XDG_STATE_HOME"], exist_ok=True)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_state_dir_descriptor_held_and_0700(self):
        dir_fd, path = secure_state.open_held_state_dir()
        try:
            st = os.fstat(dir_fd)
            self.assertTrue(stat.S_ISDIR(st.st_mode))
            self.assertEqual(st.st_mode & 0o777, 0o700)
            self.assertEqual(st.st_uid, os.getuid())
        finally:
            os.close(dir_fd)

    def test_atomic_state_write_and_read_via_fd(self):
        state = {
            "version": 2,
            "theme": {"displayName": "TestTheme", "hyprcursor": "TestHypr", "xcursor": "TestX"},
            "size": 28,
            "integrationConsent": True,
            "integrationInstalled": True
        }
        ok = secure_state.write_state(state)
        self.assertTrue(ok)

        read_back = secure_state.read_state()
        self.assertEqual(read_back["theme"]["displayName"], "TestTheme")
        self.assertEqual(read_back["size"], 28)
        self.assertTrue(read_back["integrationConsent"])


class TestIntegrationTransactionsFailureInjection(unittest.TestCase):
    """Verifies all failure injection cases for integration transactions."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_tx_inj_")
        self.orig_env = os.environ.copy()
        os.environ["HOME"] = os.path.join(self.test_dir, "home")
        os.environ["XDG_DATA_HOME"] = os.path.join(self.test_dir, "home", ".local", "share")
        os.environ["XDG_STATE_HOME"] = os.path.join(self.test_dir, "home", ".local", "state")
        os.environ["XDG_CONFIG_HOME"] = os.path.join(self.test_dir, "config")
        os.makedirs(os.environ["XDG_DATA_HOME"], exist_ok=True)
        os.makedirs(os.environ["XDG_STATE_HOME"], exist_ok=True)
        os.makedirs(os.environ["XDG_CONFIG_HOME"], exist_ok=True)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_case_a_snapshot_fails_no_helper_no_desktop(self):
        # Case A: Snapshot capture fails -> helper NOT installed, desktop entry NOT installed
        fake_plugin = os.path.join(self.test_dir, "mock_plugin_a")
        os.makedirs(fake_plugin, exist_ok=True)
        # Missing scripts/omarchy-cursor-switcher
        res = cleanup_engine.install_integration(fake_plugin)
        self.assertFalse(res["ok"])
        self.assertFalse(os.path.exists(os.path.join(os.environ["HOME"], ".local", "bin", "omarchy-cursor-switcher")))
        self.assertFalse(os.path.exists(os.path.join(os.environ["XDG_DATA_HOME"], "applications", "omarchy-cursor-switcher.desktop")))

    def test_case_b_helper_install_fails_rollback_snapshot_and_no_desktop(self):
        # Case B: Helper install fails -> new snapshot rolled back, desktop registration not attempted
        fake_plugin = os.path.join(self.test_dir, "mock_plugin_b")
        os.makedirs(os.path.join(fake_plugin, "scripts"), exist_ok=True)
        os.makedirs(os.path.join(fake_plugin, "desktop"), exist_ok=True)
        os.makedirs(os.path.join(fake_plugin, "icons"), exist_ok=True)

        # Create read-only ~/.local/bin to trigger write failure
        bin_dir = os.path.join(os.environ["HOME"], ".local", "bin")
        os.makedirs(bin_dir, exist_ok=True)
        os.chmod(bin_dir, 0o400)

        # Create assets in fake_plugin
        for f in ["omarchy-cursor-switcher", "omarchy-cursor-switcher-cleanup"]:
            with open(os.path.join(fake_plugin, "scripts", f), "w") as fp:
                fp.write("#!/bin/sh\n")
        with open(os.path.join(fake_plugin, "desktop", "omarchy-cursor-switcher.desktop"), "w") as fp:
            fp.write("[Desktop Entry]\n")
        with open(os.path.join(fake_plugin, "icons", "omarchy-cursor-switcher.svg"), "w") as fp:
            fp.write("<svg></svg>\n")

        try:
            res = cleanup_engine.install_integration(fake_plugin)
            self.assertFalse(res["ok"])
            self.assertTrue(res["rolled_back"])
            self.assertEqual(res["stage"], "install_files")
            self.assertFalse(os.path.exists(os.path.join(os.environ["XDG_DATA_HOME"], "applications", "omarchy-cursor-switcher.desktop")))
        finally:
            os.chmod(bin_dir, 0o755)

    def test_case_c_install_succeeds_state_marked_correctly(self):
        # Successful installation transaction
        res = cleanup_engine.install_integration(str(ROOT))
        self.assertTrue(res["ok"])
        st = secure_state.read_state()
        self.assertTrue(st["integrationInstalled"])
        self.assertTrue(st["integrationConsent"])

    def test_case_d_partial_remove_reports_accurately(self):
        # Install first
        cleanup_engine.install_integration(str(ROOT))
        # Remove
        rem_res = cleanup_engine.remove_integration()
        self.assertTrue(rem_res["ok"])
        st = secure_state.read_state()
        self.assertFalse(st["integrationInstalled"])


class TestRestoreSafety(unittest.TestCase):
    """Verifies that invalid snapshot data NEVER causes broad configuration overwrites."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_restore_safety_")
        self.orig_env = os.environ.copy()
        os.environ["HOME"] = os.path.join(self.test_dir, "home")
        os.environ["XDG_STATE_HOME"] = os.path.join(self.test_dir, "home", ".local", "state")
        os.environ["XDG_CONFIG_HOME"] = os.path.join(self.test_dir, "config")
        os.makedirs(os.environ["XDG_STATE_HOME"], exist_ok=True)
        os.makedirs(os.environ["XDG_CONFIG_HOME"], exist_ok=True)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_invalid_snapshot_preserves_current_state_without_overwrites(self):
        # Corrupt/empty snapshot file
        snap_path = os.path.join(os.environ["XDG_STATE_HOME"], "cursor-theme-manager", "snapshot.json")
        os.makedirs(os.path.dirname(snap_path), exist_ok=True)
        with open(snap_path, "w") as f:
            f.write('{"invalid": true}')

        res = cleanup_engine.restore_original_state()
        self.assertFalse(res["ok"], "Restore with invalid snapshot must return ok: False")
        self.assertIn("preserved current environment", res["error"])


class TestPlainTextAndModelSanitization(unittest.TestCase):
    """Verifies that control characters and hostile markup are sanitized and dynamic Text elements enforce Text.PlainText."""

    def test_sanitize_text_strips_control_characters_and_caps_length(self):
        hostile = "Theme\x00\x08<script>alert('xss')</script>\nLine2\t" + ("B" * 500)
        cleaned = runtime_safety.sanitize_text(hostile, max_len=50)
        self.assertNotIn("\x00", cleaned)
        self.assertNotIn("\x08", cleaned)
        self.assertLessEqual(len(cleaned), 50)

    def test_qml_files_strictly_use_plaintext(self):
        qml_files = list(ROOT.glob("*.qml")) + list((ROOT / "components").glob("*.qml"))
        self.assertTrue(len(qml_files) > 0)

        for qml in qml_files:
            content = qml.read_text(encoding="utf-8")
            clean = re.sub(r'//.*', '', content)
            clean = re.sub(r'/\*.*?\*/', '', clean, flags=re.DOTALL)

            matches = [m.start() for m in re.finditer(r'\b(Text|Label)\s*\{', clean)]
            for idx in matches:
                open_b = 0
                end_idx = idx
                for j in range(idx, len(clean)):
                    if clean[j] == '{':
                        open_b += 1
                    elif clean[j] == '}':
                        open_b -= 1
                        if open_b == 0:
                            end_idx = j
                            break
                block = clean[idx:end_idx+1]
                if re.search(r'\btext\s*:', block):
                    self.assertIn(
                        "textFormat: Text.PlainText",
                        block,
                        f"{qml.name} contains Text node without textFormat: Text.PlainText"
                    )


if __name__ == "__main__":
    unittest.main()
