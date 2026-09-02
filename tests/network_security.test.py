#!/usr/bin/env python3
"""
Network Security Assertion Test for Omarchy Cursor Switcher.
Verifies that runtime code performs zero network access, imports no network libraries,
and executes no download commands (curl/wget/git clone).
"""

import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RUNTIME_PATHS = (
    [p for p in (ROOT / "scripts").glob("*") if p.is_file() and not p.name.startswith(".") and not p.name.endswith(".pyc")] +
    [ROOT / "CursorService.qml", ROOT / "CursorModel.js", ROOT / "Panel.qml"] +
    list((ROOT / "components").glob("*.qml"))
)


class TestNetworkSecurity(unittest.TestCase):

    def test_01_no_python_network_imports(self):
        """Runtime Python scripts must not import network or HTTP libraries."""
        forbidden_imports = [
            r'^\s*import\s+(urllib|requests|http|socket|ftplib|aiohttp|httpx|urllib3)',
            r'^\s*from\s+(urllib|requests|http|socket|ftplib|aiohttp|httpx|urllib3)\b',
        ]
        for path in RUNTIME_PATHS:
            if path.suffix == ".py":
                text = path.read_text(encoding="utf-8")
                for i, line in enumerate(text.splitlines(), 1):
                    for pattern in forbidden_imports:
                        match = re.search(pattern, line)
                        self.assertIsNone(
                            match,
                            f"Forbidden network import in {path.name}:{i}: '{line.strip()}'"
                        )

    def test_02_no_shell_network_commands(self):
        """Runtime scripts must not invoke curl, wget, git clone, or download utilities."""
        forbidden_commands = [
            r'\bcurl\b',
            r'\bwget\b',
            r'\bgit\s+clone\b',
            r'\bnetcat\b',
            r'\baria2c\b',
        ]
        for path in RUNTIME_PATHS:
            text = path.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("/*"):
                    continue
                for pattern in forbidden_commands:
                    match = re.search(pattern, line)
                    self.assertIsNone(
                        match,
                        f"Forbidden network command in {path.name}:{i}: '{line.strip()}'"
                    )

    def test_03_no_qml_network_primitives(self):
        """QML components must not use QNetworkAccessManager, XMLHttpRequest, or fetch."""
        forbidden_qml = [
            r'XMLHttpRequest',
            r'QNetworkAccessManager',
            r'\bfetch\s*\(',
            r'WebSocket',
        ]
        for path in RUNTIME_PATHS:
            if path.suffix == ".qml" or path.suffix == ".js":
                text = path.read_text(encoding="utf-8")
                for i, line in enumerate(text.splitlines(), 1):
                    stripped = line.strip()
                    if stripped.startswith("//") or stripped.startswith("/*"):
                        continue
                    for pattern in forbidden_qml:
                        match = re.search(pattern, line)
                        self.assertIsNone(
                            match,
                            f"Forbidden QML network primitive in {path.name}:{i}: '{line.strip()}'"
                        )

    def test_04_no_runtime_network_urls(self):
        """Runtime code must not contact remote endpoints (ignoring standard XML namespaces)."""
        for path in RUNTIME_PATHS:
            text = path.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("/*"):
                    continue
                if 'xmlns="http://www.w3.org/2000/svg"' in line or "xmlns:xlink" in line:
                    continue
                urls = re.findall(r'https?://[^\s\'"<>]+', line)
                self.assertEqual(
                    len(urls), 0,
                    f"Forbidden remote URL in {path.name}:{i}: {urls}"
                )


if __name__ == "__main__":
    unittest.main()
