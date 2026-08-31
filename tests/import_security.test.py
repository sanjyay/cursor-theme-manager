#!/usr/bin/env python3
"""
Comprehensive test suite for cursor theme import security and functionality.
Covers all test requirements from the specification.
"""

import sys
import os
import shutil
import tempfile
import tarfile
import zipfile
import subprocess
import json
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
IMPORT_SCRIPT = os.path.join(ROOT_DIR, "scripts", "cursor-import.py")
CURSORCTL = os.path.join(ROOT_DIR, "scripts", "cursorctl")


class TestCursorImportSecurity(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="cs-test-import-")
        self.orig_env = os.environ.copy()
        os.environ["HOME"] = self.test_dir
        os.environ["XDG_DATA_HOME"] = os.path.join(self.test_dir, ".local", "share")
        os.environ["XDG_CONFIG_HOME"] = os.path.join(self.test_dir, ".config")
        os.environ["XDG_CACHE_HOME"] = os.path.join(self.test_dir, ".cache")

        os.makedirs(os.path.join(self.test_dir, ".local", "share", "icons"), exist_ok=True)
        os.makedirs(os.path.join(self.test_dir, ".config", "omarchy"), exist_ok=True)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def create_mock_xcursor(self, name="TestXCursor", with_license=True, license_text=None):
        theme_dir = os.path.join(self.test_dir, "mock_src", name)
        cursors_dir = os.path.join(theme_dir, "cursors")
        os.makedirs(cursors_dir, exist_ok=True)

        with open(os.path.join(cursors_dir, "default"), "wb") as f:
            f.write(b"Xcur\x00\x00\x00\x01\x00\x00\x00\x00" + b"\x00" * 64)
        with open(os.path.join(cursors_dir, "left_ptr"), "wb") as f:
            f.write(b"Xcur\x00\x00\x00\x01\x00\x00\x00\x00" + b"\x00" * 64)

        with open(os.path.join(theme_dir, "index.theme"), "w") as f:
            f.write(f"[Icon Theme]\nName={name}\nComment=Mock XCursor Theme\n")

        if with_license:
            text = license_text or "GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007\n"
            with open(os.path.join(theme_dir, "LICENSE"), "w") as f:
                f.write(text)

        return theme_dir

    def create_mock_hyprcursor(self, name="TestHyprcursor", with_license=True):
        theme_dir = os.path.join(self.test_dir, "mock_src", name)
        os.makedirs(theme_dir, exist_ok=True)

        with open(os.path.join(theme_dir, "manifest.hl"), "w") as f:
            f.write(f'name = "{name}"\ndescription = "Mock Hyprcursor Theme"\nversion = 1.0\ncursors_directory = "hyprcursors"\n')

        cur_dir = os.path.join(theme_dir, "hyprcursors", "default")
        os.makedirs(cur_dir, exist_ok=True)
        with open(os.path.join(cur_dir, "default.hl"), "w") as f:
            f.write("resize_algorithm = nearest\nhotspot_x = 0.1\nhotspot_y = 0.1\n")
        with open(os.path.join(cur_dir, "default_24.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

        if with_license:
            with open(os.path.join(theme_dir, "LICENSE.txt"), "w") as f:
                f.write("The MIT License (MIT)\nPermission is hereby granted, free of charge...")

        return theme_dir

    def test_01_valid_xcursor_directory_import(self):
        src = self.create_mock_xcursor("ValidXCursor")
        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Import failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertTrue(data.get("ok"))
        theme = data["theme"]
        self.assertIn("xcursor", theme["formats"])
        self.assertEqual(theme["license"], "GPL-3.0")
        self.assertTrue(theme["id"].startswith("CursorSwitcher-Imported-ValidXCursor-"))
        self.assertTrue(os.path.isdir(theme["path"]))
        self.assertTrue(os.path.isfile(os.path.join(theme["path"], ".omarchy-cursor-switcher-imported")))
        # License file is preserved
        self.assertTrue(os.path.isfile(os.path.join(theme["path"], "LICENSE")))

    def test_02_valid_hyprcursor_directory_import(self):
        src = self.create_mock_hyprcursor("ValidHypr")
        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Import failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertTrue(data.get("ok"))
        theme = data["theme"]
        self.assertIn("hyprcursor", theme["formats"])
        self.assertEqual(theme["license"], "MIT")
        self.assertTrue(os.path.isdir(theme["path"]))
        # License file is preserved
        self.assertTrue(os.path.isfile(os.path.join(theme["path"], "LICENSE.txt")))

    def test_03_mixed_theme_import(self):
        src = self.create_mock_hyprcursor("MixedTheme")
        # Add XCursor cursors directory
        cursors_dir = os.path.join(src, "cursors")
        os.makedirs(cursors_dir, exist_ok=True)
        with open(os.path.join(cursors_dir, "default"), "wb") as f:
            f.write(b"Xcur\x00\x00\x00\x01\x00\x00\x00\x00" + b"\x00" * 64)
        with open(os.path.join(src, "index.theme"), "w") as f:
            f.write("[Icon Theme]\nName=MixedTheme\n")

        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Import failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertTrue(data.get("ok"))
        self.assertIn("hyprcursor", data["theme"]["formats"])
        self.assertIn("xcursor", data["theme"]["formats"])

    def test_04_reject_plain_icon_theme(self):
        icon_dir = os.path.join(self.test_dir, "mock_icons")
        os.makedirs(os.path.join(icon_dir, "apps", "scalable"), exist_ok=True)
        with open(os.path.join(icon_dir, "apps", "scalable", "app.svg"), "w") as f:
            f.write("<svg></svg>")
        with open(os.path.join(icon_dir, "index.theme"), "w") as f:
            f.write("[Icon Theme]\nName=JustIcons\nDirectories=apps/scalable\n")

        res = subprocess.run([CURSORCTL, "import", "--source", icon_dir], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertFalse(data.get("ok"))
        self.assertIn("not a valid cursor theme", data.get("error", "").lower())

    def test_05_malformed_theme_rejected(self):
        # Theme with empty cursors directory
        empty_dir = os.path.join(self.test_dir, "empty_cursor_theme")
        os.makedirs(os.path.join(empty_dir, "cursors"), exist_ok=True)
        res = subprocess.run([CURSORCTL, "import", "--source", empty_dir], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertFalse(data.get("ok"))
        self.assertIn("empty", data.get("error", "").lower())

    def test_06_unsafe_name_normalized(self):
        src = self.create_mock_xcursor("Evil Name /../ with $$ special @ chars!")
        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertTrue(data.get("ok"))
        internal_id = data["theme"]["id"]
        # Must be safe string without slashes or metacharacters
        self.assertNotIn("/", internal_id)
        self.assertNotIn("..", internal_id)
        self.assertNotIn("$", internal_id)
        self.assertTrue(internal_id.startswith("CursorSwitcher-Imported-"))

    def test_07_collision_does_not_overwrite_existing_theme(self):
        # Create an existing system/user theme in ~/.local/share/icons/Adwaita
        adwaita_path = os.path.join(self.test_dir, ".local", "share", "icons", "Adwaita")
        os.makedirs(os.path.join(adwaita_path, "cursors"), exist_ok=True)
        with open(os.path.join(adwaita_path, "cursors", "default"), "w") as f:
            f.write("Original Adwaita")

        src = self.create_mock_xcursor("Adwaita")
        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertTrue(data.get("ok"))
        # Must NOT have overwritten ~/.local/share/icons/Adwaita
        with open(os.path.join(adwaita_path, "cursors", "default"), "r") as f:
            self.assertEqual(f.read(), "Original Adwaita")
        # Installed as namespaced directory
        self.assertTrue(data["theme"]["path"].startswith(os.path.join(self.test_dir, ".local", "share", "icons", "CursorSwitcher-Imported-Adwaita-")))

    def test_08_internal_symlink_allowed(self):
        src = self.create_mock_xcursor("InternalSymlinkTheme")
        # Internal symlink within theme (pointer -> default)
        os.symlink("default", os.path.join(src, "cursors", "pointer"))

        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertTrue(data.get("ok"))

    def test_09_reject_symlink_escaping_theme_root(self):
        src = self.create_mock_xcursor("EscapingSymlinkTheme")
        # Add escaping symlink
        os.symlink("/etc/passwd", os.path.join(src, "cursors", "evil_link"))

        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertFalse(data.get("ok"))
        self.assertIn("escapes", data.get("error", "").lower())

    def test_10_same_hash_not_duplicated(self):
        src = self.create_mock_xcursor("DedupeCursor")
        res1 = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True)
        self.assertEqual(res1.returncode, 0)
        data1 = json.loads(res1.stdout)
        self.assertFalse(data1.get("alreadyImported"))

        # Second import of identical content
        res2 = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True)
        self.assertEqual(res2.returncode, 0)
        data2 = json.loads(res2.stdout)
        self.assertTrue(data2.get("alreadyImported"))
        self.assertEqual(data1["theme"]["id"], data2["theme"]["id"])

    def test_11_safe_removal_of_imported_theme(self):
        src = self.create_mock_xcursor("RemovableCursor")
        res_import = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True)
        self.assertEqual(res_import.returncode, 0)
        data = json.loads(res_import.stdout)
        theme_id = data["theme"]["id"]
        installed_path = data["theme"]["path"]
        self.assertTrue(os.path.isdir(installed_path))

        # Remove imported theme
        res_remove = subprocess.run([CURSORCTL, "remove-imported", "--id", theme_id], capture_output=True, text=True)
        self.assertEqual(res_remove.returncode, 0)
        remove_data = json.loads(res_remove.stdout)
        self.assertTrue(remove_data.get("ok"))
        self.assertFalse(os.path.exists(installed_path))

    def test_12_refusal_to_remove_system_theme(self):
        # Attempt to remove non-imported theme
        res = subprocess.run([CURSORCTL, "remove-imported", "--id", "Adwaita"], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertFalse(data.get("ok"))
        self.assertIn("not a valid imported theme", data.get("error", "").lower())

    def test_13_unknown_license_remains_unknown(self):
        src = self.create_mock_xcursor("UnknownLicenseCursor", with_license=True, license_text="Custom proprietary license text with no standard tags")
        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data["theme"]["license"], "Unknown")

    def test_14_valid_tar_archive_import(self):
        src = self.create_mock_xcursor("TarCursor")
        tar_path = os.path.join(self.test_dir, "tar_cursor.tar.gz")
        with tarfile.open(tar_path, "w:gz") as tf:
            tf.add(src, arcname="TarCursor")

        res = subprocess.run([CURSORCTL, "import", "--source", tar_path], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Tar import failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertTrue(data.get("ok"))
        self.assertEqual(data["theme"]["license"], "GPL-3.0")

    def test_15_valid_zip_archive_import(self):
        src = self.create_mock_hyprcursor("ZipHypr")
        zip_path = os.path.join(self.test_dir, "zip_cursor.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            for root, _, files in os.walk(src):
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, src)
                    zf.write(full, arcname=os.path.join("ZipHypr", rel))

        res = subprocess.run([CURSORCTL, "import", "--source", zip_path], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Zip import failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertTrue(data.get("ok"))

    def test_16_reject_archive_with_path_traversal(self):
        import io
        tar_path = os.path.join(self.test_dir, "malicious_traversal.tar.gz")
        payload = b"hello"
        with tarfile.open(tar_path, "w:gz") as tf:
            ti = tarfile.TarInfo(name="../../etc/evil.txt")
            ti.size = len(payload)
            tf.addfile(ti, fileobj=io.BytesIO(payload))

        res = subprocess.run([CURSORCTL, "import", "--source", tar_path], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertFalse(data.get("ok"))
        self.assertIn("dangerous path", data.get("error", "").lower())

    def test_17_reject_archive_with_absolute_path(self):
        import io
        tar_path = os.path.join(self.test_dir, "absolute_path.tar.gz")
        payload = b"hello"
        with tarfile.open(tar_path, "w:gz") as tf:
            ti = tarfile.TarInfo(name="/tmp/evil_abs.txt")
            ti.size = len(payload)
            tf.addfile(ti, fileobj=io.BytesIO(payload))

        res = subprocess.run([CURSORCTL, "import", "--source", tar_path], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertFalse(data.get("ok"))

    def test_18_reject_archive_with_symlink_escape(self):
        tar_path = os.path.join(self.test_dir, "symlink_escape.tar.gz")
        with tarfile.open(tar_path, "w:gz") as tf:
            ti = tarfile.TarInfo(name="mytheme/cursors/escape")
            ti.type = tarfile.SYMTYPE
            ti.linkname = "../../etc/shadow"
            tf.addfile(ti)

        res = subprocess.run([CURSORCTL, "import", "--source", tar_path], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertFalse(data.get("ok"))

    def test_19_file_count_limit(self):
        src = self.create_mock_xcursor("HugeFileTheme")
        for i in range(100):
            with open(os.path.join(src, "cursors", f"extra_{i}"), "w") as f:
                f.write("dummy")
        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)

    def test_20_discovery_detects_imported_theme(self):
        src = self.create_mock_xcursor("DiscoveredImport")
        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)

        # Run discovery
        res_disc = subprocess.run([CURSORCTL, "discover"], capture_output=True, text=True)
        self.assertEqual(res_disc.returncode, 0)
        disc_data = json.loads(res_disc.stdout)
        imported_entries = [t for t in disc_data["themes"] if t.get("imported") is True]
        self.assertTrue(len(imported_entries) >= 1)
        self.assertTrue(any("DiscoveredImport" in t["displayName"] for t in imported_entries))


if __name__ == "__main__":
    unittest.main()
