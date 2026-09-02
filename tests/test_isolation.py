#!/usr/bin/env python3
"""
Shared test isolation helper and security guards for Cursor Theme Manager tests.
Guarantees:
1. Every test runs with an isolated temporary HOME, XDG_DATA_HOME, XDG_STATE_HOME, XDG_CONFIG_HOME, XDG_CACHE_HOME.
2. Destructive path operations outside the test root are strictly forbidden and guarded.
3. System mock binaries (systemctl, gsettings, hyprctl, dbus-update-activation-environment) are provided.
4. Automatic clean tearDown removes the temporary test directory.
"""

import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Any, Optional

REAL_USER_HOME = Path(os.path.expanduser("~")).resolve()


class IsolatedEnvironment:
    def __init__(self, prefix="ctm-test-"):
        self.test_dir = tempfile.mkdtemp(prefix=prefix)
        self.root = Path(self.test_dir).resolve()
        self.home = self.root / "home"
        self.xdg_data = self.home / ".local" / "share"
        self.xdg_state = self.home / ".local" / "state"
        self.xdg_config = self.root / "config"
        self.xdg_cache = self.root / "cache"
        self.sys_data = self.root / "usr" / "share"
        self.mock_bin = self.root / "mock_bin"

        self.user_icons = self.xdg_data / "icons"
        self.user_apps = self.xdg_data / "applications"
        self.state_dir = self.xdg_state / "cursor-theme-manager"
        self.libexec_dir = self.home / ".local" / "libexec" / "cursor-theme-manager"
        self.systemd_user = self.xdg_config / "systemd" / "user"
        self.omarchy_plugins = self.xdg_config / "omarchy" / "plugins"

        # Create all required directory trees
        for d in [
            self.home, self.xdg_data, self.xdg_state, self.xdg_config, self.xdg_cache,
            self.user_icons, self.user_apps, self.state_dir, self.libexec_dir,
            self.systemd_user, self.omarchy_plugins, self.mock_bin,
            self.sys_data / "icons"
        ]:
            d.mkdir(parents=True, exist_ok=True)

        self._create_mock_binaries()

        self.orig_env = os.environ.copy()
        self.env: Dict[str, str] = {
            **self.orig_env,
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.xdg_data),
            "XDG_STATE_HOME": str(self.xdg_state),
            "XDG_CONFIG_HOME": str(self.xdg_config),
            "XDG_CACHE_HOME": str(self.xdg_cache),
            "XDG_DATA_DIRS": f"{self.sys_data}:/usr/local/share:/usr/share",
            "PATH": f"{self.mock_bin}:{self.orig_env.get('PATH', '')}"
        }

    def _create_mock_binaries(self):
        mocks = {
            "gsettings": "#!/bin/sh\nexit 0\n",
            "systemctl": "#!/bin/sh\nexit 0\n",
            "dbus-update-activation-environment": "#!/bin/sh\nexit 0\n",
            "hyprctl": "#!/bin/sh\nexit 0\n",
        }
        for name, code in mocks.items():
            p = self.mock_bin / name
            p.write_text(code)
            p.chmod(0o755)

    def activate(self):
        os.environ.clear()
        os.environ.update(self.env)
        return self

    def deactivate(self):
        os.environ.clear()
        os.environ.update(self.orig_env)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def __enter__(self):
        return self.activate()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.deactivate()

    def assert_safe_path(self, target: Any, msg: str = ""):
        p = Path(target).resolve()
        assert p.is_relative_to(self.root), (
            f"TEST HYGIENE VIOLATION: Path '{p}' is outside isolated test root '{self.root}'! {msg}"
        )
        assert not p.is_relative_to(REAL_USER_HOME / ".local" / "share" / "icons"), (
            f"TEST HYGIENE VIOLATION: Path '{p}' points into real user ~/.local/share/icons!"
        )


class IsolatedTestCase(unittest.TestCase):
    def setUp(self):
        self.iso = IsolatedEnvironment(prefix=f"ctm-test-{self.__class__.__name__}-")
        self.iso.activate()
        self.test_dir = self.iso.test_dir
        self.env = self.iso.env

    def tearDown(self):
        self.iso.deactivate()

    def assert_safe_path(self, target: Any, msg: str = ""):
        self.iso.assert_safe_path(target, msg)
