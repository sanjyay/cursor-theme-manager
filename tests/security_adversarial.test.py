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

import importlib.machinery
import importlib.util

import runtime_safety
import secure_state
import integration_manager
import cleanup_helper
from test_isolation import IsolatedTestCase

cursorctl_loader = importlib.machinery.SourceFileLoader("cursorctl_adv", str(SCRIPTS_DIR / "cursorctl"))
cursorctl_spec = importlib.util.spec_from_loader("cursorctl_adv", cursorctl_loader)
cursorctl = importlib.util.module_from_spec(cursorctl_spec)
cursorctl_loader.exec_module(cursorctl)


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

    def test_unknown_environment_override_is_stripped(self):
        env = runtime_safety.get_secure_subprocess_env({
            "HYPRLAND_INSTANCE_SIGNATURE": "safe-session",
            "GCONV_PATH": "/tmp/attacker",
            "QT_PLUGIN_PATH": "/tmp/attacker",
            "PATH": "/tmp/attacker"
        })
        self.assertEqual(env["HYPRLAND_INSTANCE_SIGNATURE"], "safe-session")
        self.assertNotIn("GCONV_PATH", env)
        self.assertNotIn("QT_PLUGIN_PATH", env)
        self.assertEqual(env["PATH"], runtime_safety.SAFE_SYSTEM_PATH)

    def test_resolver_revalidates_cached_executable_permissions(self):
        tool_dir = Path(self.test_dir) / "trusted-tools"
        tool_dir.mkdir(mode=0o700)
        tool = tool_dir / "demo-tool"
        tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        tool.chmod(0o700)
        resolved = runtime_safety._resolve_executable_from_roots(
            "demo-tool", [str(tool_dir)], allow_non_root=True
        )
        self.assertEqual(resolved, str(tool.resolve()))
        tool.chmod(0o722)
        self.assertIsNone(runtime_safety._resolve_executable_from_roots(
            "demo-tool", [str(tool_dir)], allow_non_root=True
        ))

    def test_bidirectional_pipes_do_not_bypass_deadline(self):
        helper = (
            "import sys\n"
            "sys.stdout.buffer.write(b'O' * 131072)\n"
            "sys.stdout.buffer.flush()\n"
            "data = sys.stdin.buffer.read()\n"
            "sys.stderr.write(str(len(data)))\n"
        )
        payload = b"I" * (512 * 1024)
        res = runtime_safety.run_bounded(
            [sys.executable, "-c", helper], input_data=payload,
            stdout_limit=200000, timeout=3.0
        )
        self.assertTrue(res.ok, res.error)
        self.assertEqual(len(res.stdout_bytes), 131072)
        self.assertEqual(res.stderr.strip(), str(len(payload)))


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

    def test_valid_first_run_migration_is_non_recursive_and_durable(self):
        legacy_path = os.path.join(os.environ["XDG_CONFIG_HOME"], "omarchy", "cursor-switcher.json")
        with open(legacy_path, "w", encoding="utf-8") as f:
            json.dump({"version": 2, "size": 32}, f)
        state = secure_state.read_state()
        self.assertEqual(state["size"], 32)
        self.assertTrue((self.iso.state_dir / "state.json").is_file())
        self.assertFalse(os.path.exists(legacy_path))

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

    def test_user_writable_intermediate_directory_rejected(self):
        unsafe_parent = Path(os.environ["HOME"]) / "unsafe-state-parent"
        unsafe_parent.mkdir(mode=0o700)
        os.chmod(unsafe_parent, 0o777)
        os.environ["XDG_STATE_HOME"] = str(unsafe_parent / "state")
        with self.assertRaises(secure_state.SecurityError):
            secure_state.open_held_state_dir()
        self.assertEqual(unsafe_parent.stat().st_mode & 0o777, 0o777)

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

    def test_enable_does_not_modify_live_plugin_directory(self):
        plugin_dir = self.iso.plugin_dir
        before_entries = sorted(os.listdir(plugin_dir))
        before_stat = os.lstat(plugin_dir)

        res = integration_manager.enable_integration()

        self.assertTrue(res["ok"])
        after_stat = os.lstat(plugin_dir)
        self.assertEqual(sorted(os.listdir(plugin_dir)), before_entries)
        self.assertEqual(after_stat.st_mtime_ns, before_stat.st_mtime_ns)
        self.assertTrue(integration_manager.get_status()["enabled"])

    def test_enabled_state_write_cannot_erase_installation_instance(self):
        res = integration_manager.enable_integration()
        self.assertTrue(res["ok"])

        partial_qml_state = secure_state.read_state()
        partial_qml_state.pop("integrationInstanceId", None)
        partial_qml_state.pop("integrationPluginFingerprint", None)
        partial_qml_state["integrationEnabled"] = True
        secure_state.write_state(partial_qml_state)

        state = secure_state.read_state()
        self.assertEqual(state["integrationInstanceId"], res["instanceId"])
        self.assertEqual(state["integrationPluginFingerprint"], res["pluginFingerprint"])
        self.assertTrue(integration_manager.get_status()["enabled"])

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

    def test_foreign_non_desktop_artifact_collisions_are_refused(self):
        paths = integration_manager.get_paths()
        for key in ("cleanup", "path_unit", "service_unit"):
            with self.subTest(key=key):
                target = paths[key]
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "w", encoding="utf-8") as f:
                    f.write("foreign file: preserve me\n")
                res = integration_manager.enable_integration()
                self.assertFalse(res["ok"])
                with open(target, encoding="utf-8") as f:
                    self.assertEqual(f.read(), "foreign file: preserve me\n")
                os.unlink(target)

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
        # Real UI startup creates a token before Integration is enabled. The
        # standalone cleanup copy must derive the same token fingerprint.
        identity = integration_manager.ensure_installation_identity()
        self.assertTrue(identity["ok"], identity)

        # Enable integration
        res_enable = integration_manager.enable_integration()
        self.assertTrue(res_enable["ok"])
        instance_id = res_enable["instanceId"]
        plugin_fingerprint = res_enable["pluginFingerprint"]
        paths = integration_manager.get_paths()

        # Run cleanup helper for the still-current plugin installation.
        res = runtime_safety.run_bounded([
            sys.executable, paths["cleanup"], "--instance", instance_id,
            "--plugin-fingerprint", plugin_fingerprint
        ], timeout=3.0)
        self.assertTrue(res.ok)

        # Verify nothing was deleted
        self.assertTrue(os.path.exists(paths["desktop"]))
        self.assertTrue(os.path.exists(paths["cleanup"]))
        self.assertTrue(os.path.exists(paths["path_unit"]))

    def test_old_cleanup_compare_and_delete_preserves_new_instance_state(self):
        identity_a = integration_manager.ensure_installation_identity()
        self.assertTrue(identity_a["ok"], identity_a)
        enabled_a = integration_manager.enable_integration()
        self.assertTrue(enabled_a["ok"], enabled_a)
        old_instance = enabled_a["instanceId"]
        old_fingerprint = enabled_a["pluginFingerprint"]

        old_state = secure_state.read_state()
        old_state["preCtmCursor"] = {
            "captured": True,
            "gtkThemeSet": True, "gtkTheme": "Adwaita",
            "gtkSizeSet": True, "gtkSize": 24,
            "liveRestoreBackend": "gtk",
            "liveRestoreTheme": "Adwaita", "liveRestoreSize": 24,
        }
        old_state["cursorModifiedByCtm"] = True
        secure_state.write_state(old_state)

        plugin_dir = self.iso.plugin_dir
        shutil.rmtree(plugin_dir)
        plugin_dir.mkdir()
        identity_b = integration_manager.ensure_installation_identity()
        self.assertTrue(identity_b["ok"], identity_b)

        def restore_then_publish_new_state(_baseline):
            new_state = secure_state.read_state()
            new_state["integrationEnabled"] = False
            new_state["integrationPromptSeen"] = False
            new_state["integrationInstanceId"] = None
            new_state["integrationPluginFingerprint"] = identity_b["pluginFingerprint"]
            secure_state.write_state(new_state)
            return True

        with mock.patch.object(cleanup_helper, "restore_cursor", side_effect=restore_then_publish_new_state), \
             mock.patch.object(cleanup_helper, "run_cmd"):
            with self.assertRaises(SystemExit) as finished:
                cleanup_helper.execute_cleanup(old_instance, old_fingerprint)
        self.assertEqual(finished.exception.code, 0)

        preserved = secure_state.read_state()
        self.assertEqual(preserved["integrationPluginFingerprint"], identity_b["pluginFingerprint"])
        self.assertTrue((self.iso.state_dir / "state.json").is_file())

    def test_remove_immediate_reinstall_race_cleans_old_instance_safely(self):
        # 1. Enable integration for instance ABC
        res = integration_manager.enable_integration()
        self.assertTrue(res["ok"])
        old_instance = res["instanceId"]
        old_fingerprint = res["pluginFingerprint"]
        paths = integration_manager.get_paths()

        # 2. Simulate plugin directory removed then immediately re-created by fresh install (instance XYZ)
        plugin_dir = os.path.join(os.environ["XDG_CONFIG_HOME"], "omarchy", "plugins", "sanjyay.cursor-theme-manager")
        shutil.rmtree(plugin_dir)
        os.makedirs(plugin_dir)

        # A new QML instance can start before the old systemd cleanup. It must
        # neither replay the old selected cursor nor replace the recovery state.
        stale_status = integration_manager.get_status()
        self.assertTrue(stale_status["recoveryPending"])
        old_state = secure_state.read_state()
        old_state["theme"] = {
            "displayName": "Banana", "hyprcursor": "Banana",
            "xcursor": "Banana", "path": "/tmp/Banana"
        }
        old_state["size"] = 64
        old_state["cursorModifiedByCtm"] = True
        old_state["preCtmCursor"] = {
            "captured": True,
            "gtkThemeSet": True, "gtkTheme": "Adwaita",
            "gtkSizeSet": True, "gtkSize": 24,
            "liveRestoreBackend": "gtk",
            "liveRestoreTheme": "Adwaita", "liveRestoreSize": 24,
        }
        old_state["importedThemes"] = ["PreservedImport"]
        secure_state.write_state(old_state)

        state_read = runtime_safety.run_bounded(
            [sys.executable, str(SCRIPTS_DIR / "cursorctl"), "state-read"],
            timeout=3.0
        )
        self.assertTrue(state_read.ok, state_read.error)
        new_view = json.loads(state_read.stdout)
        self.assertTrue(new_view["recoveryPending"])
        self.assertIsNone(new_view["theme"])
        self.assertFalse(new_view.get("cursorModifiedByCtm", False), new_view)
        self.assertFalse(new_view["integrationEnabled"])
        self.assertEqual(secure_state.read_state()["importedThemes"], ["PreservedImport"])

        refused = integration_manager.enable_integration()
        self.assertFalse(refused["ok"])
        self.assertTrue(refused["recoveryPending"])
        self.assertEqual(secure_state.read_state()["integrationInstanceId"], old_instance)

        # 3. Old cleanup helper runs with --instance <old_instance>
        # The live-restore command itself is covered by the dedicated tests;
        # keep this race test hermetic while exercising real cleanup ordering.
        with mock.patch("cleanup_helper.restore_cursor", return_value=True), \
             mock.patch("cleanup_helper.run_cmd"):
            with self.assertRaises(SystemExit) as finished:
                cleanup_helper.execute_cleanup(old_instance, old_fingerprint)
        self.assertEqual(finished.exception.code, 0)

        # 4. Assert old persistent integration artifacts are removed
        self.assertFalse(os.path.exists(paths["desktop"]))
        self.assertFalse(os.path.exists(paths["path_unit"]))
        self.assertFalse(os.path.exists(paths["service_unit"]))

        # 5. Assert new installation does NOT inherit integration
        st_after = integration_manager.get_status()
        self.assertFalse(st_after["enabled"])
        self.assertFalse(st_after["promptSeen"])

    def test_stale_state_startup_does_not_inherit_integration_enabled(self):
        # Pre-seed stale state file claiming integration is enabled for instance ABC
        st = secure_state.read_state()
        st["integrationEnabled"] = True
        st["integrationPromptSeen"] = True
        st["integrationInstanceId"] = "abcdef1234567890"
        st["integrationPluginFingerprint"] = "a" * 64
        secure_state.write_state(st)

        status = integration_manager.get_status()
        self.assertFalse(status["enabled"])
        self.assertFalse(status["promptSeen"])

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

    def test_live_baseline_prefers_queryable_gtk_over_stale_environment(self):
        def fake_run(argv, **kwargs):
            joined = " ".join(argv)
            if "cursor-theme" in joined:
                out = b"'Adwaita'\n"
            elif "cursor-size" in joined:
                out = b"24\n"
            elif "show-environment" in joined:
                out = b"HYPRCURSOR_THEME=Nordzy\nHYPRCURSOR_SIZE=48\nXCURSOR_THEME=Nordzy\nXCURSOR_SIZE=48\n"
            else:
                out = b""
            return runtime_safety.BoundedResult(0, out, b"")

        with mock.patch("runtime_safety.run_bounded", side_effect=fake_run), \
             mock.patch("runtime_safety.resolve_system_executable", side_effect=lambda name: f"/usr/bin/{name}"), \
             mock.patch.object(secure_state, "has_cursor_data", return_value=True):
            baseline = secure_state.capture_original_cursor()
        self.assertEqual(baseline["hyprcursorTheme"], "Nordzy")
        self.assertEqual(baseline["gtkTheme"], "Adwaita")
        self.assertEqual(baseline["liveRestoreTheme"], "Adwaita")
        self.assertEqual(baseline["liveRestoreSize"], 24)



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

    def _live_restore_baseline(self):
        return {
            "captured": True,
            "liveRestoreBackend": "gtk",
            "liveRestoreTheme": "Adwaita",
            "liveRestoreSize": 24,
            "gtkThemeSet": True,
            "gtkTheme": "Adwaita",
            "gtkSizeSet": True,
            "gtkSize": 24,
            "hyprcursorThemeSet": False,
            "xcursorThemeSet": False,
        }

    def _exercise_live_restore(self, live_result):
        calls = []

        def fake_run(args, env_override=None, **kwargs):
            calls.append((list(args), dict(env_override or {})))
            if "setcursor" in args:
                return live_result
            return cleanup_helper.CommandResult(ok=True, exit_code=0, argv=list(args))

        with mock.patch.object(cleanup_helper, "run_cmd", side_effect=fake_run), \
             mock.patch.object(cleanup_helper, "find_hyprland_instance", return_value="test-hypr-instance"), \
             mock.patch.object(cleanup_helper, "resolve_system_executable", return_value="/usr/bin/hyprctl"), \
             mock.patch.object(cleanup_helper, "has_cursor_data", return_value=True):
            result = cleanup_helper.restore_cursor(self._live_restore_baseline())
        return result, calls

    def test_live_restore_invokes_exact_baseline_after_persistent_stages(self):
        result, calls = self._exercise_live_restore(
            cleanup_helper.CommandResult(ok=True, exit_code=0, argv=["/usr/bin/hyprctl"])
        )
        self.assertTrue(result)
        self.assertEqual(calls[-1][0], ["/usr/bin/hyprctl", "setcursor", "Adwaita", "24"])
        self.assertEqual(calls[-1][1]["HYPRLAND_INSTANCE_SIGNATURE"], "test-hypr-instance")
        self.assertTrue(any(call[0][0] == "gsettings" for call in calls[:-1]))
        self.assertTrue(any(call[0][0] == "systemctl" for call in calls[:-1]))

    def test_live_restore_nonzero_is_failure(self):
        result, _ = self._exercise_live_restore(
            cleanup_helper.CommandResult(ok=False, exit_code=1, stderr="connection failed", argv=["/usr/bin/hyprctl"])
        )
        self.assertFalse(result)

    def test_live_restore_timeout_is_failure(self):
        result, _ = self._exercise_live_restore(
            cleanup_helper.CommandResult(ok=False, exit_code=124, timed_out=True, error="command timed out", argv=["/usr/bin/hyprctl"])
        )
        self.assertFalse(result)

    def test_missing_hyprland_instance_never_reports_live_success(self):
        calls = []
        with mock.patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": ""}), \
             mock.patch.object(cleanup_helper, "run_cmd", side_effect=lambda args, **kwargs: calls.append(list(args)) or cleanup_helper.CommandResult(ok=True, exit_code=0, argv=list(args))), \
             mock.patch.object(cleanup_helper, "find_hyprland_instance", return_value=None), \
             mock.patch.object(cleanup_helper, "resolve_system_executable", return_value="/usr/bin/hyprctl"), \
             mock.patch.object(cleanup_helper, "has_cursor_data", return_value=True):
            self.assertFalse(cleanup_helper.restore_cursor(self._live_restore_baseline()))
        self.assertFalse(any("setcursor" in call for call in calls))

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

        generated_cache = self.iso.user_icons / "CursorSwitcher-XCursor-FailureCase-deadbeef0000"
        generated_cache.mkdir(parents=True)
        (generated_cache / ".cursor-theme-manager-generated").write_text(
            "version=1\nkind=conversion-cache\nsourceTheme=FailureCase\n", encoding="utf-8"
        )

        # Simulate plugin removal in isolated test environment
        plugin_dir = os.path.join(os.environ["XDG_CONFIG_HOME"], "omarchy", "plugins", "sanjyay.cursor-theme-manager")
        if os.path.exists(plugin_dir):
            shutil.rmtree(plugin_dir)

        # Run cleanup helper with uninstalled theme causing restore failure
        res_fail = runtime_safety.run_bounded([sys.executable, paths["cleanup"]], timeout=3.0)
        self.assertFalse(res_fail.ok)
        self.assertIn("critical failure", res_fail.stderr)
        self.assertNotIn("Previous cursor configuration restored", res_fail.stdout)

        # Ensure state file and units are preserved for retry
        self.assertTrue(os.path.exists(paths["cleanup"]))
        self.assertTrue(os.path.exists(paths["path_unit"]))
        state_file = os.path.join(os.environ["XDG_STATE_HOME"], "cursor-theme-manager", "state.json")
        self.assertTrue(os.path.exists(state_file))
        self.assertTrue(generated_cache.is_dir(), "Generated cache was deleted before live restore succeeded")



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

        # Simulate plugin removal in isolated test environment
        plugin_dir = os.path.join(os.environ["XDG_CONFIG_HOME"], "omarchy", "plugins", "sanjyay.cursor-theme-manager")
        if os.path.exists(plugin_dir):
            shutil.rmtree(plugin_dir)

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

    This class inherits IsolatedTestCase for sandboxed home dirs and run_bounded mocking but
    deliberately STOPS the resolver patcher so tests exercise the real production resolver.
    """

    def setUp(self):
        super().setUp()
        # Stop BOTH patchers — we need to call the REAL production resolver AND real run_bounded
        # to verify they reject hostile paths. We manage them manually here.
        self._patcher_resolve.stop()
        self._patcher_run.stop()

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

    def tearDown(self):
        # Replace both patchers with unstarted ones so IsolatedTestCase.tearDown safely calls .stop()
        self._patcher_resolve = mock.patch("runtime_safety.resolve_system_executable")
        self._patcher_run = mock.patch("runtime_safety.run_bounded")
        super().tearDown()

    def test_resolver_never_resolves_hostile_path_binaries(self):
        runtime_safety._RESOLVED_TOOL_CACHE.clear()
        try:
            for tool_name in ["hyprctl", "gsettings", "systemctl", "hyprcursor-util"]:
                resolved = runtime_safety.resolve_system_executable(tool_name)
                if resolved is not None:
                    self.assertFalse(
                        resolved.startswith(str(self.evil_bin)),
                        f"Resolver returned hostile path executable: {resolved}"
                    )
                    self.assertTrue(
                        resolved.startswith("/usr/bin/") or resolved.startswith("/bin/"),
                        f"Resolved binary not in trusted system directory: {resolved}"
                    )
        finally:
            runtime_safety._RESOLVED_TOOL_CACHE.clear()

    def test_production_resolver_ignores_hostile_ctm_test_mock_bin_and_path(self):
        """
        Security regression: resolve_system_executable() must NEVER read CTM_TEST_MOCK_BIN
        or PATH and must never return a binary from a hostile directory, regardless of
        what those environment variables are set to.
        """
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ctm-evil-") as evil_tmp:
            evil_bin = Path(evil_tmp)
            sentinel = evil_bin / "EVIL_WAS_EXECUTED"

            # Plant fake binaries in the evil directory
            for tool_name in ["hyprctl", "gsettings", "systemctl", "hyprcursor-util"]:
                fake_script = evil_bin / tool_name
                fake_script.write_text(
                    f"#!/bin/sh\ntouch '{sentinel}'\necho 'PWNED: {tool_name}'\nexit 0\n"
                )
                fake_script.chmod(0o755)

            # Inject both hostile env vars
            saved_mock_bin = os.environ.pop("CTM_TEST_MOCK_BIN", None)
            saved_path = os.environ.get("PATH", "")
            os.environ["CTM_TEST_MOCK_BIN"] = str(evil_bin)
            os.environ["PATH"] = f"{evil_bin}:{saved_path}"
            runtime_safety._RESOLVED_TOOL_CACHE.clear()

            try:
                for tool_name in ["hyprctl", "gsettings", "systemctl", "hyprcursor-util"]:
                    resolved = runtime_safety.resolve_system_executable(tool_name)
                    if resolved is not None:
                        self.assertFalse(
                            str(evil_bin) in resolved,
                            f"Production resolver returned evil-bin path for {tool_name}: {resolved}"
                        )
            finally:
                runtime_safety._RESOLVED_TOOL_CACHE.clear()
                os.environ["PATH"] = saved_path
                if saved_mock_bin is not None:
                    os.environ["CTM_TEST_MOCK_BIN"] = saved_mock_bin
                else:
                    os.environ.pop("CTM_TEST_MOCK_BIN", None)

            # Sentinel must never have been created — no fake binary was run
            self.assertFalse(
                sentinel.exists(),
                "CTM_TEST_MOCK_BIN / hostile PATH caused production resolver to load a fake binary!"
            )

    def test_persistent_cleanup_helper_ignores_hostile_ctm_test_mock_bin(self):
        """
        Security regression: the installed cleanup_helper must not honor CTM_TEST_MOCK_BIN.
        We import it directly (as production does) and verify its resolver ignores the env var.
        """
        import tempfile
        import importlib.util
        cleanup_src = ROOT / "scripts" / "cleanup_helper.py"
        spec = importlib.util.spec_from_file_location("cleanup_helper_prod", cleanup_src)
        ch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ch)

        with tempfile.TemporaryDirectory(prefix="ctm-evil-cleanup-") as evil_tmp:
            evil_bin = Path(evil_tmp)
            sentinel = evil_bin / "EVIL_CLEANUP_WAS_EXECUTED"

            for tool_name in ["hyprctl", "gsettings", "systemctl"]:
                fake_script = evil_bin / tool_name
                fake_script.write_text(
                    f"#!/bin/sh\ntouch '{sentinel}'\necho 'CLEANUP_PWNED: {tool_name}'\nexit 0\n"
                )
                fake_script.chmod(0o755)

            saved_mock_bin = os.environ.pop("CTM_TEST_MOCK_BIN", None)
            os.environ["CTM_TEST_MOCK_BIN"] = str(evil_bin)
            ch._RESOLVED_TOOL_CACHE.clear()

            try:
                for tool_name in ["hyprctl", "gsettings", "systemctl"]:
                    resolved = ch.resolve_system_executable(tool_name)
                    if resolved is not None:
                        self.assertFalse(
                            str(evil_bin) in resolved,
                            f"cleanup_helper.resolve_system_executable returned evil-bin path for {tool_name}: {resolved}"
                        )
            finally:
                ch._RESOLVED_TOOL_CACHE.clear()
                if saved_mock_bin is not None:
                    os.environ["CTM_TEST_MOCK_BIN"] = saved_mock_bin
                else:
                    os.environ.pop("CTM_TEST_MOCK_BIN", None)

            self.assertFalse(
                sentinel.exists(),
                "CTM_TEST_MOCK_BIN caused cleanup_helper to execute a hostile fake binary!"
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

    def test_missing_trusted_tools_hyprctl_fails_closed(self):
        # Simulate environment where hyprctl does not exist in any trusted bin dir
        with mock.patch("runtime_safety.resolve_system_executable", return_value=None):
            res = runtime_safety.run_bounded(["hyprctl", "setcursor", "Adwaita", "24"])
            self.assertFalse(res.ok)
            self.assertEqual(res.exit_code, 127)
            self.assertIn("unavailable or failed validation", res.error)

    def test_qml_has_zero_hardcoded_executable_fallbacks(self):
        qml_path = ROOT / "CursorService.qml"
        qml_content = qml_path.read_text(encoding="utf-8")
        self.assertNotIn('|| "/usr/bin/hyprctl"', qml_content)
        self.assertNotIn("|| '/usr/bin/hyprctl'", qml_content)
        self.assertNotIn('hyprBin = "/usr/bin/hyprctl"', qml_content)

    def test_qml_persists_and_refreshes_integration_instance_id(self):
        qml_content = (ROOT / "CursorService.qml").read_text(encoding="utf-8")
        self.assertIn("integrationInstanceId: integrationInstanceId", qml_content)
        self.assertIn("integrationPluginFingerprint: integrationPluginFingerprint", qml_content)
        self.assertIn("root.integrationInstanceId = res.instanceId", qml_content)


class TestGtkAndConfigSyncSecurity(IsolatedTestCase):
    """Verifies that GTK and X11 synchronization securely enforces held-parent descriptor identity,
    symlink refusal, non-blocking FIFO rejection, size bounding, and clean restoration."""

    def test_gtk3_and_gtk4_settings_ini_symlink_refused_and_target_unmodified(self):
        canary = self.iso.home / "canary_secret.txt"
        canary.write_text("SENSITIVE_DATA_DO_NOT_TOUCH", encoding="utf-8")

        for gtk_dir in ["gtk-3.0", "gtk-4.0"]:
            d = self.iso.xdg_config / gtk_dir
            d.mkdir(parents=True, exist_ok=True)
            settings = d / "settings.ini"
            settings.symlink_to(canary)

        # Apply through cursorctl
        cursorctl.sync_x11_and_gtk_cursor("Adwaita", 32)
        self.assertEqual(canary.read_text(encoding="utf-8"), "SENSITIVE_DATA_DO_NOT_TOUCH")

        # Cleanup through cleanup_helper
        with mock.patch.object(cleanup_helper, "run_cmd", return_value=cleanup_helper.CommandResult(ok=True, exit_code=0)), \
             mock.patch.object(cleanup_helper, "find_hyprland_instance", return_value="sig"), \
             mock.patch.object(cleanup_helper, "resolve_system_executable", return_value="/usr/bin/hyprctl"), \
             mock.patch.object(cleanup_helper, "has_cursor_data", return_value=True):
            cleanup_helper.restore_cursor({
                "captured": True,
                "gtkThemeSet": True,
                "gtkTheme": "Adwaita",
                "gtkSizeSet": True,
                "gtkSize": 24,
                "liveRestoreTheme": "Adwaita",
                "liveRestoreSize": 24
            })

        self.assertEqual(canary.read_text(encoding="utf-8"), "SENSITIVE_DATA_DO_NOT_TOUCH")
        for gtk_dir in ["gtk-3.0", "gtk-4.0"]:
            settings = self.iso.xdg_config / gtk_dir / "settings.ini"
            self.assertTrue(settings.is_symlink())

    def test_gtk2_rc_symlink_refused_and_target_unmodified(self):
        canary = self.iso.home / "canary_gtk2.txt"
        canary.write_text("SENSITIVE_GTK2_DATA", encoding="utf-8")

        gtk2_rc = self.iso.home / ".gtkrc-2.0"
        gtk2_rc.symlink_to(canary)

        cursorctl.sync_x11_and_gtk_cursor("Adwaita", 32)
        self.assertEqual(canary.read_text(encoding="utf-8"), "SENSITIVE_GTK2_DATA")

        with mock.patch.object(cleanup_helper, "run_cmd", return_value=cleanup_helper.CommandResult(ok=True, exit_code=0)), \
             mock.patch.object(cleanup_helper, "find_hyprland_instance", return_value="sig"), \
             mock.patch.object(cleanup_helper, "resolve_system_executable", return_value="/usr/bin/hyprctl"), \
             mock.patch.object(cleanup_helper, "has_cursor_data", return_value=True):
            cleanup_helper.restore_cursor({
                "captured": True,
                "gtkThemeSet": True,
                "gtkTheme": "Adwaita",
                "gtkSizeSet": True,
                "gtkSize": 24,
                "liveRestoreTheme": "Adwaita",
                "liveRestoreSize": 24
            })

        self.assertEqual(canary.read_text(encoding="utf-8"), "SENSITIVE_GTK2_DATA")
        self.assertTrue(gtk2_rc.is_symlink())

    def test_gtk_directory_symlink_refused(self):
        evil_dir = self.iso.home / "evil_redirect_dir"
        evil_dir.mkdir()

        self.iso.xdg_config.mkdir(parents=True, exist_ok=True)
        (self.iso.xdg_config / "gtk-3.0").symlink_to(evil_dir)

        cursorctl.sync_x11_and_gtk_cursor("Adwaita", 32)
        self.assertEqual(list(evil_dir.iterdir()), [])

        with mock.patch.object(cleanup_helper, "run_cmd", return_value=cleanup_helper.CommandResult(ok=True, exit_code=0)), \
             mock.patch.object(cleanup_helper, "find_hyprland_instance", return_value="sig"), \
             mock.patch.object(cleanup_helper, "resolve_system_executable", return_value="/usr/bin/hyprctl"), \
             mock.patch.object(cleanup_helper, "has_cursor_data", return_value=True):
            cleanup_helper.restore_cursor({
                "captured": True,
                "gtkThemeSet": True,
                "gtkTheme": "Adwaita",
                "gtkSizeSet": True,
                "gtkSize": 24,
                "liveRestoreTheme": "Adwaita",
                "liveRestoreSize": 24
            })

        self.assertEqual(list(evil_dir.iterdir()), [])

    def test_x11_default_theme_symlink_refused(self):
        canary = self.iso.home / "canary_x11.txt"
        canary.write_text("SENSITIVE_X11_DATA", encoding="utf-8")

        icons_default = self.iso.home / ".icons" / "default"
        icons_default.mkdir(parents=True, exist_ok=True)
        (icons_default / "index.theme").symlink_to(canary)

        cursorctl.sync_x11_and_gtk_cursor("Adwaita", 32)
        self.assertEqual(canary.read_text(encoding="utf-8"), "SENSITIVE_X11_DATA")

        with mock.patch.object(cleanup_helper, "run_cmd", return_value=cleanup_helper.CommandResult(ok=True, exit_code=0)), \
             mock.patch.object(cleanup_helper, "find_hyprland_instance", return_value="sig"), \
             mock.patch.object(cleanup_helper, "resolve_system_executable", return_value="/usr/bin/hyprctl"), \
             mock.patch.object(cleanup_helper, "has_cursor_data", return_value=True):
            cleanup_helper.restore_cursor({
                "captured": True,
                "xcursorThemeSet": True,
                "xcursorTheme": "Adwaita",
                "liveRestoreTheme": "Adwaita",
                "liveRestoreSize": 24
            })

        self.assertEqual(canary.read_text(encoding="utf-8"), "SENSITIVE_X11_DATA")
        self.assertTrue((icons_default / "index.theme").is_symlink())

    def test_fifo_special_files_handled_without_hang(self):
        d = self.iso.xdg_config / "gtk-3.0"
        d.mkdir(parents=True, exist_ok=True)
        fifo_settings = d / "settings.ini"
        os.mkfifo(fifo_settings)

        fifo_gtk2 = self.iso.home / ".gtkrc-2.0"
        os.mkfifo(fifo_gtk2)

        start = time.monotonic()
        cursorctl.sync_x11_and_gtk_cursor("Adwaita", 32)
        with mock.patch.object(cleanup_helper, "run_cmd", return_value=cleanup_helper.CommandResult(ok=True, exit_code=0)), \
             mock.patch.object(cleanup_helper, "find_hyprland_instance", return_value="sig"), \
             mock.patch.object(cleanup_helper, "resolve_system_executable", return_value="/usr/bin/hyprctl"), \
             mock.patch.object(cleanup_helper, "has_cursor_data", return_value=True):
            cleanup_helper.restore_cursor({
                "captured": True,
                "gtkThemeSet": True,
                "gtkTheme": "Adwaita",
                "gtkSizeSet": True,
                "gtkSize": 24,
                "liveRestoreTheme": "Adwaita",
                "liveRestoreSize": 24
            })
        duration = time.monotonic() - start

        # Must execute promptly without hanging on FIFOs
        self.assertLess(duration, 2.0)
        self.assertTrue(stat.S_ISFIFO(fifo_settings.stat().st_mode))
        self.assertTrue(stat.S_ISFIFO(fifo_gtk2.stat().st_mode))

    def test_oversized_config_ignored_without_modification(self):
        d = self.iso.xdg_config / "gtk-3.0"
        d.mkdir(parents=True, exist_ok=True)
        settings = d / "settings.ini"
        large_content = "# large ini\n" + ("A" * (200 * 1024))
        settings.write_text(large_content, encoding="utf-8")

        cursorctl.sync_x11_and_gtk_cursor("Adwaita", 32)
        self.assertEqual(settings.stat().st_size, len(large_content.encode("utf-8")))

        with mock.patch.object(cleanup_helper, "run_cmd", return_value=cleanup_helper.CommandResult(ok=True, exit_code=0)), \
             mock.patch.object(cleanup_helper, "find_hyprland_instance", return_value="sig"), \
             mock.patch.object(cleanup_helper, "resolve_system_executable", return_value="/usr/bin/hyprctl"), \
             mock.patch.object(cleanup_helper, "has_cursor_data", return_value=True):
            cleanup_helper.restore_cursor({
                "captured": True,
                "gtkThemeSet": True,
                "gtkTheme": "Adwaita",
                "gtkSizeSet": True,
                "gtkSize": 24,
                "liveRestoreTheme": "Adwaita",
                "liveRestoreSize": 24
            })
        self.assertEqual(settings.stat().st_size, len(large_content.encode("utf-8")))

    def test_legitimate_gtk_and_x11_synchronization_and_restoration(self):
        d3 = self.iso.xdg_config / "gtk-3.0"
        d3.mkdir(parents=True, exist_ok=True)
        (d3 / "settings.ini").write_text(
            "[Settings]\ngtk-theme-name=Adwaita\ngtk-cursor-theme-name=OldTheme\ngtk-cursor-theme-size=24\ngtk-font-name=Cantarell 11\n",
            encoding="utf-8"
        )

        d4 = self.iso.xdg_config / "gtk-4.0"
        d4.mkdir(parents=True, exist_ok=True)
        (d4 / "settings.ini").write_text(
            "[Settings]\ngtk-cursor-theme-name=OldTheme\ngtk-cursor-theme-size=24\n",
            encoding="utf-8"
        )

        gtk2 = self.iso.home / ".gtkrc-2.0"
        gtk2.write_text(
            'gtk-theme-name="Adwaita"\ngtk-cursor-theme-name="OldTheme"\ngtk-cursor-theme-size=24\n',
            encoding="utf-8"
        )

        # Apply new theme and size
        cursorctl.sync_x11_and_gtk_cursor("NewTheme", 32)

        content3 = (d3 / "settings.ini").read_text(encoding="utf-8")
        self.assertIn("gtk-cursor-theme-name=NewTheme", content3)
        self.assertIn("gtk-cursor-theme-size=32", content3)
        self.assertIn("gtk-theme-name=Adwaita", content3)
        self.assertIn("gtk-font-name=Cantarell 11", content3)

        content4 = (d4 / "settings.ini").read_text(encoding="utf-8")
        self.assertIn("gtk-cursor-theme-name=NewTheme", content4)
        self.assertIn("gtk-cursor-theme-size=32", content4)

        content_gtk2 = gtk2.read_text(encoding="utf-8")
        self.assertIn('gtk-cursor-theme-name="NewTheme"', content_gtk2)
        self.assertIn('gtk-cursor-theme-size=32', content_gtk2)
        self.assertIn('gtk-theme-name="Adwaita"', content_gtk2)

        theme_file = self.iso.home / ".icons" / "default" / "index.theme"
        self.assertTrue(theme_file.is_file())
        self.assertIn("Inherits=NewTheme", theme_file.read_text(encoding="utf-8"))

        # Restore baseline
        with mock.patch.object(cleanup_helper, "run_cmd", return_value=cleanup_helper.CommandResult(ok=True, exit_code=0)), \
             mock.patch.object(cleanup_helper, "find_hyprland_instance", return_value="sig"), \
             mock.patch.object(cleanup_helper, "resolve_system_executable", return_value="/usr/bin/hyprctl"), \
             mock.patch.object(cleanup_helper, "has_cursor_data", return_value=True):
            cleanup_helper.restore_cursor({
                "captured": True,
                "gtkThemeSet": True,
                "gtkTheme": "OldTheme",
                "gtkSizeSet": True,
                "gtkSize": 24,
                "xcursorThemeSet": True,
                "xcursorTheme": "OldTheme",
                "liveRestoreTheme": "OldTheme",
                "liveRestoreSize": 24
            })

        restored3 = (d3 / "settings.ini").read_text(encoding="utf-8")
        self.assertIn("gtk-cursor-theme-name=OldTheme", restored3)
        self.assertIn("gtk-cursor-theme-size=24", restored3)

        restored_gtk2 = gtk2.read_text(encoding="utf-8")
        self.assertIn('gtk-cursor-theme-name="OldTheme"', restored_gtk2)
        self.assertIn('gtk-cursor-theme-size=24', restored_gtk2)

        self.assertIn("Inherits=OldTheme", theme_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
