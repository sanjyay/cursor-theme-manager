#!/usr/bin/env python3
"""
Unit tests for file_browser.py cursor archive and directory detection.
"""

import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TEST_DIR))

import file_browser
from test_isolation import IsolatedTestCase


class TestFileBrowser(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.root = self.iso.home / "Downloads"
        self.root.mkdir(parents=True, exist_ok=True)

    def test_01_detects_cursor_archives(self):
        # Create test archives with supported extensions
        (self.root / "Theme1.tar.gz").touch()
        (self.root / "Theme2.tar.xz").touch()
        (self.root / "Theme3.tar.bz2").touch()
        (self.root / "Theme4.zip").touch()
        (self.root / "unrelated.pdf").touch()
        (self.root / "image.png").touch()

        res = file_browser.list_directory(str(self.root))
        self.assertTrue(res["ok"])
        names = [e["name"] for e in res["entries"]]
        self.assertIn("Theme1.tar.gz", names)
        self.assertIn("Theme2.tar.xz", names)
        self.assertIn("Theme3.tar.bz2", names)
        self.assertIn("Theme4.zip", names)
        self.assertNotIn("unrelated.pdf", names)
        self.assertNotIn("image.png", names)

    def test_02_detects_cursor_theme_directories(self):
        # 1. Normal folder
        normal_dir = self.root / "MyDocuments"
        normal_dir.mkdir()

        # 2. XCursor theme folder (contains cursors/)
        xcursor_dir = self.root / "XCursorTheme"
        (xcursor_dir / "cursors").mkdir(parents=True)
        (xcursor_dir / "index.theme").write_text("[Icon Theme]\nName=Cool XCursor\n", encoding="utf-8")

        # 3. Hyprcursor theme folder (contains manifest.hl)
        hypr_dir = self.root / "HyprTheme"
        hypr_dir.mkdir()
        (hypr_dir / "manifest.hl").write_text("name = Cool Hypr\n", encoding="utf-8")

        res = file_browser.list_directory(str(self.root))
        self.assertTrue(res["ok"])

        entries = {e["name"]: e for e in res["entries"]}
        self.assertFalse(entries["MyDocuments"]["is_theme_dir"])
        self.assertTrue(entries["XCursorTheme"]["is_theme_dir"])
        self.assertEqual(entries["XCursorTheme"]["theme_name"], "Cool XCursor")
        self.assertTrue(entries["HyprTheme"]["is_theme_dir"])

    def test_03_sorts_theme_dirs_first_then_folders_then_archives(self):
        (self.root / "a_normal_folder").mkdir()
        theme_dir = self.root / "z_theme_folder"
        (theme_dir / "cursors").mkdir(parents=True)
        (self.root / "m_archive.tar.xz").touch()

        res = file_browser.list_directory(str(self.root))
        entries = res["entries"]
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0]["name"], "z_theme_folder") # Theme dir (order 0)
        self.assertEqual(entries[1]["name"], "a_normal_folder") # Normal dir (order 1)
        self.assertEqual(entries[2]["name"], "m_archive.tar.xz") # Archive (order 2)

    def test_04_parent_and_can_go_up_navigation(self):
        sub = self.root / "subdir"
        sub.mkdir()
        res = file_browser.list_directory(str(sub))
        self.assertTrue(res["ok"])
        self.assertEqual(res["parent"], str(self.root))
        self.assertTrue(res["can_go_up"])


if __name__ == "__main__":
    unittest.main()
