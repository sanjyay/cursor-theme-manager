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

# Add scripts directory to path
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

    def test_01_banana_resolves_all_roles_with_distinct_hashes(self):
        roles = cursor_theming.get_theme_role_previews("Banana")
        self.assertIn("default", roles)
        self.assertIn("pointer", roles)
        self.assertIn("text", roles)
        self.assertIn("move", roles)
        self.assertIn("resize", roles)
        self.assertIn("wait", roles)

        hashes = {}
        for r, p in roles.items():
            self.assertTrue(os.path.isfile(p), f"Preview file missing: {p}")
            data = Path(p).read_bytes()
            hashes[r] = hashlib.md5(data).hexdigest()

        # Verify all 6 roles have unique artwork
        distinct_count = len(set(hashes.values()))
        self.assertEqual(distinct_count, 6, f"Expected 6 distinct artwork hashes for Banana, got {distinct_count}")

    def test_02_adwaita_xcursor_resolves_distinct_roles(self):
        roles = cursor_theming.get_theme_role_previews("Adwaita")
        self.assertIn("default", roles)
        self.assertIn("pointer", roles)
        self.assertIn("text", roles)
        self.assertIn("move", roles)
        self.assertIn("resize", roles)
        self.assertIn("wait", roles)

        hashes = {}
        for r, p in roles.items():
            self.assertTrue(os.path.isfile(p), f"Preview file missing: {p}")
            data = Path(p).read_bytes()
            hashes[r] = hashlib.md5(data).hexdigest()

        # Verify Adwaita extracts distinct role PNGs
        distinct_count = len(set(hashes.values()))
        self.assertGreaterEqual(distinct_count, 5, f"Expected >= 5 distinct hashes for Adwaita, got {distinct_count}")
        # default and pointer must not be identical
        self.assertNotEqual(hashes["default"], hashes["pointer"])
        # default and text must not be identical
        self.assertNotEqual(hashes["default"], hashes["text"])

    def test_03_bibata_xcursor_resolves_distinct_roles(self):
        roles = cursor_theming.get_theme_role_previews("Bibata-Catppuccin-Mocha")
        self.assertIn("default", roles)
        self.assertIn("pointer", roles)
        self.assertIn("text", roles)
        self.assertIn("move", roles)
        self.assertIn("resize", roles)
        self.assertIn("wait", roles)

        hashes = {}
        for r, p in roles.items():
            self.assertTrue(os.path.isfile(p))
            data = Path(p).read_bytes()
            hashes[r] = hashlib.md5(data).hexdigest()

        distinct_count = len(set(hashes.values()))
        self.assertEqual(distinct_count, 6)

    def test_04_phinger_hyprcursor_resolves_distinct_roles(self):
        roles = cursor_theming.get_theme_role_previews("Phinger")
        self.assertIn("default", roles)
        self.assertIn("pointer", roles)
        self.assertIn("text", roles)
        self.assertIn("move", roles)
        self.assertIn("resize", roles)
        self.assertIn("wait", roles)

        hashes = {}
        for r, p in roles.items():
            self.assertTrue(os.path.isfile(p))
            data = Path(p).read_bytes()
            hashes[r] = hashlib.md5(data).hexdigest()

        distinct_count = len(set(hashes.values()))
        self.assertEqual(distinct_count, 6)

    def test_05_preview_cache_keys_are_role_specific(self):
        roles = cursor_theming.get_theme_role_previews("Banana")
        paths = list(roles.values())
        # All role paths must be unique filenames
        self.assertEqual(len(paths), len(set(paths)))
        for r, p in roles.items():
            self.assertTrue(p.endswith(f"{r}.svg") or p.endswith(f"{r}.png"))

    def test_06_unsupported_role_does_not_silently_fallback_to_default(self):
        # Create a mock theme fixture that only contains 'left_ptr' and 'xterm'
        fixture_dir = Path(self.temp_cache) / "MockTheme"
        cursors_dir = fixture_dir / "cursors"
        cursors_dir.mkdir(parents=True)
        # Copy a real cursor file for left_ptr and xterm
        adwaita_cursors = Path("/usr/share/icons/Adwaita/cursors")
        shutil.copy2(adwaita_cursors / "left_ptr", cursors_dir / "left_ptr")
        shutil.copy2(adwaita_cursors / "xterm", cursors_dir / "xterm")

        roles = cursor_theming.get_theme_role_previews("MockTheme", theme_path_hint=str(fixture_dir))
        self.assertIn("default", roles)
        self.assertIn("text", roles)
        # 'pointer', 'move', 'resize', 'wait' must NOT be in roles (or must NOT equal default)
        self.assertNotIn("pointer", roles, "Missing role should not silently map to default")
        self.assertNotIn("wait", roles, "Missing role should not silently map to default")

    def test_07_xcursor_symlink_aliases_resolve_properly(self):
        # Create a mock theme where 'hand2' is a symlink to 'pointer'
        fixture_dir = Path(self.temp_cache) / "SymlinkTheme"
        cursors_dir = fixture_dir / "cursors"
        cursors_dir.mkdir(parents=True)
        adwaita_cursors = Path("/usr/share/icons/Adwaita/cursors")
        shutil.copy2(adwaita_cursors / "pointer", cursors_dir / "pointer")
        os.symlink("pointer", cursors_dir / "hand2")

        roles = cursor_theming.get_theme_role_previews("SymlinkTheme", theme_path_hint=str(fixture_dir))
        self.assertIn("pointer", roles)
        self.assertTrue(os.path.isfile(roles["pointer"]))

if __name__ == "__main__":
    unittest.main()
