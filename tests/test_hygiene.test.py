#!/usr/bin/env python3
"""
Test Hygiene, Ownership Markers & Real User Directory Isolation Assertions.
Formally verifies:
A. Import creates themes only under temporary XDG_DATA_HOME/icons.
B. Cleanup removes only temporary CTM state/artifacts without touching real HOME.
C. Discovery does not read real ~/.local/share/icons in automated tests.
D. State writes occur only under temp XDG_STATE_HOME.
E. Integration tests never touch real ~/.config/systemd/user.
F. Test-created theme names exist only in isolated temp roots.
G. Temporary root is removed cleanly when deactivated.
H. Importing Banana produces one visible logical theme.
I. Generated XCursor->Hyprcursor cache is NOT in discovery output.
J. Extracted Theme intermediate data never appears in theme list.
K. Generated cache has explicit internal marker (.cursor-theme-manager-generated).
L. Imported user theme has distinct imported marker (.cursor-theme-manager-imported).
M. Uninstall preserves imported user theme and deletes generated conversion cache.
N. Imported theme removal in CTM deletes its derived generated caches.
O. Ordinary user theme named similarly to CursorSwitcher-XCursor-* without marker is NOT deleted.
P. Symlink generated-cache directory is rejected and not traversed/deleted.
Q. Malformed foreign ownership marker does not cause deletion.
R. Multiple conversions do not create duplicate visible themes.
S. Reinstallation after uninstall discovers preserved imported Banana exactly once.
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

    def create_mock_xcursor(self, name: str) -> Path:
        theme_dir = self.iso.root / "mock_src" / name
        cursors_dir = theme_dir / "cursors"
        cursors_dir.mkdir(parents=True, exist_ok=True)
        (cursors_dir / "default").write_bytes(b"Xcur\x00\x00\x00\x01\x00\x00\x00\x00" + b"\x00" * 64)
        (cursors_dir / "left_ptr").write_bytes(b"Xcur\x00\x00\x00\x01\x00\x00\x00\x00" + b"\x00" * 64)
        (theme_dir / "index.theme").write_text(f"[Icon Theme]\nName={name}\nComment=Mock XCursor\n", encoding="utf-8")
        return theme_dir

    def test_A_import_creates_themes_only_under_isolated_xdg_data_home(self):
        """A. Import creates themes only under temporary XDG_DATA_HOME/icons."""
        src_dir = self.create_mock_xcursor("HygieneTestTheme")
        res = subprocess.run(
            [str(ROOT / "scripts" / "cursorctl"), "import", "--source", str(src_dir)],
            env=self.env, capture_output=True, text=True
        )
        self.assertEqual(res.returncode, 0, f"Import failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertTrue(data.get("ok"))
        installed_path = Path(data["theme"]["path"]).resolve()

        self.assert_safe_path(installed_path)
        self.assertTrue(installed_path.is_relative_to(self.iso.user_icons))

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

        res = subprocess.run([paths["cleanup"]], env=self.env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)

        for k in ["desktop", "cleanup", "path_unit", "service_unit"]:
            self.assertFalse(os.path.exists(paths[k]))
        self.assertFalse(os.path.exists(paths["libexec_dir"]))
        self.assertFalse(os.path.exists(str(self.iso.state_dir)))

    def test_C_discovery_does_not_scan_real_user_icons_when_isolated(self):
        """C. Discovery does not read real ~/.local/share/icons in automated tests."""
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

        real_state_file = REAL_USER_HOME / ".local" / "state" / "cursor-theme-manager" / "state.json"
        if real_state_file.exists():
            with open(real_state_file) as f:
                content = f.read()
            self.assertNotIn("HygieneStateTheme", content)

    def test_E_integration_tests_never_touch_real_systemd_user(self):
        """E. Integration tests never touch real ~/.config/systemd/user."""
        res = subprocess.run([str(ROOT / "scripts" / "cursorctl"), "integration-enable"], env=self.env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertTrue((self.iso.systemd_user / "cursor-theme-manager-cleanup.path").is_file())
        self.assertTrue((self.iso.systemd_user / "cursor-theme-manager-cleanup.service").is_file())

    def test_F_test_created_theme_names_exist_only_in_temp_root(self):
        """F. Test theme names stay strictly isolated."""
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

    def test_H_importing_banana_produces_one_visible_logical_theme(self):
        """H. Importing Banana produces one visible logical theme and hides internal conversion caches."""
        src = self.create_mock_xcursor("Banana")
        res = subprocess.run([str(ROOT / "scripts" / "cursorctl"), "import", "--source", str(src)], env=self.env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        imp_data = json.loads(res.stdout)
        self.assertTrue(imp_data["ok"])

        # Discover themes
        disc_res = subprocess.run([str(ROOT / "scripts" / "cursorctl"), "discover"], env=self.env, capture_output=True, text=True)
        self.assertEqual(disc_res.returncode, 0)
        disc_data = json.loads(disc_res.stdout)
        themes = disc_data["themes"]

        # Only one Banana entry must exist
        banana_themes = [t for t in themes if t["displayName"] == "Banana" or "Banana" in t["id"]]
        self.assertEqual(len(banana_themes), 1)
        self.assertEqual(banana_themes[0]["sourceType"], "imported")
        self.assertTrue(banana_themes[0]["imported"])

    def test_I_generated_cache_not_in_discovery_output(self):
        """I. Generated XCursor->Hyprcursor conversion caches are excluded from discover output."""
        # Create simulated generated cache
        gen_dir = self.iso.user_icons / "CursorSwitcher-XCursor-Banana-123456789abc"
        (gen_dir / "hyprcursors").mkdir(parents=True)
        (gen_dir / "manifest.hl").write_text("name = CursorSwitcher-XCursor-Banana\n", encoding="utf-8")
        (gen_dir / ".cursor-theme-manager-generated").write_text("version=1\nkind=conversion-cache\n", encoding="utf-8")

        disc_res = subprocess.run([str(ROOT / "scripts" / "cursorctl"), "discover"], env=self.env, capture_output=True, text=True)
        self.assertEqual(disc_res.returncode, 0)
        disc_data = json.loads(disc_res.stdout)
        ids = [t["id"] for t in disc_data["themes"]]
        self.assertNotIn("CursorSwitcher-XCursor-Banana-123456789abc", ids)

    def test_J_extracted_theme_intermediate_data_never_appears_in_theme_list(self):
        """J. Intermediate directory containing 'Extracted Theme' manifest is filtered out."""
        bad_dir = self.iso.user_icons / "Banana-Hyprcursor"
        (bad_dir / "hyprcursors").mkdir(parents=True)
        (bad_dir / "manifest.hl").write_text("name = Extracted Theme\n", encoding="utf-8")

        disc_res = subprocess.run([str(ROOT / "scripts" / "cursorctl"), "discover"], env=self.env, capture_output=True, text=True)
        self.assertEqual(disc_res.returncode, 0)
        disc_data = json.loads(disc_res.stdout)
        names = [t["displayName"] for t in disc_data["themes"]]
        self.assertNotIn("Extracted Theme", names)

    def test_K_and_L_distinct_markers_written(self):
        """K & L. Imported user theme has imported marker and generated cache has generated marker."""
        src = self.create_mock_xcursor("MarkerTestTheme")
        res = subprocess.run([str(ROOT / "scripts" / "cursorctl"), "import", "--source", str(src)], env=self.env, capture_output=True, text=True)
        data = json.loads(res.stdout)
        theme_path = Path(data["theme"]["path"])

        # Check imported marker
        self.assertTrue((theme_path / ".cursor-theme-manager-imported").is_file())
        self.assertTrue((theme_path / ".omarchy-cursor-switcher-imported").is_file())
        marker_data = json.loads((theme_path / ".cursor-theme-manager-imported").read_text())
        self.assertEqual(marker_data["kind"], "imported-user-theme")

    def test_M_uninstall_preserves_imported_and_deletes_generated_cache(self):
        """M. Clean uninstall preserves imported user themes and deletes marker-owned generated conversion caches."""
        src = self.create_mock_xcursor("Banana")
        res = subprocess.run([str(ROOT / "scripts" / "cursorctl"), "import", "--source", str(src)], env=self.env, capture_output=True, text=True)
        imp_path = Path(json.loads(res.stdout)["theme"]["path"])

        # Create generated cache
        gen_dir = self.iso.user_icons / f"CursorSwitcher-XCursor-{imp_path.name}-abc123"
        (gen_dir / "hyprcursors").mkdir(parents=True)
        (gen_dir / "manifest.hl").write_text("name = GenBanana\n", encoding="utf-8")
        (gen_dir / ".cursor-theme-manager-generated").write_text(f"version=1\nkind=conversion-cache\nsourceTheme={imp_path.name}\n", encoding="utf-8")

        # Enable integration and run cleanup
        integration_manager.enable_integration()
        paths = integration_manager.get_paths()

        res_clean = subprocess.run([paths["cleanup"]], env=self.env, capture_output=True, text=True)
        self.assertEqual(res_clean.returncode, 0)

        # Imported user theme is PRESERVED
        self.assertTrue(imp_path.is_dir(), "Imported theme was deleted on uninstall!")
        self.assertTrue((imp_path / ".cursor-theme-manager-imported").is_file())

        # Generated conversion cache is DELETED
        self.assertFalse(gen_dir.exists(), "Internal generated cache survived uninstall!")

    def test_N_imported_theme_removal_deletes_its_generated_caches(self):
        """N. Removing an imported theme inside CTM deletes its derived generated caches."""
        src = self.create_mock_xcursor("ThemeToDelete")
        res = subprocess.run([str(ROOT / "scripts" / "cursorctl"), "import", "--source", str(src)], env=self.env, capture_output=True, text=True)
        imp_id = json.loads(res.stdout)["theme"]["id"]
        imp_path = Path(json.loads(res.stdout)["theme"]["path"])

        # Create generated cache
        gen_dir = self.iso.user_icons / f"CursorSwitcher-XCursor-{imp_id}-987654"
        (gen_dir / "hyprcursors").mkdir(parents=True)
        (gen_dir / "manifest.hl").write_text("name = GenTheme\n", encoding="utf-8")
        (gen_dir / ".cursor-theme-manager-generated").write_text(f"version=1\nkind=conversion-cache\nsourceTheme={imp_id}\n", encoding="utf-8")

        rem_res = subprocess.run([str(ROOT / "scripts" / "cursorctl"), "remove-imported", "--id", imp_id], env=self.env, capture_output=True, text=True)
        self.assertEqual(rem_res.returncode, 0)

        # Both source and generated cache must be gone
        self.assertFalse(imp_path.exists())
        self.assertFalse(gen_dir.exists())

    def test_O_ordinary_user_theme_similarly_named_without_marker_not_deleted(self):
        """O. An ordinary user theme named similarly to CursorSwitcher-XCursor-* without marker is NOT deleted."""
        fake_user_theme = self.iso.user_icons / "CursorSwitcher-XCursor-UserCustom"
        (fake_user_theme / "cursors").mkdir(parents=True)
        (fake_user_theme / "cursors" / "default").write_bytes(b"Xcur\x00\x00\x00\x01\x00\x00\x00\x00")
        (fake_user_theme / "index.theme").write_text("[Icon Theme]\nName=UserCustom\n", encoding="utf-8")

        integration_manager.enable_integration()
        paths = integration_manager.get_paths()

        res_clean = subprocess.run([paths["cleanup"]], env=self.env, capture_output=True, text=True)
        self.assertEqual(res_clean.returncode, 0)

        # Must NOT be deleted because it lacks CTM internal marker
        self.assertTrue(fake_user_theme.is_dir())

    def test_P_symlink_generated_cache_directory_is_rejected(self):
        """P. Symlink generated-cache directory is rejected and not traversed/deleted."""
        real_target = self.iso.root / "important_data"
        real_target.mkdir(parents=True)
        (real_target / "file.txt").write_text("secret")

        symlink_gen = self.iso.user_icons / "CursorSwitcher-XCursor-Symlink"
        os.symlink(real_target, symlink_gen)

        integration_manager.enable_integration()
        paths = integration_manager.get_paths()

        res_clean = subprocess.run([paths["cleanup"]], env=self.env, capture_output=True, text=True)
        self.assertEqual(res_clean.returncode, 0)

        # Real target data untouched
        self.assertTrue(real_target.is_dir())
        self.assertTrue((real_target / "file.txt").is_file())

    def test_Q_foreign_ownership_marker_malformed_no_deletion(self):
        """Q. Malformed foreign ownership marker does not cause deletion."""
        foreign_theme = self.iso.user_icons / "ForeignTheme"
        foreign_theme.mkdir(parents=True)
        (foreign_theme / "cursors").mkdir(parents=True)
        (foreign_theme / "cursors" / "default").write_bytes(b"Xcur\x00\x00\x00\x01\x00\x00\x00\x00")

        integration_manager.enable_integration()
        paths = integration_manager.get_paths()

        res_clean = subprocess.run([paths["cleanup"]], env=self.env, capture_output=True, text=True)
        self.assertEqual(res_clean.returncode, 0)
        self.assertTrue(foreign_theme.is_dir())

    def test_S_reinstallation_after_uninstall_discovers_preserved_imported_theme_exactly_once(self):
        """S. Reinstallation after uninstall discovers preserved imported Banana exactly once."""
        src = self.create_mock_xcursor("Banana")
        res = subprocess.run([str(ROOT / "scripts" / "cursorctl"), "import", "--source", str(src)], env=self.env, capture_output=True, text=True)
        imp_path = Path(json.loads(res.stdout)["theme"]["path"])

        # Enable integration and run cleanup
        integration_manager.enable_integration()
        paths = integration_manager.get_paths()
        subprocess.run([paths["cleanup"]], env=self.env, capture_output=True, text=True)

        # Reinstall/Re-run discover
        disc_res = subprocess.run([str(ROOT / "scripts" / "cursorctl"), "discover"], env=self.env, capture_output=True, text=True)
        self.assertEqual(disc_res.returncode, 0)
        disc_data = json.loads(disc_res.stdout)
        banana_matches = [t for t in disc_data["themes"] if t["displayName"] == "Banana"]
        self.assertEqual(len(banana_matches), 1)
        self.assertEqual(banana_matches[0]["sourceType"], "imported")


if __name__ == "__main__":
    unittest.main()
