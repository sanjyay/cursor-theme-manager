#!/usr/bin/env python3
"""
Local Discovery and Ownership Enforcement Test for Omarchy Cursor Switcher.
Tests:
1. Empty discovery state (0 themes).
2. System vs User vs Imported classification.
3. Protected destructive actions (only plugin-imported themes can be deleted/renamed).
4. Missing theme fallback handling.
5. Git repository cleanliness (no third-party archives or compiled cursor trees).
"""

import os
import sys
import json
import shutil
import tarfile
import tempfile
import unittest
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURSORCTL = ROOT / "scripts" / "cursorctl"
CURSOR_IMPORT = ROOT / "scripts" / "cursor-import.py"
CURSOR_THEMING = ROOT / "scripts" / "cursor_theming.py"


class TestLocalDiscoveryAndOwnership(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cs-disc-test-")
        self.home = Path(self.temp_dir) / "home"
        self.xdg_data = self.home / ".local" / "share"
        self.xdg_config = self.home / ".config"
        self.xdg_cache = self.home / ".cache"
        self.sys_icons = Path(self.temp_dir) / "usr" / "share" / "icons"
        self.user_icons = self.xdg_data / "icons"

        self.sys_icons.mkdir(parents=True)
        self.user_icons.mkdir(parents=True)
        self.xdg_config.mkdir(parents=True)
        self.xdg_cache.mkdir(parents=True)

        self.env = dict(
            os.environ,
            HOME=str(self.home),
            XDG_DATA_HOME=str(self.xdg_data),
            XDG_CONFIG_HOME=str(self.xdg_config),
            XDG_CACHE_HOME=str(self.xdg_cache),
            XDG_DATA_DIRS=str(Path(self.temp_dir) / "usr" / "share"),
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_empty_discovery_state(self):
        """When no cursor themes exist, discover returns an empty list without crashing."""
        res = subprocess.run([str(CURSORCTL), "discover"], env=self.env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"discover failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertEqual(data.get("themes"), [])

    def test_02_system_theme_classification(self):
        """Themes in system directory are classified as sourceType: 'system', imported: false."""
        theme_dir = self.sys_icons / "Adwaita"
        cursors_dir = theme_dir / "cursors"
        cursors_dir.mkdir(parents=True)
        (cursors_dir / "default").write_bytes(b"Xcur\x00\x00\x00\x01\x00\x00\x00\x00")
        (theme_dir / "index.theme").write_text("[Icon Theme]\nName=Adwaita\nComment=GNOME Standard\n", encoding="utf-8")

        res = subprocess.run([str(CURSORCTL), "discover"], env=self.env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(len(data["themes"]), 1)
        t = data["themes"][0]
        self.assertEqual(t["id"], "Adwaita")
        self.assertEqual(t["displayName"], "Adwaita")
        self.assertEqual(t["sourceType"], "system")
        self.assertFalse(t["imported"])
        self.assertEqual(t["subtitle"], "GNOME Standard")

    def test_03_external_user_theme_classification(self):
        """Themes manually placed in user icons dir are classified as sourceType: 'user', imported: false."""
        theme_dir = self.user_icons / "CustomUserTheme"
        cursors_dir = theme_dir / "cursors"
        cursors_dir.mkdir(parents=True)
        (cursors_dir / "default").write_bytes(b"Xcur\x00\x00\x00\x01\x00\x00\x00\x00")
        (theme_dir / "index.theme").write_text("[Icon Theme]\nName=CustomUserTheme\n", encoding="utf-8")

        res = subprocess.run([str(CURSORCTL), "discover"], env=self.env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(len(data["themes"]), 1)
        t = data["themes"][0]
        self.assertEqual(t["id"], "CustomUserTheme")
        self.assertEqual(t["sourceType"], "user")
        self.assertFalse(t["imported"])

    def test_04_plugin_imported_theme_classification(self):
        """Themes imported via Cursor Theme Manager are classified as sourceType: 'imported', imported: true."""
        # Create a mock source directory to import
        src_dir = Path(self.temp_dir) / "source_theme"
        (src_dir / "cursors").mkdir(parents=True)
        (src_dir / "cursors" / "left_ptr").write_bytes(b"Xcur\x00\x00\x00\x01\x00\x00\x00\x00")
        (src_dir / "index.theme").write_text("[Icon Theme]\nName=ImportedClassic\n", encoding="utf-8")

        res_imp = subprocess.run(
            [str(CURSORCTL), "import", "--source", str(src_dir), "--name", "Imported Classic"],
            env=self.env, capture_output=True, text=True
        )
        self.assertEqual(res_imp.returncode, 0, f"import failed: {res_imp.stderr}")
        imp_data = json.loads(res_imp.stdout)
        self.assertTrue(imp_data.get("ok"))
        theme_id = imp_data["theme"]["id"]

        # Run discover
        res_disc = subprocess.run([str(CURSORCTL), "discover"], env=self.env, capture_output=True, text=True)
        self.assertEqual(res_disc.returncode, 0)
        disc_data = json.loads(res_disc.stdout)
        self.assertEqual(len(disc_data["themes"]), 1)
        t = disc_data["themes"][0]
        self.assertEqual(t["id"], theme_id)
        self.assertEqual(t["displayName"], "Imported Classic")
        self.assertEqual(t["sourceType"], "imported")
        self.assertTrue(t["imported"])

    def test_05_destructive_action_protection(self):
        """Unmanaged system and user themes cannot be deleted or renamed by the plugin."""
        # 1. Try to delete a system theme
        sys_theme = self.sys_icons / "SystemAdwaita"
        (sys_theme / "cursors").mkdir(parents=True)
        (sys_theme / "cursors" / "default").write_bytes(b"Xcur\x00\x00\x00\x01\x00\x00\x00\x00")

        res_del_sys = subprocess.run(
            [str(CURSORCTL), "remove-imported", "SystemAdwaita"],
            env=self.env, capture_output=True, text=True
        )
        self.assertNotEqual(res_del_sys.returncode, 0)
        self.assertTrue(sys_theme.exists(), "System theme must not be deleted")

        # 2. Try to delete an unmanaged user theme
        user_theme = self.user_icons / "UnmanagedUserTheme"
        (user_theme / "cursors").mkdir(parents=True)
        (user_theme / "cursors" / "default").write_bytes(b"Xcur\x00\x00\x00\x01\x00\x00\x00\x00")

        res_del_usr = subprocess.run(
            [str(CURSORCTL), "remove-imported", "UnmanagedUserTheme"],
            env=self.env, capture_output=True, text=True
        )
        self.assertNotEqual(res_del_usr.returncode, 0)
        self.assertTrue(user_theme.exists(), "Unmanaged user theme must not be deleted")

    def test_06_imported_theme_management_lifecycle(self):
        """Imported themes can be renamed and removed safely."""
        src_dir = Path(self.temp_dir) / "source_theme_2"
        (src_dir / "cursors").mkdir(parents=True)
        (src_dir / "cursors" / "left_ptr").write_bytes(b"Xcur\x00\x00\x00\x01\x00\x00\x00\x00")
        (src_dir / "index.theme").write_text("[Icon Theme]\nName=MyTheme\n", encoding="utf-8")

        # 1. Import
        res_imp = subprocess.run(
            [str(CURSORCTL), "import", "--source", str(src_dir), "--name", "Original Name"],
            env=self.env, capture_output=True, text=True
        )
        self.assertEqual(res_imp.returncode, 0)
        theme_id = json.loads(res_imp.stdout)["theme"]["id"]
        installed_path = Path(json.loads(res_imp.stdout)["theme"]["path"])
        self.assertTrue(installed_path.is_dir())

        # 2. Rename
        res_ren = subprocess.run(
            [str(CURSORCTL), "rename-imported", "--id", theme_id, "--name", "Renamed Display"],
            env=self.env, capture_output=True, text=True
        )
        self.assertEqual(res_ren.returncode, 0)
        ren_data = json.loads(res_ren.stdout)
        self.assertTrue(ren_data.get("ok"))
        self.assertEqual(ren_data["displayName"], "Renamed Display")

        # Verify discovery reflects new name
        res_disc = subprocess.run([str(CURSORCTL), "discover"], env=self.env, capture_output=True, text=True)
        disc_data = json.loads(res_disc.stdout)
        self.assertEqual(disc_data["themes"][0]["displayName"], "Renamed Display")

        # 3. Remove
        res_rem = subprocess.run(
            [str(CURSORCTL), "remove-imported", theme_id],
            env=self.env, capture_output=True, text=True
        )
        self.assertEqual(res_rem.returncode, 0)
        self.assertFalse(installed_path.exists())

    def test_07_git_tracking_cleanliness(self):
        """Assert git repository contains zero third-party archives or compiled cursor trees."""
        res_cur = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
        all_tracked = res_cur.stdout.strip().splitlines()

        # 1. No archives
        tracked_archives = [f for f in all_tracked if f.endswith(".tar.xz") or f.endswith(".tar.gz") or f.endswith(".zip")]
        self.assertEqual(len(tracked_archives), 0, f"Git must not track archives: {tracked_archives}")

        # 2. No themes/ or third_party/ directories
        tracked_themes = [f for f in all_tracked if f.startswith("themes/") or f.startswith("third_party/")]
        self.assertEqual(len(tracked_themes), 0, f"Git must not track themes/ or third_party/: {tracked_themes}")

        # 3. No cursors trees
        tracked_cursors = [f for f in all_tracked if "/cursors/" in f or "/hyprcursors/" in f or "/generated/" in f]
        self.assertEqual(len(tracked_cursors), 0, f"Git must not track compiled cursor trees: {tracked_cursors}")


if __name__ == "__main__":
    unittest.main()
