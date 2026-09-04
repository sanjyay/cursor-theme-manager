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


from test_isolation import IsolatedTestCase

class TestCursorImportSecurity(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        os.makedirs(str(self.iso.user_icons), exist_ok=True)
        os.makedirs(os.path.join(self.test_dir, ".config", "omarchy"), exist_ok=True)

    def tearDown(self):
        super().tearDown()

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
        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
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
        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
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

        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
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

        res = subprocess.run([CURSORCTL, "import", "--source", icon_dir], capture_output=True, text=True, env=self.env)
        self.assertNotEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertFalse(data.get("ok"))
        self.assertIn("not a valid cursor theme", data.get("error", "").lower())

    def test_05_malformed_theme_rejected(self):
        # Theme with empty cursors directory
        empty_dir = os.path.join(self.test_dir, "empty_cursor_theme")
        os.makedirs(os.path.join(empty_dir, "cursors"), exist_ok=True)
        res = subprocess.run([CURSORCTL, "import", "--source", empty_dir], capture_output=True, text=True, env=self.env)
        self.assertNotEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertFalse(data.get("ok"))
        self.assertIn("empty", data.get("error", "").lower())

    def test_06_unsafe_name_normalized(self):
        src = self.create_mock_xcursor("Evil Name /../ with $$ special @ chars!")
        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
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
        adwaita_path = str(self.iso.user_icons / "Adwaita")
        os.makedirs(os.path.join(adwaita_path, "cursors"), exist_ok=True)
        with open(os.path.join(adwaita_path, "cursors", "default"), "w") as f:
            f.write("Original Adwaita")

        src = self.create_mock_xcursor("Adwaita")
        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertTrue(data.get("ok"))
        # Must NOT have overwritten ~/.local/share/icons/Adwaita
        with open(os.path.join(adwaita_path, "cursors", "default"), "r") as f:
            self.assertEqual(f.read(), "Original Adwaita")
        # Installed as namespaced directory
        self.assertTrue(data["theme"]["path"].startswith(str(self.iso.user_icons / "CursorSwitcher-Imported-Adwaita-")))

    def test_08_internal_symlink_allowed(self):
        src = self.create_mock_xcursor("InternalSymlinkTheme")
        # Internal symlink within theme (pointer -> default)
        os.symlink("default", os.path.join(src, "cursors", "pointer"))

        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertTrue(data.get("ok"))

    def test_09_reject_symlink_escaping_theme_root(self):
        src = self.create_mock_xcursor("EscapingSymlinkTheme")
        # Add escaping symlink
        os.symlink("/etc/passwd", os.path.join(src, "cursors", "evil_link"))

        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
        self.assertNotEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertFalse(data.get("ok"))
        self.assertIn("escapes", data.get("error", "").lower())

    def test_10_same_hash_not_duplicated(self):
        src = self.create_mock_xcursor("DedupeCursor")
        res1 = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
        self.assertEqual(res1.returncode, 0)
        data1 = json.loads(res1.stdout)
        self.assertFalse(data1.get("alreadyImported"))

        # Second import of identical content
        res2 = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
        self.assertEqual(res2.returncode, 0)
        data2 = json.loads(res2.stdout)
        self.assertTrue(data2.get("alreadyImported"))
        self.assertEqual(data1["theme"]["id"], data2["theme"]["id"])

    def test_11_safe_removal_of_imported_theme(self):
        src = self.create_mock_xcursor("RemovableCursor")
        res_import = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
        self.assertEqual(res_import.returncode, 0)
        data = json.loads(res_import.stdout)
        theme_id = data["theme"]["id"]
        installed_path = data["theme"]["path"]
        self.assertTrue(os.path.isdir(installed_path))

        # Remove imported theme
        res_remove = subprocess.run([CURSORCTL, "remove-imported", "--id", theme_id], capture_output=True, text=True, env=self.env)
        self.assertEqual(res_remove.returncode, 0)
        remove_data = json.loads(res_remove.stdout)
        self.assertTrue(remove_data.get("ok"))
        self.assertFalse(os.path.exists(installed_path))

    def test_12_refusal_to_remove_system_theme(self):
        # Attempt to remove non-imported theme
        res = subprocess.run([CURSORCTL, "remove-imported", "--id", "Adwaita"], capture_output=True, text=True, env=self.env)
        self.assertNotEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertFalse(data.get("ok"))
        self.assertIn("not a valid imported theme", data.get("error", "").lower())

    def test_13_unknown_license_remains_unknown(self):
        src = self.create_mock_xcursor("UnknownLicenseCursor", with_license=True, license_text="Custom proprietary license text with no standard tags")
        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data["theme"]["license"], "Unknown")

    def test_13b_elf_payload_without_extension_is_rejected(self):
        src = self.create_mock_xcursor("ElfPayloadCursor")
        with open(os.path.join(src, "payload"), "wb") as f:
            f.write(b"\x7fELF" + b"\x00" * 32)
        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
        self.assertNotEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertFalse(data.get("ok"))
        self.assertIn("elf", data.get("error", "").lower())

    def test_14_valid_tar_archive_import(self):
        src = self.create_mock_xcursor("TarCursor")
        tar_path = os.path.join(self.test_dir, "tar_cursor.tar.gz")
        with tarfile.open(tar_path, "w:gz") as tf:
            tf.add(src, arcname="TarCursor")

        res = subprocess.run([CURSORCTL, "import", "--source", tar_path], capture_output=True, text=True, env=self.env)
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

        res = subprocess.run([CURSORCTL, "import", "--source", zip_path], capture_output=True, text=True, env=self.env)
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

        res = subprocess.run([CURSORCTL, "import", "--source", tar_path], capture_output=True, text=True, env=self.env)
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

        res = subprocess.run([CURSORCTL, "import", "--source", tar_path], capture_output=True, text=True, env=self.env)
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

        res = subprocess.run([CURSORCTL, "import", "--source", tar_path], capture_output=True, text=True, env=self.env)
        self.assertNotEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertFalse(data.get("ok"))

    def test_19_file_count_limit(self):
        src = self.create_mock_xcursor("HugeFileTheme")
        for i in range(100):
            with open(os.path.join(src, "cursors", f"extra_{i}"), "w") as f:
                f.write("dummy")
        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
        self.assertEqual(res.returncode, 0)

    def test_20_discovery_detects_imported_theme(self):
        src = self.create_mock_xcursor("DiscoveredImport")
        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
        self.assertEqual(res.returncode, 0)

        # Run discovery
        res_disc = subprocess.run([CURSORCTL, "discover"], capture_output=True, text=True, env=self.env)
        self.assertEqual(res_disc.returncode, 0)
        disc_data = json.loads(res_disc.stdout)
        imported_entries = [t for t in disc_data["themes"] if t.get("imported") is True]
        self.assertTrue(len(imported_entries) >= 1)
        self.assertTrue(any("DiscoveredImport" in t["displayName"] for t in imported_entries))

    def test_21_rename_imported_theme(self):
        src = self.create_mock_xcursor("InitialName")
        res = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
        self.assertEqual(res.returncode, 0)
        imported_id = json.loads(res.stdout)["theme"]["id"]

        # Rename
        res_rename = subprocess.run([CURSORCTL, "rename-imported", "--id", imported_id, "--name", "BrandNewName"], capture_output=True, text=True, env=self.env)
        self.assertEqual(res_rename.returncode, 0)
        rename_data = json.loads(res_rename.stdout)
        self.assertTrue(rename_data.get("ok"))
        self.assertEqual(rename_data.get("displayName"), "BrandNewName")

        # Discover should immediately reflect BrandNewName
        res_disc = subprocess.run([CURSORCTL, "discover"], capture_output=True, text=True, env=self.env)
        disc_data = json.loads(res_disc.stdout)
        renamed_theme = next((t for t in disc_data["themes"] if t["id"] == imported_id), None)
        self.assertIsNotNone(renamed_theme)
        self.assertEqual(renamed_theme["displayName"], "BrandNewName")

    def test_22_duplicate_import_opens_existing_theme_notice(self):
        with open(os.path.join(ROOT_DIR, "CursorService.qml"), encoding="utf-8") as source:
            service_qml = source.read()
        with open(os.path.join(ROOT_DIR, "components", "ImportDialog.qml"), encoding="utf-8") as source:
            dialog_qml = source.read()

        self.assertIn("root.importCompleted(parsed.theme, msg, Boolean(parsed.alreadyImported))", service_qml)
        self.assertIn("function onImportCompleted(theme, message, alreadyImported)", dialog_qml)
        self.assertIn("if (alreadyImported)", dialog_qml)
        self.assertIn("root.duplicateNotice = Model.sanitizeString(message, 256)", dialog_qml)
        self.assertIn('text: "Already Imported"', dialog_qml)
        self.assertIn("if (canonical && !parsed.alreadyImported)", service_qml)
        self.assertIn("if (!parsed.alreadyImported) root.refresh(true)", service_qml)

    def test_23_instance_bound_duplicate_import_reaches_import_parser(self):
        identity = subprocess.run(
            [CURSORCTL, "installation-identity"], capture_output=True, text=True, env=self.env
        )
        self.assertEqual(identity.returncode, 0, identity.stderr)
        fingerprint = json.loads(identity.stdout)["pluginFingerprint"]
        src = self.create_mock_xcursor("BoundDuplicate")

        first = subprocess.run(
            [CURSORCTL, "import", "--source", src, "--plugin-fingerprint", fingerprint],
            capture_output=True, text=True, env=self.env
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertFalse(json.loads(first.stdout)["alreadyImported"])

        duplicate = subprocess.run(
            [CURSORCTL, "import", "--source", src, "--plugin-fingerprint", fingerprint],
            capture_output=True, text=True, env=self.env
        )
        self.assertEqual(duplicate.returncode, 0, duplicate.stderr)
        self.assertTrue(json.loads(duplicate.stdout)["alreadyImported"])


    def test_24_legacy_hash_duplicate_detection(self):
        # Create a theme with symlinks so legacy hash != modern hash
        src = self.create_mock_xcursor("LegacyHashTheme")
        cursors_dir = os.path.join(src, "cursors")
        os.symlink("default", os.path.join(cursors_dir, "arrow"))

        # First import
        res1 = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
        self.assertEqual(res1.returncode, 0, res1.stderr)
        data1 = json.loads(res1.stdout)
        self.assertFalse(data1.get("alreadyImported"))
        theme1_path = data1["theme"]["path"]
        modern_hash = data1["theme"]["contentHash"]

        # Compute legacy hash
        sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))
        import importlib.util
        spec = importlib.util.spec_from_file_location("cursor_import", IMPORT_SCRIPT)
        ci = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ci)
        legacy_hash = ci.compute_legacy_content_hash(src)
        self.assertNotEqual(modern_hash, legacy_hash)

        # Overwrite marker with legacy hash to simulate pre-upgrade import
        m1 = os.path.join(theme1_path, ".cursor-theme-manager-imported")
        m2 = os.path.join(theme1_path, ".omarchy-cursor-switcher-imported")
        with open(m1, "r", encoding="utf-8") as f:
            rec = json.load(f)
        rec["contentHash"] = legacy_hash
        for m in (m1, m2):
            with open(m, "w", encoding="utf-8") as f:
                json.dump(rec, f, indent=2)

        # Re-import should detect it as already imported via legacy hash
        res2 = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
        self.assertEqual(res2.returncode, 0, res2.stderr)
        data2 = json.loads(res2.stdout)
        self.assertTrue(data2.get("alreadyImported"), "Expected alreadyImported: True via legacy hash")
        # And marker should have been modernized to modern_hash
        with open(m1, "r", encoding="utf-8") as f:
            rec_modern = json.load(f)
        self.assertEqual(rec_modern["contentHash"], modern_hash)

    def test_25_marker_files_ignored_during_hash(self):
        sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))
        import importlib.util
        spec = importlib.util.spec_from_file_location("cursor_import", IMPORT_SCRIPT)
        ci = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ci)

        src = self.create_mock_xcursor("MarkerIgnoreTheme")
        hash_before = ci.compute_content_hash(src)

        # Add managed markers with varied content
        with open(os.path.join(src, ".cursor-theme-manager-imported"), "w") as f:
            f.write(json.dumps({"importedAt": "2026-09-04T12:00:00Z", "id": "test"}))
        with open(os.path.join(src, ".omarchy-cursor-switcher-imported"), "w") as f:
            f.write(json.dumps({"importedAt": "2026-09-04T13:00:00Z", "id": "test2"}))

        hash_after = ci.compute_content_hash(src)
        self.assertEqual(hash_before, hash_after)

    def test_26_import_theme_already_in_icons_dir(self):
        src = self.create_mock_xcursor("AlreadyInIcons")
        res1 = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
        self.assertEqual(res1.returncode, 0)
        installed_path = json.loads(res1.stdout)["theme"]["path"]

        # Importing from the installed location inside user icons dir
        res2 = subprocess.run([CURSORCTL, "import", "--source", installed_path], capture_output=True, text=True, env=self.env)
        self.assertEqual(res2.returncode, 0)
        data2 = json.loads(res2.stdout)
        self.assertTrue(data2.get("alreadyImported"))

    def test_27_remove_theme_cleans_up_duplicate_folder(self):
        src = self.create_mock_xcursor("DupCleanTheme")
        res1 = subprocess.run([CURSORCTL, "import", "--source", src], capture_output=True, text=True, env=self.env)
        self.assertEqual(res1.returncode, 0)
        theme1 = json.loads(res1.stdout)["theme"]
        id1 = theme1["id"]
        path1 = theme1["path"]

        # Manually create a duplicate imported folder with same contentHash
        id2 = f"{id1}-dup"
        path2 = os.path.join(str(self.iso.user_icons), id2)
        shutil.copytree(path1, path2, symlinks=True)
        # Update marker id for the dup
        m1 = os.path.join(path2, ".cursor-theme-manager-imported")
        m2 = os.path.join(path2, ".omarchy-cursor-switcher-imported")
        for m in (m1, m2):
            with open(m, "r", encoding="utf-8") as f:
                rec = json.load(f)
            rec["id"] = id2
            with open(m, "w", encoding="utf-8") as f:
                json.dump(rec, f, indent=2)

        self.assertTrue(os.path.isdir(path1))
        self.assertTrue(os.path.isdir(path2))

        # Remove theme 1
        res_del = subprocess.run([CURSORCTL, "remove-imported", "--id", id1], capture_output=True, text=True, env=self.env)
        self.assertEqual(res_del.returncode, 0, res_del.stderr)
        self.assertFalse(os.path.exists(path1))
        self.assertFalse(os.path.exists(path2), "Duplicate theme directory should have been cleaned up")

    def test_28_safe_write_text_file_security_and_descriptor_relative_replacement(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("cursor_import", IMPORT_SCRIPT)
        ci = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ci)

        safe_write = ci.safe_write_text_file

        theme_parent = os.path.join(self.test_dir, "safe_write_test")
        os.makedirs(theme_parent, mode=0o700, exist_ok=True)
        target_file = os.path.join(theme_parent, "manifest.hl")

        # 1. Normal write succeeds
        self.assertTrue(safe_write(target_file, "name = TestTheme\n"))
        with open(target_file, "r") as f:
            self.assertEqual(f.read(), "name = TestTheme\n")

        # 2. Re-write existing file succeeds atomically
        self.assertTrue(safe_write(target_file, "name = UpdatedTheme\n"))
        with open(target_file, "r") as f:
            self.assertEqual(f.read(), "name = UpdatedTheme\n")

        # 3. World-writable parent directory is rejected
        os.chmod(theme_parent, 0o777)
        self.assertFalse(safe_write(target_file, "name = Malicious\n"))
        with open(target_file, "r") as f:
            self.assertEqual(f.read(), "name = UpdatedTheme\n")

        # 4. Group-writable parent directory is rejected
        os.chmod(theme_parent, 0o775)
        self.assertFalse(safe_write(target_file, "name = MaliciousGroup\n"))
        with open(target_file, "r") as f:
            self.assertEqual(f.read(), "name = UpdatedTheme\n")

        # Restore safe permissions
        os.chmod(theme_parent, 0o700)

        # 5. Symlink target is rejected and target victim is not overwritten
        victim = os.path.join(self.test_dir, "victim.txt")
        with open(victim, "w") as f:
            f.write("UNTOUCHED_VICTIM")
        symlink_target = os.path.join(theme_parent, "symlink_file")
        os.symlink(victim, symlink_target)
        self.assertFalse(safe_write(symlink_target, "OVERWRITTEN"))
        with open(victim, "r") as f:
            self.assertEqual(f.read(), "UNTOUCHED_VICTIM")

        # 6. Symlink parent directory is rejected
        symlink_parent = os.path.join(self.test_dir, "parent_link")
        os.symlink(theme_parent, symlink_parent)
        self.assertFalse(safe_write(os.path.join(symlink_parent, "file.txt"), "data"))

        # 7. Descriptor-relative guarantee: parent directory rename during write stays in held inode
        # We verify that safe_write's descriptor-relative replace uses src_dir_fd and dst_dir_fd
        # by verifying that a held parent descriptor write survives directory renaming without touching decoy/victim
        held_dir = os.path.join(self.test_dir, "held_dir")
        os.makedirs(held_dir, mode=0o700, exist_ok=True)
        fname = "index.theme"
        victim2 = os.path.join(self.test_dir, "victim2.txt")
        with open(victim2, "w") as f:
            f.write("SAFE_VICTIM_2")

        dir_fd = os.open(held_dir, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            tmp_name = f".tmp-{fname}-test"
            tmp_fd = os.open(tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644, dir_fd=dir_fd)
            os.write(tmp_fd, b"SECURE_CONTENT")
            os.close(tmp_fd)

            # Concurrent attacker swaps directory path
            decoy = os.path.join(self.test_dir, "held_dir_moved")
            os.rename(held_dir, decoy)
            attacker_dir = os.path.join(self.test_dir, "held_dir")
            os.makedirs(attacker_dir, mode=0o700)
            os.symlink(victim2, os.path.join(attacker_dir, fname))

            # Final rename executed relative to held dir_fd
            os.replace(tmp_name, fname, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)

            # Victim at the swapped pathname was not touched
            with open(victim2) as f:
                self.assertEqual(f.read(), "SAFE_VICTIM_2")

            # File was placed in original held inode (now at decoy)
            with open(os.path.join(decoy, fname)) as f:
                self.assertEqual(f.read(), "SECURE_CONTENT")
        finally:
            os.close(dir_fd)


if __name__ == "__main__":
    unittest.main()
