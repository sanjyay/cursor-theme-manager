#!/usr/bin/env python3
import os
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THEMES_DIR = ROOT / "themes"
CATALOG_PATH = THEMES_DIR / "catalog.json"
THIRD_PARTY_DIR = ROOT / "third_party"
THIRD_PARTY_MD = ROOT / "THIRD_PARTY.md"

class TestThirdPartyRegistry(unittest.TestCase):
    def setUp(self):
        self.assertTrue(CATALOG_PATH.exists(), "catalog.json must exist")
        self.catalog = json.loads(CATALOG_PATH.read_text())
        
    def test_catalog_structure(self):
        expected_ids = ["banana", "phinger", "oreo", "volantes", "nordzy", "capitaine"]
        actual_ids = [t["id"] for t in self.catalog]
        self.assertEqual(actual_ids, expected_ids)
        
        # Unique IDs
        self.assertEqual(len(actual_ids), len(set(actual_ids)))
        
    def test_licenses_and_upstream_metadata(self):
        expected_licenses = {
            "banana": "GPL-3.0",
            "phinger": "CC-BY-SA-4.0",
            "oreo": "GPL-2.0-only",
            "volantes": "GPL-2.0-only",
            "nordzy": "GPL-3.0-only",
            "capitaine": "LGPL-3.0-or-later"
        }
        
        for item in self.catalog:
            tid = item["id"]
            self.assertIn(tid, expected_licenses)
            self.assertEqual(item["license"], expected_licenses[tid])
            
            theme_root = THEMES_DIR / tid
            self.assertTrue(theme_root.exists(), f"Theme dir {theme_root} must exist")
            
            # 1. UPSTREAM.json
            upstream_path = theme_root / "UPSTREAM.json"
            self.assertTrue(upstream_path.exists(), f"UPSTREAM.json must exist in {theme_root}")
            upstream_info = json.loads(upstream_path.read_text())
            self.assertTrue(len(upstream_info.get("commit", "")) >= 10, f"Commit SHA required for {tid}")
            self.assertTrue(upstream_info.get("upstream", "").startswith("https://"), f"Upstream URL required for {tid}")
            self.assertIn("author", upstream_info)
            
            # 2. LICENSE or COPYING
            license_files = [f for f in ["LICENSE", "COPYING"] if (theme_root / f).exists()]
            self.assertTrue(len(license_files) > 0, f"License file required in {theme_root}")
            
            # 3. ATTRIBUTION.md
            attrib_path = theme_root / "ATTRIBUTION.md"
            self.assertTrue(attrib_path.exists(), f"ATTRIBUTION.md must exist in {theme_root}")
            
            # 4. Preview SVG
            preview_path = theme_root / "preview.svg"
            self.assertTrue(preview_path.exists(), f"preview.svg must exist in {theme_root}")
            self.assertGreater(preview_path.stat().st_size, 50, f"preview.svg in {theme_root} is too small")
            
            # 5. Generated Package
            gen_dir = theme_root / "generated"
            self.assertTrue(gen_dir.exists(), f"generated/ must exist in {theme_root}")
            subdirs = [d for d in gen_dir.iterdir() if d.is_dir()]
            self.assertGreater(len(subdirs), 0, f"generated/ package required in {theme_root}")
            pkg = subdirs[0]
            self.assertTrue((pkg / "manifest.hl").exists(), f"manifest.hl required in {pkg}")
            self.assertTrue((pkg / "hyprcursors").exists(), f"hyprcursors required in {pkg}")
            self.assertTrue((pkg / "cursors").exists(), f"cursors required in {pkg}")
            self.assertTrue((pkg / "index.theme").exists(), f"index.theme required in {pkg}")
            
            # 6. Source preservation in upstream/
            upstream_dir = theme_root / "upstream"
            self.assertTrue(upstream_dir.exists(), f"upstream source dir required in {theme_root}")
            
    def test_third_party_md_document(self):
        self.assertTrue(THIRD_PARTY_MD.exists(), "THIRD_PARTY.md must exist at repository root")
        content = THIRD_PARTY_MD.read_text()
        for name in ["Banana", "Phinger", "Oreo", "Volantes", "Nordzy", "Capitaine"]:
            self.assertIn(name, content, f"{name} must be documented in THIRD_PARTY.md")
        self.assertIn("CC BY-SA 4.0", content)
        self.assertIn("GPL-2.0", content)
        self.assertIn("GPL-3.0", content)
        self.assertIn("LGPL-3.0", content)

if __name__ == "__main__":
    unittest.main()
