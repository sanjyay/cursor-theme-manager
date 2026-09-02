#!/usr/bin/env python3
"""Persistent remove/reinstall recovery and state-lock interruption tests."""

import fcntl
import importlib.machinery
import importlib.util
import multiprocessing
import os
import signal
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_isolation import IsolatedTestCase
import cleanup_helper
import integration_manager
import runtime_safety
import secure_state

loader = importlib.machinery.SourceFileLoader("ctm_cursorctl_persistent", str(SCRIPTS / "cursorctl"))
spec = importlib.util.spec_from_loader(loader.name, loader)
cursorctl = importlib.util.module_from_spec(spec)
loader.exec_module(cursorctl)


BASELINE = {
    "captured": True,
    "hyprcursorThemeSet": True, "hyprcursorTheme": "Adwaita",
    "hyprcursorSizeSet": True, "hyprcursorSize": 24,
    "xcursorThemeSet": True, "xcursorTheme": "Adwaita",
    "xcursorSizeSet": True, "xcursorSize": 24,
    "gtkThemeSet": True, "gtkTheme": "Adwaita",
    "gtkSizeSet": True, "gtkSize": 24,
    "liveRestoreBackend": "gtk", "liveRestoreTheme": "Adwaita", "liveRestoreSize": 24,
    "liveBackend": "gtk", "liveTheme": "Adwaita", "liveSize": 24,
}


def hold_directory_lock(path, ready_conn):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    fcntl.flock(fd, fcntl.LOCK_EX)
    ready_conn.send(True)
    ready_conn.close()
    while True:
        time.sleep(1)


class TestPersistentLifecycleRecovery(IsolatedTestCase):
    def _identity(self):
        result = integration_manager.ensure_installation_identity()
        self.assertTrue(result["ok"], result)
        return result

    def _next_identity(self):
        marker = self.iso.plugin_dir / ".installation_instance"
        if marker.exists():
            marker.unlink()
        return self._identity()

    def _publish_managed_state(self, fingerprint, integration_enabled=False, instance=None):
        state = secure_state.read_state()
        state.update({
            "theme": {"displayName": "Banana", "hyprcursor": "Banana", "xcursor": "Banana", "path": "/tmp/Banana"},
            "size": 64,
            "integrationEnabled": integration_enabled,
            "integrationPromptSeen": integration_enabled,
            "integrationInstanceId": instance,
            "integrationPluginFingerprint": fingerprint,
            "preCtmCursor": dict(BASELINE),
            "originalCursor": dict(BASELINE),
            "cursorModifiedByCtm": True,
        })
        self.assertTrue(secure_state.write_state(state))

    def _first_mutation(self, fingerprint):
        calls = []

        def fake_run(argv, **_kwargs):
            calls.append(list(argv))
            return runtime_safety.BoundedResult(0, b"ok\n", b"")

        with mock.patch.object(cursorctl.secure_state, "capture_original_cursor", return_value=dict(BASELINE)), \
             mock.patch.object(cursorctl, "run_bounded", side_effect=fake_run):
            cursorctl.perform_live_cursor_mutation("Banana", 64, fingerprint)
        self.assertEqual([call for call in calls if len(call) > 1 and call[1] == "setcursor"], [["hyprctl", "setcursor", "Banana", "64"]])
        state = secure_state.read_state()
        self.assertEqual(state["integrationPluginFingerprint"], fingerprint)
        self.assertTrue(state["preCtmCursor"]["captured"])
        self.assertTrue(state["cursorModifiedByCtm"])

    def test_exact_broken_state_is_orphaned_recovered_then_writable(self):
        old = self._identity()
        self._publish_managed_state(old["pluginFingerprint"], integration_enabled=False, instance=None)
        current = self._next_identity()

        status = integration_manager.get_status()
        self.assertTrue(status["recoveryPending"])
        self.assertTrue(status["recoveryOrphaned"])
        self.assertFalse(status["recoveryActorPresent"])

        with mock.patch.object(cleanup_helper, "restore_cursor", return_value=True):
            result = cleanup_helper.reconcile_orphaned_state(current["pluginFingerprint"])
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["reconciled"], result)
        self.assertFalse((self.iso.state_dir / "state.json").exists())
        self.assertFalse(integration_manager.get_status()["recoveryPending"])
        self._first_mutation(current["pluginFingerprint"])

    def test_same_owner_atomic_replacement_is_deleted_not_orphaned(self):
        old = self._identity()
        self._publish_managed_state(old["pluginFingerprint"])
        original_identity = secure_state.get_state_file_identity()
        replacement = secure_state.read_state()
        replacement["size"] = 80
        self.assertTrue(secure_state.write_state(replacement))
        self.assertNotEqual(original_identity, secure_state.get_state_file_identity())

        self.assertTrue(cleanup_helper.remove_secure_state_dir(
            None, old["pluginFingerprint"], original_identity
        ))
        self.assertFalse((self.iso.state_dir / "state.json").exists())

    def test_orphan_restore_failure_preserves_recovery_state(self):
        old = self._identity()
        self._publish_managed_state(old["pluginFingerprint"])
        current = self._next_identity()
        before = (self.iso.state_dir / "state.json").read_bytes()

        with mock.patch.object(cleanup_helper, "restore_cursor", return_value=False):
            result = cleanup_helper.reconcile_orphaned_state(current["pluginFingerprint"])
        self.assertFalse(result["ok"], result)
        self.assertEqual((self.iso.state_dir / "state.json").read_bytes(), before)
        self.assertTrue(integration_manager.get_status()["recoveryPending"])

    def test_qml_quarantines_then_invokes_bound_orphan_reconciliation(self):
        qml = (ROOT / "CursorService.qml").read_text(encoding="utf-8")
        self.assertIn("if (root._loadedState.recoveryOrphaned) {", qml)
        self.assertIn("root.requestOrphanedRecovery()", qml)
        self.assertIn('mutationCommand([helperPath, "recovery-reconcile"])', qml)
        self.assertIn("root.enterRecoveryQuarantine()", qml)
        self.assertIn("recoveryReconcileProcess.running = false", qml)

    def test_twenty_generations_never_inherit_orphan_or_fail_first_mutation(self):
        identities = set()
        current = self._identity()
        identities.add(current["pluginFingerprint"])
        self._first_mutation(current["pluginFingerprint"])

        for _generation in range(1, 20):
            current = self._next_identity()
            identities.add(current["pluginFingerprint"])
            status = integration_manager.get_status()
            self.assertTrue(status["recoveryOrphaned"], status)
            with mock.patch.object(cleanup_helper, "restore_cursor", return_value=True):
                recovered = cleanup_helper.reconcile_orphaned_state(current["pluginFingerprint"])
            self.assertTrue(recovered["ok"], recovered)
            self.assertFalse(integration_manager.get_status()["recoveryPending"])
            self._first_mutation(current["pluginFingerprint"])

        self.assertEqual(len(identities), 20)

    def test_killed_lock_holder_leaves_no_stale_lock(self):
        parent_conn, child_conn = multiprocessing.Pipe(duplex=False)
        proc = multiprocessing.Process(target=hold_directory_lock, args=(str(self.iso.state_dir), child_conn))
        proc.start()
        child_conn.close()
        self.assertTrue(parent_conn.recv())
        parent_conn.close()
        os.kill(proc.pid, signal.SIGKILL)
        proc.join(timeout=3)
        self.assertFalse(proc.is_alive())

        started = time.monotonic()
        self.assertTrue(secure_state.write_state({"integrationEnabled": False}))
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertFalse(any(self.iso.state_dir.glob("*lock*")))

    def test_cleanup_interruptions_are_retryable_across_generations(self):
        current = self._identity()
        for checkpoint in (
            "after-state-load", "before-compare-delete",
            "after-compare-delete", "before-artifact-cleanup",
        ):
            enabled = integration_manager.enable_integration(current["pluginFingerprint"])
            self.assertTrue(enabled["ok"], enabled)
            self._publish_managed_state(
                current["pluginFingerprint"], integration_enabled=True,
                instance=enabled["instanceId"],
            )
            old = current
            current = self._next_identity()

            def interrupt(stage):
                if stage == checkpoint:
                    raise KeyboardInterrupt(stage)

            with mock.patch.object(cleanup_helper, "restore_cursor", return_value=True), \
                 mock.patch.object(cleanup_helper, "run_cmd"), \
                 mock.patch.object(cleanup_helper, "_cleanup_checkpoint", side_effect=interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    cleanup_helper.execute_cleanup(enabled["instanceId"], old["pluginFingerprint"])

            # Kernel flock state is process/descriptor managed. A retry can
            # always finish the old generation after interruption.
            with mock.patch.object(cleanup_helper, "restore_cursor", return_value=True), \
                 mock.patch.object(cleanup_helper, "run_cmd"):
                with self.assertRaises(SystemExit) as finished:
                    cleanup_helper.execute_cleanup(enabled["instanceId"], old["pluginFingerprint"])
            self.assertEqual(finished.exception.code, 0)
            self.assertFalse(integration_manager.get_status()["recoveryPending"])
            self._first_mutation(current["pluginFingerprint"])


if __name__ == "__main__":
    unittest.main()
