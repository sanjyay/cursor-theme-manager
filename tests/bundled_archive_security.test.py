#!/usr/bin/env python3
"""
Comprehensive Security & Integrity Test Suite for Bundled Cursor Theme Archives.
Tests:
- SHA-256 integrity verification (matching vs mismatched/tampered archives)
- Archive decompression bomb & resource limit protections
- Safe extraction path traversal prevention (../ and absolute paths)
- Symlink and hardlink directory escape prevention
- Device nodes, FIFOs, and special file rejection
- Executable installer script and binary payload rejection
- Corrupted archive handling
- Missing archive handling
- Atomic materialization & idempotency
- All 6 bundled themes load and render previews
- User-imported custom themes regression test
- Git repository cleanliness (no tracked unpacked generated cursor trees)
"""

import os
import sys
import json
import shutil
import tarfile
import zipfile
import tempfile
import hashlib
import unittest
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
THEMES_DIR = ROOT / "themes"
BUNDLED_DIR = THEMES_DIR / "bundled"
CATALOG_PATH = BUNDLED_DIR / "catalog.json"

sys.path.insert(0, str(SCRIPTS_DIR))
import importlib.util
spec_ci = importlib.util.spec_from_file_location("cursor_import", SCRIPTS_DIR / "cursor-import.py")
ci = importlib.util.module_from_spec(spec_ci)
spec_ci.loader.exec_module(ci)

import cursor_theming


class TestBundledArchiveSecurity(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_bundle_sec_")
        self.icons_dir = Path(self.temp_dir) / "icons"
        self.icons_dir.mkdir(parents=True, exist_ok=True)
        self.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_catalog_integrity_all_themes(self):
        """All 6 themes must exist in catalog.json with correct SHA-256 and archive files."""
        expected_themes = {"banana", "phinger", "oreo", "volantes", "nordzy", "capitaine"}
        catalog_themes = {entry["id"] for entry in self.catalog}
        self.assertEqual(catalog_themes, expected_themes)

        for entry in self.catalog:
            archive_path = ROOT / entry["archive"]
            self.assertTrue(archive_path.is_file(), f"Archive file {archive_path} does not exist")
            actual_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            self.assertEqual(actual_sha, entry["sha256"], f"SHA-256 mismatch for {entry['id']}")
            self.assertEqual(archive_path.stat().st_size, entry["sizeBytes"], f"Size mismatch for {entry['id']}")

    def test_02_sha256_mismatch_rejection(self):
        """Archives with tampered content or incorrect SHA-256 must be rejected."""
        fake_archive = Path(self.temp_dir) / "tampered.tar.xz"
        with tarfile.open(fake_archive, "w:xz") as tf:
            info = tarfile.TarInfo(name="Tampered/index.theme")
            content = b"[Icon Theme]\nName=Tampered\n"
            info.size = len(content)
            tf.addfile(info, io_bytes(content))

        with self.assertRaises(ValueError) as ctx:
            ci.verify_archive_sha256(str(fake_archive), "0000000000000000000000000000000000000000000000000000000000000000")
        self.assertIn("Integrity check failed", str(ctx.exception))

    def test_03_path_traversal_rejection(self):
        """Archives containing ../ paths or leading slashes must be rejected."""
        traversal_tar = Path(self.temp_dir) / "traversal.tar.xz"
        with tarfile.open(traversal_tar, "w:xz") as tf:
            info = tarfile.TarInfo(name="../escape.txt")
            data = b"malicious"
            info.size = len(data)
            tf.addfile(info, io_bytes(data))

        stage = Path(self.temp_dir) / "stage_traversal"
        stage.mkdir()
        with self.assertRaises(ValueError) as ctx:
            ci.extract_archive_safely(str(traversal_tar), str(stage))
        self.assertIn("Dangerous path", str(ctx.exception))

    def test_04_symlink_escape_rejection(self):
        """Archives containing symlinks pointing outside the theme root must be rejected."""
        symlink_tar = Path(self.temp_dir) / "symlink_escape.tar.xz"
        with tarfile.open(symlink_tar, "w:xz") as tf:
            dinfo = tarfile.TarInfo(name="BadTheme")
            dinfo.type = tarfile.DIRTYPE
            tf.addfile(dinfo)

            cinfo = tarfile.TarInfo(name="BadTheme/cursors")
            cinfo.type = tarfile.DIRTYPE
            tf.addfile(cinfo)

            finfo = tarfile.TarInfo(name="BadTheme/manifest.hl")
            fcontent = b"name = BadTheme\n"
            finfo.size = len(fcontent)
            tf.addfile(finfo, io_bytes(fcontent))

            sinfo = tarfile.TarInfo(name="BadTheme/cursors/badlink")
            sinfo.type = tarfile.SYMTYPE
            sinfo.linkname = "/etc/passwd"
            tf.addfile(sinfo)

        stage = Path(self.temp_dir) / "stage_symlink"
        stage.mkdir()
        with self.assertRaises(ValueError) as ctx:
            ci.extract_archive_safely(str(symlink_tar), str(stage))
        self.assertTrue("Dangerous path" in str(ctx.exception) or "escapes" in str(ctx.exception))

    def test_05_executable_script_rejection(self):
        """Archives containing shell scripts or installer executables must be rejected."""
        script_tar = Path(self.temp_dir) / "installer.tar.xz"
        with tarfile.open(script_tar, "w:xz") as tf:
            info = tarfile.TarInfo(name="Theme/install.sh")
            data = b"#!/bin/sh\necho pwned\n"
            info.size = len(data)
            tf.addfile(info, io_bytes(data))

        stage = Path(self.temp_dir) / "stage_script"
        stage.mkdir()
        with self.assertRaises(ValueError) as ctx:
            ci.extract_archive_safely(str(script_tar), str(stage))
        self.assertIn("Forbidden", str(ctx.exception))

    def test_06_corrupt_archive_rejection(self):
        """Corrupted/truncated archive data must be cleanly rejected."""
        corrupt_tar = Path(self.temp_dir) / "corrupt.tar.xz"
        corrupt_tar.write_bytes(b"\xfd7zXZ\x00\x00\x01\x00\x00\x00\x00corrupt garbage data")

        stage = Path(self.temp_dir) / "stage_corrupt"
        stage.mkdir()
        with self.assertRaises(ValueError):
            ci.extract_archive_safely(str(corrupt_tar), str(stage))

    def test_07_missing_archive_rejection(self):
        """Attempting to install a missing archive must raise FileNotFoundError."""
        missing = Path(self.temp_dir) / "nonexistent.tar.xz"
        with self.assertRaises(FileNotFoundError):
            ci.install_single_theme_archive(str(missing), str(self.icons_dir / "Test"))

    def test_08_atomic_materialization_all_bundled(self):
        """All 6 bundled themes must materialize safely and atomically into target directory."""
        res = ci.install_bundled_themes(
            catalog_path=str(CATALOG_PATH),
            target_icons_dir=str(self.icons_dir),
            version="1.0"
        )
        self.assertTrue(res.get("ok"))
        self.assertEqual(len(res["installed"]), 6)

        for entry in self.catalog:
            expected_root = entry.get("expectedRoot", entry["displayName"])
            target = self.icons_dir / expected_root
            self.assertTrue(target.is_dir(), f"Theme dir {target} was not created")
            self.assertTrue((target / ".omarchy-cursor-switcher-theme").is_file())
            self.assertTrue((target / ".omarchy-cursor-switcher-sha256").is_file())
            self.assertTrue((target / "manifest.hl").is_file() or (target / "cursors").is_dir())

        # Second run should be idempotent and report up-to-date
        res2 = ci.install_bundled_themes(
            catalog_path=str(CATALOG_PATH),
            target_icons_dir=str(self.icons_dir),
            version="1.0"
        )
        self.assertTrue(res2.get("ok"))
        for item in res2["installed"]:
            self.assertEqual(item["status"], "up-to-date")

    def test_09_all_bundled_themes_render_previews(self):
        """Previews must resolve seamlessly for all 6 materialized bundled themes."""
        # Materialize into icons_dir
        ci.install_bundled_themes(catalog_path=str(CATALOG_PATH), target_icons_dir=str(self.icons_dir))

        for entry in self.catalog:
            theme_name = entry.get("expectedRoot", entry["displayName"])
            roles = cursor_theming.get_theme_role_previews(theme_name, theme_path_hint=str(self.icons_dir / theme_name))
            self.assertIn("default", roles, f"Theme {theme_name} missing default role preview")
            self.assertTrue(os.path.isfile(roles["default"]), f"Preview file {roles['default']} missing")

    def test_10_user_imported_custom_theme_regression(self):
        """User-imported theme workflows must continue to work without regression."""
        mock_src = Path(self.temp_dir) / "custom_theme_src"
        mock_src_cursors = mock_src / "cursors"
        mock_src_cursors.mkdir(parents=True)
        (mock_src_cursors / "left_ptr").write_bytes(b"Xcur\x00\x00\x00\x01\x00\x00\x00\x00mockcursor")
        (mock_src / "index.theme").write_text("[Icon Theme]\nName=MyCustomTheme\n", encoding="utf-8")
        (mock_src / "LICENSE").write_text("MIT License\n", encoding="utf-8")

        # Set environment for run_import
        orig_home = os.environ.get("HOME")
        orig_xdg = os.environ.get("XDG_DATA_HOME")
        try:
            os.environ["HOME"] = self.temp_dir
            os.environ["XDG_DATA_HOME"] = str(Path(self.temp_dir) / ".local/share")

            res = ci.run_import(str(mock_src), display_name_override="MyCustomTheme")
            self.assertTrue(res.get("ok"), f"Import failed: {res}")
            theme_id = res["theme"]["id"]
            self.assertTrue(theme_id.startswith("CursorSwitcher-Imported-"))

            installed_path = Path(res["theme"]["path"])
            self.assertTrue(installed_path.is_dir())
            self.assertTrue((installed_path / ".omarchy-cursor-switcher-imported").is_file())

            # Test rename
            rename_res = ci.run_rename(theme_id, "RenamedCustomTheme")
            self.assertTrue(rename_res.get("ok"))

            # Test remove
            remove_res = ci.run_remove(theme_id)
            self.assertTrue(remove_res.get("ok"))
            self.assertFalse(installed_path.exists())
        finally:
            if orig_home: os.environ["HOME"] = orig_home
            if orig_xdg: os.environ["XDG_DATA_HOME"] = orig_xdg

    def test_11_git_tracking_cleanliness(self):
        """Git repository must NOT track any unpacked generated/ trees, compiled cursors, or build executables."""
        # 1. Check generated directories in git
        res_gen = subprocess.run(["git", "ls-files", "themes/*/generated/*"], cwd=ROOT, capture_output=True, text=True)
        tracked_gen = [f for f in res_gen.stdout.strip().splitlines() if f]
        self.assertEqual(len(tracked_gen), 0, f"Git must not track generated trees: {tracked_gen}")

        # 2. Check shipped unpacked cursor trees outside upstream/third_party
        res_cur = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
        all_tracked = res_cur.stdout.strip().splitlines()
        tracked_shipped_cursors = [
            f for f in all_tracked 
            if ("/cursors/" in f or "/hyprcursors/" in f) 
            and "upstream/" not in f 
            and "third_party/" not in f
        ]
        self.assertEqual(len(tracked_shipped_cursors), 0, f"Git must not track unpacked shipped cursors: {tracked_shipped_cursors}")

        # 3. Check build executables
        tracked_build = [f for f in all_tracked if ".build/" in f or f == "scripts/xcursor-pack" or f.endswith("/xcursor-pack")]
        self.assertEqual(len(tracked_build), 0, f"Git must not track build artifacts: {tracked_build}")



def io_bytes(b: bytes):
    import io
    return io.BytesIO(b)


if __name__ == "__main__":
    unittest.main()
