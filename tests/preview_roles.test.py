#!/usr/bin/env python3
"""
Unit and integration tests for multi-role cursor preview extraction, alias resolution,
cache separation, and non-identical artwork verification across Hyprcursor and XCursor themes.
"""

import unittest
import os
import shutil
import tempfile
import hashlib
import json
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

import sys
sys.path.insert(0, str(SCRIPTS_DIR))
import cursor_theming


class TestPreviewRoles(unittest.TestCase):
    def setUp(self):
        self.temp_cache = tempfile.mkdtemp(prefix="test_roles_cache_")
        self.orig_roles_dir = cursor_theming.ROLES_DIR
        cursor_theming.ROLES_DIR = Path(self.temp_cache)

    def tearDown(self):
        cursor_theming.ROLES_DIR = self.orig_roles_dir
        shutil.rmtree(self.temp_cache, ignore_errors=True)

    def test_01_adwaita_xcursor_resolves_distinct_roles(self):
        roles = cursor_theming.get_theme_role_previews("Adwaita")
        self.assertIn("default", roles)
        self.assertIn("pointer", roles)
        self.assertIn("text", roles)
        self.assertIn("move", roles)
        self.assertIn("resize", roles)
        self.assertIn("wait", roles)

        hashes = {}
        for r in ["default", "pointer", "text", "move", "resize", "wait"]:
            p = roles[r]
            self.assertTrue(os.path.isfile(p), f"Preview file missing: {p}")
            data = Path(p).read_bytes()
            hashes[r] = hashlib.md5(data).hexdigest()

        distinct_count = len(set(hashes.values()))
        self.assertGreaterEqual(distinct_count, 5, f"Expected >= 5 distinct hashes for Adwaita, got {distinct_count}")
        self.assertNotEqual(hashes["default"], hashes["pointer"])
        self.assertNotEqual(hashes["default"], hashes["text"])

    def test_02_hotspot_metadata_is_extracted(self):
        roles = cursor_theming.get_theme_role_previews("Adwaita")
        self.assertIn("_meta", roles)
        meta = roles["_meta"]
        self.assertIn("default", meta)
        def_meta = meta["default"]
        self.assertIn("hotspot_x", def_meta)
        self.assertIn("hotspot_y", def_meta)
        self.assertGreaterEqual(def_meta["hotspot_x"], 0.0)
        self.assertGreaterEqual(def_meta["hotspot_y"], 0.0)

    def test_03_watch_alias_resolves_semantic_wait_role(self):
        # Create a mock theme that only has 'watch' and no 'wait'
        fixture_dir = Path(self.temp_cache) / "WatchTheme"
        cursors_dir = fixture_dir / "cursors"
        cursors_dir.mkdir(parents=True)
        adwaita_cursors = Path("/usr/share/icons/Adwaita/cursors")
        shutil.copy2(adwaita_cursors / "watch", cursors_dir / "watch")

        roles = cursor_theming.get_theme_role_previews("WatchTheme", theme_path_hint=str(fixture_dir))
        self.assertIn("wait", roles, "Semantic wait must resolve from 'watch' alias")
        self.assertTrue(os.path.isfile(roles["wait"]))

    def test_04_unsupported_role_does_not_silently_fallback_to_default(self):
        fixture_dir = Path(self.temp_cache) / "MockTheme"
        cursors_dir = fixture_dir / "cursors"
        cursors_dir.mkdir(parents=True)
        adwaita_cursors = Path("/usr/share/icons/Adwaita/cursors")
        shutil.copy2(adwaita_cursors / "left_ptr", cursors_dir / "left_ptr")
        shutil.copy2(adwaita_cursors / "xterm", cursors_dir / "xterm")

        roles = cursor_theming.get_theme_role_previews("MockTheme", theme_path_hint=str(fixture_dir))
        self.assertIn("default", roles)
        self.assertIn("text", roles)
        self.assertNotIn("pointer", roles)
        self.assertNotIn("wait", roles)

    def test_05_multi_role_dynamic_reflow(self):
        """Themes with 5 roles vs 6 roles have exact role subsets."""
        # 5 roles mock theme (no wait)
        fixture_dir = Path(self.temp_cache) / "FiveRoleTheme"
        cursors_dir = fixture_dir / "cursors"
        cursors_dir.mkdir(parents=True)
        adwaita_cursors = Path("/usr/share/icons/Adwaita/cursors")
        for alias in ["left_ptr", "hand2", "xterm", "all-scroll", "ew-resize"]:
            if (adwaita_cursors / alias).is_file():
                shutil.copy2(adwaita_cursors / alias, cursors_dir / alias)

        roles = cursor_theming.get_theme_role_previews("FiveRoleTheme", theme_path_hint=str(fixture_dir))
        found_roles = [k for k in roles if not k.startswith("_")]
        self.assertEqual(len(found_roles), 5)
        self.assertNotIn("wait", found_roles)


if __name__ == "__main__":
    unittest.main()
