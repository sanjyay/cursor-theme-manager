#!/usr/bin/env python3
"""Installation identity and read-only startup lifecycle regression tests."""

import importlib
import importlib.machinery
import importlib.util
import contextlib
import io
import json
import os
import stat
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_isolation import IsolatedTestCase
import integration_manager
import runtime_safety
import secure_state

loader = importlib.machinery.SourceFileLoader("ctm_cursorctl_startup", str(SCRIPTS / "cursorctl"))
spec = importlib.util.spec_from_loader(loader.name, loader)
cursorctl = importlib.util.module_from_spec(spec)
loader.exec_module(cursorctl)


class TestStartupLifecycleRace(IsolatedTestCase):
    def managed_state(self):
        identity = integration_manager.ensure_installation_identity()
        self.assertTrue(identity["ok"], identity)
        state = secure_state.read_state()
        state.update({
            "theme": {"displayName": "Adwaita", "xcursor": "Adwaita"},
            "size": 64,
            "cursorModifiedByCtm": True,
            "integrationPluginFingerprint": identity["pluginFingerprint"],
            "preCtmCursor": {
                "captured": True, "liveRestoreBackend": "gtk",
                "liveRestoreTheme": "Adwaita", "liveRestoreSize": 24,
            },
        })
        self.assertTrue(secure_state.write_state(state))
        return identity

    def restore(self, run, wait=None):
        identity = integration_manager.get_plugin_installation_fingerprint()
        emitted = []
        with mock.patch.object(sys, "argv", ["cursorctl", "state-read", "--restore-live", "--plugin-fingerprint", identity]), \
             mock.patch.object(cursorctl, "run_bounded", side_effect=run), \
             mock.patch.object(cursorctl, "emit_bounded_json", side_effect=lambda value, **kwargs: emitted.append(value)), \
             mock.patch.object(cursorctl, "sync_x11_and_gtk_cursor"), \
             contextlib.redirect_stderr(io.StringIO()):
            if wait is None:
                cursorctl.main()
            else:
                with mock.patch.object(cursorctl, "wait_for_startup_cursor", side_effect=wait):
                    cursorctl.main()
        cursorctl._REQUEST_PLUGIN_FINGERPRINT = None
        return emitted[-1]

    def test_saved_size_is_applied_after_delayed_startup_reveal(self):
        self.managed_state()
        before = secure_state.read_state()["preCtmCursor"]
        events = []
        pending = True
        live_size = 24

        def run(argv, **kwargs):
            nonlocal pending, live_size
            if argv[1] == "repl":
                if not events:
                    events.append("pending")
                    return runtime_safety.BoundedResult(0, b"true\n", b"")
                pending = False
                live_size = 24
                events.append("startup-reveal:24")
                return runtime_safety.BoundedResult(0, b"false\n", b"")
            if argv[1] == "setcursor":
                live_size = int(argv[-1])
                events.append("ctm:64")
            return runtime_safety.BoundedResult(0, b"ok\n", b"")

        result = self.restore(run)
        if pending:
            live_size = 24
        self.assertEqual(live_size, 64)
        self.assertLess(events.index("startup-reveal:24"), events.index("ctm:64"))
        self.assertNotIn("restoreError", result)
        self.assertEqual(secure_state.read_state()["preCtmCursor"], before)

    def test_startup_wait_is_bounded_and_does_not_mutate_on_timeout(self):
        self.managed_state()
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            return runtime_safety.BoundedResult(0, b"true\n", b"")

        with mock.patch.object(cursorctl.time, "monotonic", side_effect=[0, 0, 21, 21]), \
             mock.patch.object(cursorctl.time, "sleep"):
            result = self.restore(run)
        self.assertIn("still restoring", result["restoreError"])
        self.assertFalse(any("setcursor" in call for call in calls))

    def test_generation_change_during_startup_wait_prevents_restore(self):
        self.managed_state()
        calls = []

        def replace_install():
            (self.iso.plugin_dir / ".installation_instance").unlink()
            integration_manager.ensure_installation_identity()

        result = self.restore(lambda argv, **kwargs: calls.append(argv), wait=replace_install)
        self.assertIn("state changed", result["restoreError"])
        self.assertFalse(calls)

    def test_missing_baseline_is_not_recaptured_during_boot(self):
        self.managed_state()
        state = secure_state.read_state()
        state["preCtmCursor"] = None
        state["originalCursor"] = None
        (self.iso.state_dir / "state.json").write_text(json.dumps(state))
        calls = []
        result = self.restore(lambda argv, **kwargs: calls.append(argv), wait=lambda: None)
        self.assertIn("baseline is unavailable", result["restoreError"])
        self.assertFalse(calls)

    def test_older_compositor_without_lua_needs_no_startup_wait(self):
        with mock.patch.object(cursorctl, "run_bounded", return_value=runtime_safety.BoundedResult(1, b"unknown request\n", b"")):
            cursorctl.wait_for_startup_cursor()

    def test_unexpected_startup_probe_response_is_reported(self):
        with mock.patch.object(cursorctl, "run_bounded", return_value=runtime_safety.BoundedResult(0, b"unexpected\n", b"")):
            with self.assertRaisesRegex(RuntimeError, "Could not check"):
                cursorctl.wait_for_startup_cursor()

    def test_unmanaged_startup_does_not_probe_or_change_the_cursor(self):
        integration_manager.ensure_installation_identity()
        calls = []
        result = self.restore(lambda argv, **kwargs: calls.append(argv))
        self.assertFalse(calls)
        self.assertFalse(result.get("cursorModifiedByCtm"))

    def test_previous_installation_is_quarantined_without_replay(self):
        self.managed_state()
        (self.iso.plugin_dir / ".installation_instance").unlink()
        integration_manager.ensure_installation_identity()
        calls = []
        result = self.restore(lambda argv, **kwargs: calls.append(argv))
        self.assertTrue(result["recoveryPending"])
        self.assertIsNone(result["theme"])
        self.assertFalse(calls)

    def plugin_dir(self):
        path = Path(os.environ["XDG_CONFIG_HOME"]) / "omarchy" / "plugins" / integration_manager.PLUGIN_ID
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
        return path

    def test_installation_identity_exists_before_state_adoption(self):
        plugin = self.plugin_dir()
        result = integration_manager.ensure_installation_identity()
        self.assertTrue(result["ok"], result)
        marker = plugin / ".installation_instance"
        self.assertRegex(marker.read_text().strip(), r"^[a-f0-9]{32}$")
        self.assertEqual(stat.S_IMODE(marker.stat().st_mode), 0o600)
        self.assertEqual(integration_manager.get_plugin_installation_fingerprint(), result["pluginFingerprint"])
        self.assertFalse((Path(os.environ["XDG_STATE_HOME"]) / "cursor-theme-manager" / "state.json").exists())

    def test_identity_is_stable_within_install_and_unique_across_generations(self):
        identities = set()
        fingerprints = set()
        for _generation in ("A", "B", "C", "D", "E"):
            plugin = self.plugin_dir()
            first = integration_manager.ensure_installation_identity()
            second = integration_manager.ensure_installation_identity()
            self.assertEqual(first["instanceToken"], second["instanceToken"])
            identities.add(first["instanceToken"])
            fingerprints.add(first["pluginFingerprint"])
            (plugin / ".installation_instance").unlink()
            plugin.rmdir()
        self.assertEqual(len(identities), 5)
        self.assertEqual(len(fingerprints), 5)

    def test_unsafe_preplanted_identity_is_rejected(self):
        plugin = self.plugin_dir()
        marker = plugin / ".installation_instance"
        marker.write_text("attacker-controlled\n")
        marker.chmod(0o600)
        result = integration_manager.ensure_installation_identity()
        self.assertFalse(result["ok"])
        self.assertIn("invalid or unsafe", result["error"])

    def test_actual_qml_startup_has_no_mutation_route(self):
        qml = (ROOT / "CursorService.qml").read_text(encoding="utf-8")
        initialize = qml.split("function initialize(currentXcursor)", 1)[1].split("function requestPreview", 1)[0]
        self.assertNotIn("enqueueApply(", initialize)
        self.assertNotIn("setcursor-live", initialize)
        self.assertNotIn("integration-enable", initialize)
        self.assertIn("Startup is strictly read-only", initialize)
        self.assertIn("if (!theme || !ready || recoveryPending || _destroying) return", qml)
        self.assertIn("if (!ready || recoveryPending || _destroying) return", qml)
        self.assertIn("root.enterRecoveryQuarantine()", qml)
        self.assertIn("cancelMutationWork()", qml)
        self.assertIn("root.keepPanelOpenAfterIntegration()", qml)

    def test_recovery_quarantine_is_enforced_by_helper(self):
        helper = (SCRIPTS / "cursorctl").read_text(encoding="utf-8")
        self.assertIn('lifecycle_status.get("recoveryPending")', helper)
        self.assertIn('"recoveryPending": True', helper)
        self.assertIn("expected_fingerprint != current_fingerprint", helper)


if __name__ == "__main__":
    unittest.main()
