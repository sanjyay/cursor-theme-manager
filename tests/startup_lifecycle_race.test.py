#!/usr/bin/env python3
"""Installation identity and read-only startup lifecycle regression tests."""

import importlib
import os
import stat
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_isolation import IsolatedTestCase
import integration_manager


class TestStartupLifecycleRace(IsolatedTestCase):
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
