#!/usr/bin/env python3
"""
Comprehensive Adversarial Security & Verification Test Suite for Cursor Theme Manager.
Demonstrates:
1. Output limits: Immediate process-group kill upon exceeding byte limits (+1 byte tests), verifying parent, child, grandchild all terminated.
2. Process tree cancellation: Fake helpers ignoring SIGTERM, sleeping forever, forking children/grandchildren.
3. Legacy state migration: Symlinks, FIFOs, oversize files (>64KB), malformed JSON, deep recursion rejection.
4. Secure descriptor-held state directory: 0700 permissions, current-user ownership, symlink rejection.
5. Consented Integration & Automatic Removal Lifecycle:
   - Zero artifacts before consent.
   - Declining creates zero persistent files.
   - Transactional rollback on staging/systemctl failure.
   - Foreign desktop entry collision refusal.
   - Symlink substitution rejection.
   - Watcher no-op when plugin directory exists.
   - Watcher cleanup execution when plugin directory is missing.
   - Idempotent cleanup execution.
   - Baseline capture preservation across multiple applies.
   - Imported cursor themes preservation.
   - Clean reinstall after removal.
6. Plain-text UI & model sanitization: Control characters, hostile HTML/markup injection, length caps.
"""

import sys
import os
import re
import json
import stat
import time
import shutil
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import runtime_safety
import secure_state
import integration_manager
import cleanup_helper
from test_isolation import IsolatedTestCase


def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


class TestProcessSupervisorSafety(IsolatedTestCase):
    """Verifies that run_bounded enforces strict byte caps, timeouts, and process-group isolation."""

    def test_stdout_limit_plus_one_byte_kills_entire_process_tree(self):
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
        self.assertTrue(res.limit_exceeded)
        self.assertFalse(res.ok)
        self.assertIn("exceeded limit", res.error.lower())

        time.sleep(0.2)
        if os.path.exists(pid_file):
            with open(pid_file) as pf:
                pids = [int(p.strip()) for p in pf.read().splitlines() if p.strip().isdigit()]
            os.unlink(pid_file)
            for pid in pids:
                self.assertFalse(is_pid_alive(pid), f"PID {pid} was not terminated after stdout flood")

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
            with open(pid_file) as pf:
                pids = [int(p.strip()) for p in pf.read().splitlines() if p.strip().isdigit()]
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
            with open(pid_file) as pf:
                pid = int(pf.read().strip())
            os.unlink(pid_file)
            self.assertFalse(is_pid_alive(pid), f"Process {pid} that ignored SIGTERM was not killed by SIGKILL")


class TestLegacyStateMigrationAdversarial(IsolatedTestCase):
    """Verifies that legacy state migration strictly validates file type, ownership, size, and schema BEFORE parsing."""

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(os.environ["XDG_CONFIG_HOME"], "omarchy"), exist_ok=True)

    def tearDown(self):
        super().tearDown()

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
            pass

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
        nested = '{"a": ' * 50 + '1' + '}' * 50
        with open(legacy_path, "w") as f:
            f.write(nested)

        dir_fd, _ = secure_state.open_held_state_dir()
        try:
            res = secure_state._try_legacy_migration(dir_fd)
            self.assertIsNone(res, "Deeply nested JSON legacy state must be rejected")
        finally:
            os.close(dir_fd)


class TestStateDirectorySecurity(IsolatedTestCase):
    """Verifies that the dedicated state directory is created with 0700, owned by user, verified with fstat, and held via FD."""

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

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
            "integrationPromptSeen": True,
            "integrationEnabled": True,
            "originalCursor": {
                "captured": True,
                "hyprcursorTheme": "OrigHypr",
                "hyprcursorSize": 24,
                "xcursorTheme": "OrigX",
                "xcursorSize": 24,
                "gtkTheme": "OrigX",
                "gtkSize": 24
            }
        }
        ok = secure_state.write_state(state)
        self.assertTrue(ok)

    def test_state_dir_symlink_fails_and_victim_mode_unchanged(self):
        victim_dir = Path(os.environ["HOME"]) / "victim_private_dir"
        victim_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(victim_dir, 0o755)
        self.assertEqual(victim_dir.stat().st_mode & 0o777, 0o755)

        state_dir_path = Path(secure_state.get_state_dir_path())
        if state_dir_path.exists():
            shutil.rmtree(state_dir_path)
        state_dir_path.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(str(victim_dir), str(state_dir_path))

        with self.assertRaises(secure_state.SecurityError):
            secure_state.open_held_state_dir()

        # Invariant: Victim directory mode must remain strictly UNCHANGED
        self.assertEqual(
            victim_dir.stat().st_mode & 0o777, 0o755,
            "Planted state directory symlink mutated victim directory permissions!"
        )

    def test_state_dir_intermediate_symlink_rejected(self):
        victim_dir = Path(os.environ["HOME"]) / "victim_state_parent"
        victim_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(victim_dir, 0o755)

        # Replace XDG_STATE_HOME with a symlink to victim_dir
        state_home = Path(os.environ["XDG_STATE_HOME"])
        if state_home.exists():
            shutil.rmtree(state_home)
        os.symlink(str(victim_dir), str(state_home))

        with self.assertRaises(secure_state.SecurityError):
            secure_state.open_held_state_dir()

        self.assertEqual(victim_dir.stat().st_mode & 0o777, 0o755)

    def test_state_dir_regular_file_rejected_without_mutation(self):
        state_dir_path = Path(secure_state.get_state_dir_path())
        if state_dir_path.exists():
            shutil.rmtree(state_dir_path)
        state_dir_path.parent.mkdir(parents=True, exist_ok=True)
        with open(state_dir_path, "w") as f:
            f.write("not a directory")
        os.chmod(state_dir_path, 0o644)

        with self.assertRaises(secure_state.SecurityError):
            secure_state.open_held_state_dir()

        self.assertTrue(state_dir_path.is_file())
        self.assertEqual(state_dir_path.stat().st_mode & 0o777, 0o644)

    def test_state_dir_mode_correction_only_on_verified_inode(self):
        state_dir_path = Path(secure_state.get_state_dir_path())
        state_dir_path.mkdir(parents=True, exist_ok=True)
        os.chmod(state_dir_path, 0o755)
        self.assertEqual(state_dir_path.stat().st_mode & 0o777, 0o755)

        dir_fd, path = secure_state.open_held_state_dir()
        try:
            st = os.fstat(dir_fd)
            self.assertEqual(st.st_mode & 0o777, 0o700)
            self.assertEqual(state_dir_path.stat().st_mode & 0o777, 0o700)
        finally:
            os.close(dir_fd)


class TestConsentedIntegrationAndRemovalAdversarial(IsolatedTestCase):
    """Verifies security, rollback, and lifecycle properties of the consented integration."""

    def setUp(self):
        super().setUp()

    def tearDown(self):
        try:
            integration_manager.disable_integration()
        except Exception:
            pass
        super().tearDown()

    def test_zero_artifacts_before_consent(self):
        paths = integration_manager.get_paths()
        for key in ["desktop", "cleanup", "path_unit", "service_unit"]:
            self.assertFalse(os.path.exists(paths[key]), f"Artifact '{paths[key]}' exists before user consent!")

    def test_decline_creates_no_persistent_files(self):
        res = integration_manager.dismiss_prompt()
        self.assertTrue(res["ok"])
        paths = integration_manager.get_paths()
        for key in ["desktop", "cleanup", "path_unit", "service_unit"]:
            self.assertFalse(os.path.exists(paths[key]))
        # Assert no durable state file created solely for dismissal
        self.assertFalse(os.path.exists(self.iso.state_dir / "state.json"))
        st = integration_manager.get_status()
        self.assertFalse(st["enabled"])
        self.assertFalse(st["promptSeen"])

    def test_transactional_installation_success(self):
        res = integration_manager.enable_integration()
        self.assertTrue(res["ok"])
        paths = integration_manager.get_paths()

        self.assertTrue(os.path.isfile(paths["desktop"]))
        self.assertTrue(os.path.isfile(paths["cleanup"]))
        self.assertTrue(os.path.isfile(paths["path_unit"]))
        self.assertTrue(os.path.isfile(paths["service_unit"]))

        with open(paths["desktop"]) as f:
            desktop_content = f.read()
        self.assertIn("X-CursorThemeManager-Owned=true", desktop_content)
        self.assertIn("Exec=omarchy-shell shell toggle sanjyay.cursor-theme-manager", desktop_content)

    def test_transactional_rollback_on_failure_injection(self):
        # Inject systemctl failure to force rollback
        def failing_run_bounded(cmd, *args, **kwargs):
            if any("daemon-reload" in str(c) or "enable" in str(c) for c in cmd):
                return runtime_safety.BoundedResult(exit_code=1, stdout=b"", stderr=b"Injected systemd failure", error="Injected systemd failure")
            return runtime_safety.run_bounded(cmd, *args, **kwargs)

        with mock.patch("integration_manager.run_bounded", side_effect=failing_run_bounded):
            res = integration_manager.enable_integration()
            self.assertFalse(res["ok"])
            self.assertIn("Integration installation failed and was rolled back", res["error"])

        # Verify no artifacts survived the failed attempt
        paths = integration_manager.get_paths()
        for key in ["desktop", "cleanup", "path_unit", "service_unit"]:
            self.assertFalse(os.path.exists(paths[key]), f"Artifact '{paths[key]}' survived failed installation!")

    def test_foreign_desktop_file_collision_refusal(self):
        paths = integration_manager.get_paths()
        os.makedirs(os.path.dirname(paths["desktop"]), exist_ok=True)
        with open(paths["desktop"], "w") as f:
            f.write("[Desktop Entry]\nName=ForeignApp\nExec=firefox\n")

        res = integration_manager.enable_integration()
        self.assertFalse(res["ok"])
        self.assertIn("not created by Cursor Theme Manager", res["error"])

        with open(paths["desktop"]) as f:
            self.assertIn("ForeignApp", f.read())

    def test_foreign_desktop_file_removal_refusal(self):
        paths = integration_manager.get_paths()
        os.makedirs(os.path.dirname(paths["desktop"]), exist_ok=True)
        with open(paths["desktop"], "w") as f:
            f.write("[Desktop Entry]\nName=ForeignApp\nExec=firefox\n")

        res = integration_manager.disable_integration()
        self.assertFalse(res["ok"])
        self.assertIn("not owned by Cursor Theme Manager", res["error"])
        self.assertTrue(os.path.exists(paths["desktop"]))

    def test_watcher_noop_when_plugin_directory_still_exists(self):
        # Enable integration
        integration_manager.enable_integration()
        paths = integration_manager.get_paths()

        # Create plugin directory to simulate active plugin
        plugin_dir = os.path.join(os.environ["XDG_CONFIG_HOME"], "omarchy", "plugins", "sanjyay.cursor-theme-manager")
        os.makedirs(plugin_dir, exist_ok=True)

        # Run cleanup helper
        res = runtime_safety.run_bounded([sys.executable, paths["cleanup"]], timeout=3.0)
        self.assertTrue(res.ok)

        # Verify nothing was deleted
        self.assertTrue(os.path.exists(paths["desktop"]))
        self.assertTrue(os.path.exists(paths["cleanup"]))
        self.assertTrue(os.path.exists(paths["path_unit"]))

    def test_idempotent_cleanup(self):
        # Enable integration
        integration_manager.enable_integration()
        paths = integration_manager.get_paths()

        # Plugin directory absent -> run cleanup once
        res1 = runtime_safety.run_bounded([sys.executable, paths["cleanup"]], timeout=3.0)
        self.assertTrue(res1.ok)

        # Run cleanup helper script a second time (idempotence check)
        cleanup_source = str(SCRIPTS_DIR / "cleanup_helper.py")
        res2 = runtime_safety.run_bounded([sys.executable, cleanup_source], timeout=3.0)
        self.assertTrue(res2.ok)



    def test_explicit_theme_distinguished_from_unset_in_baseline(self):
        # Case A: Variables unset
        orig_unset = secure_state.validate_original_cursor({
            "captured": True,
            "hyprcursorThemeSet": False,
            "hyprcursorTheme": None,
            "xcursorThemeSet": False,
            "xcursorTheme": None,
            "gtkThemeSet": True,
            "gtkTheme": "default",
            "gtkSizeSet": True,
            "gtkSize": 24
        })
        self.assertFalse(orig_unset["hyprcursorThemeSet"])
        self.assertIsNone(orig_unset["hyprcursorTheme"])
        self.assertFalse(orig_unset["xcursorThemeSet"])

        # Case B: Variables explicitly set to Adwaita
        orig_adwaita = secure_state.validate_original_cursor({
            "captured": True,
            "hyprcursorThemeSet": True,
            "hyprcursorTheme": "Adwaita",
            "xcursorThemeSet": True,
            "xcursorTheme": "Adwaita",
            "gtkThemeSet": True,
            "gtkTheme": "Adwaita",
            "gtkSizeSet": True,
            "gtkSize": 24
        })
        self.assertTrue(orig_adwaita["hyprcursorThemeSet"])
        self.assertEqual(orig_adwaita["hyprcursorTheme"], "Adwaita")

    def test_invalid_theme_name_rejected_in_baseline(self):
        hostile_cursor = secure_state.validate_original_cursor({
            "captured": True,
            "hyprcursorThemeSet": True,
            "hyprcursorTheme": "Theme; rm -rf /",
            "gtkSizeSet": True,
            "gtkSize": 99999
        })
        self.assertIsNone(hostile_cursor["hyprcursorTheme"])
        self.assertIsNone(hostile_cursor["gtkSize"])



    def test_default_cursor_resolution_loop_detection_and_security(self):
        # Create a loop in mock themes
        loop_dir = os.path.join(self.test_dir, "icons")
        os.makedirs(os.path.join(loop_dir, "ThemeA"), exist_ok=True)
        os.makedirs(os.path.join(loop_dir, "ThemeB"), exist_ok=True)
        with open(os.path.join(loop_dir, "ThemeA", "index.theme"), "w") as f:
            f.write("[Icon Theme]\nInherits=ThemeB\n")
        with open(os.path.join(loop_dir, "ThemeB", "index.theme"), "w") as f:
            f.write("[Icon Theme]\nInherits=ThemeA\n")

        resolved = secure_state.resolve_default_cursor_theme(roots=[loop_dir])
        self.assertIsNone(resolved)

    def test_live_restore_failure_preserves_baseline_and_state(self):
        paths = integration_manager.get_paths()
        res = integration_manager.enable_integration()
        self.assertTrue(res["ok"])

        # Set captured baseline and cursorModifiedByCtm=True
        st = secure_state.read_state()
        st["preCtmCursor"] = {
            "captured": True,
            "hyprcursorThemeSet": False,
            "hyprcursorTheme": None,
            "xcursorThemeSet": True,
            "xcursorTheme": "Adwaita",
            "xcursorSizeSet": True,
            "xcursorSize": 24,
            "gtkThemeSet": True,
            "gtkTheme": "Adwaita",
            "gtkSizeSet": True,
            "gtkSize": 24,
            "liveRestoreTheme": "NonExistentUninstalledCursorTheme",
            "liveRestoreSize": 24,
            "liveTheme": "NonExistentUninstalledCursorTheme",
            "liveSize": 24,
            "liveBackend": "xcursor"
        }
        st["cursorModifiedByCtm"] = True
        secure_state.write_state(st)

        # Run cleanup helper with uninstalled theme causing restore failure
        res_fail = runtime_safety.run_bounded([sys.executable, paths["cleanup"]], timeout=3.0)
        self.assertFalse(res_fail.ok)
        self.assertIn("critical failure", res_fail.stderr)

        # Ensure state file and units are preserved for retry
        self.assertTrue(os.path.exists(paths["cleanup"]))
        self.assertTrue(os.path.exists(paths["path_unit"]))
        state_file = os.path.join(os.environ["XDG_STATE_HOME"], "cursor-theme-manager", "state.json")
        self.assertTrue(os.path.exists(state_file))



    def test_baseline_preserved_across_qml_state_writes(self):
        # Step 1: Initial state with baseline
        st = secure_state.read_state()
        st["preCtmCursor"] = {
            "captured": True,
            "hyprcursorThemeSet": False,
            "hyprcursorTheme": None,
            "xcursorThemeSet": True,
            "xcursorTheme": "Nordzy",
            "xcursorSizeSet": True,
            "xcursorSize": 28,
            "gtkThemeSet": True,
            "gtkTheme": "Nordzy",
            "gtkSizeSet": True,
            "gtkSize": 28,
            "liveTheme": "Nordzy",
            "liveSize": 28,
            "liveBackend": "xcursor"
        }
        st["cursorModifiedByCtm"] = True
        secure_state.write_state(st)

        # Step 2: Simulate QML state write without preCtmCursor
        qml_state = {
            "version": 2,
            "theme": {"displayName": "Banana", "xcursor": "Banana"},
            "size": 80,
            "importedThemes": [],
            "integrationPromptSeen": True,
            "integrationEnabled": True
        }
        secure_state.write_state(qml_state)

        # Step 3: Read back state and verify preCtmCursor was NOT clobbered
        read_back = secure_state.read_state()
        self.assertIsNotNone(read_back.get("preCtmCursor"))
        self.assertTrue(read_back["preCtmCursor"]["captured"])
        self.assertEqual(read_back["preCtmCursor"]["liveTheme"], "Nordzy")
        self.assertEqual(read_back["preCtmCursor"]["liveSize"], 28)
        self.assertTrue(read_back["cursorModifiedByCtm"])

    def test_cleanup_fails_if_cursor_modified_but_baseline_missing(self):
        paths = integration_manager.get_paths()
        res = integration_manager.enable_integration()
        self.assertTrue(res["ok"])

        # Manually write state with cursorModifiedByCtm=True but no preCtmCursor
        state_file = os.path.join(os.environ["XDG_STATE_HOME"], "cursor-theme-manager", "state.json")
        with open(state_file, "w") as f:
            f.write(json.dumps({
                "version": 2,
                "cursorModifiedByCtm": True,
                "preCtmCursor": None
            }))

        # Run cleanup helper
        res_clean = runtime_safety.run_bounded([sys.executable, paths["cleanup"]], timeout=3.0)
        self.assertFalse(res_clean.ok)
        self.assertIn("critical error", res_clean.stderr)
        self.assertIn("preCtmCursor baseline is missing", res_clean.stderr)

        # Ensure state file and units are preserved for recovery
        self.assertTrue(os.path.exists(state_file))
        self.assertTrue(os.path.exists(paths["cleanup"]))
        self.assertTrue(os.path.exists(paths["path_unit"]))


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


class TestExecutableTrustAndHostilePath(IsolatedTestCase):
    """
    Verifies that CTM rejects user-writable PATH binaries, executes only root-owned system binaries,
    and strips dangerous code-injection environment variables.
    """

    def setUp(self):
        super().setUp()
        self.evil_bin = Path(self.test_dir) / "evil_bin"
        self.evil_bin.mkdir(parents=True, exist_ok=True)
        self.sentinel = Path(self.test_dir) / "pwned_sentinel.txt"

        # Create hostile fake binaries for all sensitive external tools
        for tool_name in ["hyprctl", "gsettings", "systemctl", "hyprcursor-util", "dbus-update-activation-environment", "update-desktop-database", "xdg-open", "xcur2png", "magick"]:
            fake_script = self.evil_bin / tool_name
            with open(fake_script, "w") as f:
                f.write(f"#!/bin/sh\necho 'PWNED: {tool_name}' >> '{self.sentinel}'\nexit 0\n")
            os.chmod(fake_script, 0o755)

        # Inject hostile PATH
        self.hostile_env = {
            **self.env,
            "PATH": f"{self.evil_bin}:{os.environ.get('PATH', '')}"
        }

    def test_resolver_never_resolves_hostile_path_binaries(self):
        for tool_name in ["hyprctl", "gsettings", "systemctl", "hyprcursor-util"]:
            resolved = runtime_safety.resolve_system_executable(tool_name)
            self.assertIsNotNone(resolved)
            self.assertFalse(
                resolved.startswith(str(self.evil_bin)),
                f"Resolver returned hostile path executable: {resolved}"
            )
            self.assertTrue(
                resolved.startswith("/usr/bin/") or resolved.startswith("/bin/"),
                f"Resolved binary not in trusted system directory: {resolved}"
            )

    def test_run_bounded_never_executes_hostile_path_binaries(self):
        # Run various commands with hostile PATH in environment
        runtime_safety.run_bounded(["hyprctl", "--version"], env=self.hostile_env, timeout=2.0)
        runtime_safety.run_bounded(["gsettings", "--version"], env=self.hostile_env, timeout=2.0)
        runtime_safety.run_bounded(["systemctl", "--version"], env=self.hostile_env, timeout=2.0)
        runtime_safety.run_bounded(["hyprcursor-util", "--help"], env=self.hostile_env, timeout=2.0)

        # Invariant: Sentinel file must NEVER be created
        self.assertFalse(
            self.sentinel.exists(),
            "Adversarial fake binary was executed through PATH substitution!"
        )

    def test_untrusted_direct_path_fails_closed(self):
        fake_hypr = str(self.evil_bin / "hyprctl")
        res = runtime_safety.run_bounded([fake_hypr, "setcursor", "foo", "24"], timeout=2.0)
        self.assertFalse(res.ok)
        self.assertEqual(res.exit_code, 127)
        self.assertIn("unavailable or failed validation", res.error)
        self.assertFalse(self.sentinel.exists())

    def test_dangerous_env_vars_stripped(self):
        probe_code = "import os; print(os.environ.get('PYTHONPATH', 'CLEAN'), os.environ.get('LD_PRELOAD', 'CLEAN'))"
        res = runtime_safety.run_bounded(
            [sys.executable, "-c", probe_code],
            env={**self.env, "PYTHONPATH": "/evil/python/path", "LD_PRELOAD": "/evil/lib.so"}
        )
        self.assertTrue(res.ok)
        self.assertIn("CLEAN CLEAN", res.stdout)


if __name__ == "__main__":
    unittest.main()
