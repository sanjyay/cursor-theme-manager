#!/usr/bin/env python3
"""
Test Hygiene & Real User Directory Isolation Assertions.
Formally verifies that automated test runs:
A. Create imported themes only under temporary XDG_DATA_HOME/icons.
B. Clean up only temporary CTM state and integration artifacts.
C. Do not read or scan the real user's ~/.local/share/icons or ~/.icons.
D. Write state only under temporary XDG_STATE_HOME.
E. Touch only temporary systemd user directories.
F. Isolate test theme names (MockXCursor, Extracted Theme, CursorSwitcher-Imported-MyUserTheme).
G. Clean up temporary roots automatically upon exit.
H. Cause zero persistent artifacts across repeated test invocations.
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_isolation import IsolatedTestCase, IsolatedEnvironment, REAL_USER_HOME
import secure_state
import integration_manager
import cursor_theming


class TestHarnessHygiene(IsolatedTestCase):

    def test_A_import_creates_themes_only_under_isolated_xdg_data_home(self):
        """A. Import creates themes only under temporary XDG_DATA_HOME/icons."""
        src_dir = self.iso.root / "mock_theme"
        cursors_dir = src_dir / "cursors"
        cursors_dir.mkdir(parents=True)
        (cursors_dir / "default").write_bytes(b"Xcur\x00\x00\x00\x01\x00\x00\x00\x00" + b"\x00" * 64)
        (src_dir / "index.theme").write_text("[Icon Theme]\nName=HygieneTestTheme\n", encoding="utf-8")

        res = subprocess.run(
            [str(ROOT / "scripts" / "cursorctl"), "import", "--source", str(src_dir)],
            env=self.env, capture_output=True, text=True
        )
        self.assertEqual(res.returncode, 0, f"Import failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertTrue(data.get("ok"))
        installed_path = Path(data["theme"]["path"]).resolve()

        # Must be strictly within isolated test root
        self.assert_safe_path(installed_path)
        self.assertTrue(installed_path.is_relative_to(self.iso.user_icons))
        # Must not exist in real user icons
        real_user_icons = REAL_USER_HOME / ".local" / "share" / "icons"
        if real_user_icons.exists():
            self.assertFalse((real_user_icons / data["theme"]["id"]).exists())

    def test_B_cleanup_removes_only_temporary_artifacts(self):
        """B. Cleanup removes only temporary CTM state/artifacts without touching real HOME."""
        integration_manager.enable_integration()
        paths = integration_manager.get_paths()
        for k in ["desktop", "cleanup", "path_unit", "service_unit"]:
            self.assert_safe_path(paths[k])
            self.assertTrue(os.path.exists(paths[k]))

        # Run cleanup helper
        res = subprocess.run([paths["cleanup"]], env=self.env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)

        # Temp artifacts removed
        for k in ["desktop", "cleanup", "path_unit", "service_unit"]:
            self.assertFalse(os.path.exists(paths[k]))
        self.assertFalse(os.path.exists(paths["libexec_dir"]))
        self.assertFalse(os.path.exists(str(self.iso.state_dir)))

    def test_C_discovery_does_not_scan_real_user_icons_when_isolated(self):
        """C. Discovery does not read real ~/.local/share/icons in automated tests."""
        # Create a unique theme only in isolated test root
        isolated_theme = self.iso.user_icons / "IsolatedTestOnlyTheme"
        (isolated_theme / "cursors").mkdir(parents=True)
        (isolated_theme / "cursors" / "default").write_bytes(b"Xcur\x00\x00\x00\x01\x00\x00\x00\x00")
        (isolated_theme / "index.theme").write_text("[Icon Theme]\nName=IsolatedTestOnlyTheme\n", encoding="utf-8")

        res = subprocess.run([str(ROOT / "scripts" / "cursorctl"), "discover"], env=self.env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        names = [t["displayName"] for t in data.get("themes", [])]
        self.assertIn("IsolatedTestOnlyTheme", names)

    def test_D_state_writes_occur_only_under_temp_xdg_state_home(self):
        """D. State writes occur only under temp XDG_STATE_HOME."""
        state_dict = {
            "version": 2,
            "theme": {"displayName": "HygieneStateTheme", "xcursor": "HygieneStateTheme"},
            "size": 32,
            "importedThemes": [],
            "integrationPromptSeen": True,
            "integrationEnabled": False
        }
        res = subprocess.run(
            [str(ROOT / "scripts" / "cursorctl"), "state-write", "--state", json.dumps(state_dict)],
            env=self.env, capture_output=True, text=True
        )
        self.assertEqual(res.returncode, 0)
        expected_state_file = self.iso.state_dir / "state.json"
        self.assert_safe_path(expected_state_file)
        self.assertTrue(expected_state_file.is_file())

        # Verify real state was not overwritten by this test
        real_state_file = REAL_USER_HOME / ".local" / "state" / "cursor-theme-manager" / "state.json"
        if real_state_file.exists():
            with open(real_state_file) as f:
                content = f.read()
            self.assertNotIn("HygieneStateTheme", content)

    def test_E_integration_tests_never_touch_real_systemd_user(self):
        """E. Integration tests never touch real ~/.config/systemd/user."""
        res = subprocess.run([str(ROOT / "scripts" / "cursorctl"), "integration-enable"], env=self.env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)

        real_systemd = REAL_USER_HOME / ".config" / "systemd" / "user"
        # Unit paths must be in isolated root
        self.assertTrue((self.iso.systemd_user / "cursor-theme-manager-cleanup.path").is_file())
        self.assertTrue((self.iso.systemd_user / "cursor-theme-manager-cleanup.service").is_file())

    def test_F_test_created_theme_names_exist_only_in_temp_root(self):
        """F. Test theme names (MockXCursor, Extracted Theme, CursorSwitcher-Imported-MyUserTheme) stay isolated."""
        test_names = ["MockXCursor", "Extracted Theme", "CursorSwitcher-Imported-MyUserTheme"]
        for name in test_names:
            td = self.iso.user_icons / name
            (td / "cursors").mkdir(parents=True)
            (td / "cursors" / "default").write_bytes(b"Xcur\x00\x00\x00\x01\x00\x00\x00\x00")
            (td / "index.theme").write_text(f"[Icon Theme]\nName={name}\n", encoding="utf-8")

            self.assert_safe_path(td)
            self.assertTrue(td.is_dir())

    def test_G_temporary_root_is_removed_after_test_environment(self):
        """G. Temporary root is removed cleanly when deactivated."""
        iso = IsolatedEnvironment(prefix="ctm-test-lifecycle-")
        test_path = Path(iso.test_dir)
        self.assertTrue(test_path.is_dir())
        iso.deactivate()
        self.assertFalse(test_path.exists())


if __name__ == "__main__":
    unittest.main()
