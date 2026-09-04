import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Any, Optional
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import runtime_safety

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
        self.plugin_dir = self.omarchy_plugins / "sanjyay.cursor-theme-manager"

        # Create all required directory trees
        for d in [
            self.home, self.xdg_data, self.xdg_state, self.xdg_config, self.xdg_cache,
            self.user_icons, self.user_apps, self.state_dir, self.libexec_dir,
            self.systemd_user, self.omarchy_plugins, self.plugin_dir, self.mock_bin,
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
            "XDG_RUNTIME_DIR": str(self.root / "run"),
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path={self.root / 'run' / 'no-session-bus'}",
            "HYPRLAND_INSTANCE_SIGNATURE": "",
            "WAYLAND_DISPLAY": "",
            "PATH": f"{self.mock_bin}:{self.orig_env.get('PATH', '')}"
        }
        (self.root / "run").mkdir(mode=0o700, exist_ok=True)

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
        runtime_safety._RESOLVED_TOOL_CACHE.clear()
        self.iso = IsolatedEnvironment(prefix=f"ctm-test-{self.__class__.__name__}-")
        self.iso.activate()
        self.test_dir = self.iso.test_dir
        self.env = self.iso.env

        # Patch run_bounded to intercept system commands targeting live daemons
        self._orig_run_bounded = runtime_safety.run_bounded
        def _safe_test_run_bounded(argv, *args, **kwargs):
            if argv:
                cmd_str = " ".join(str(a) for a in argv)
                if any(tool in cmd_str for tool in ("systemctl", "gsettings", "hyprctl", "dbus-update-activation-environment")):
                    out = b"active\n" if ("is-active" in argv and "cursor-theme-manager-cleanup.path" in argv) else b""
                    return runtime_safety.BoundedResult(
                        exit_code=0, stdout=out, stderr=b"", timed_out=False, limit_exceeded=False
                    )
            return self._orig_run_bounded(argv, *args, **kwargs)

        self._patcher_run = mock.patch("runtime_safety.run_bounded", side_effect=_safe_test_run_bounded)
        self._patcher_run.start()

        # Modules that import run_bounded directly retain their own reference;
        # patch those aliases too so an isolated test can never mutate the live
        # user systemd manager (for example by disabling CTM's real path unit).
        self._module_run_patchers = []
        for module_name in ("integration_manager", "cursor_theming"):
            module = sys.modules.get(module_name)
            if module is not None and hasattr(module, "run_bounded"):
                patcher = mock.patch.object(module, "run_bounded", side_effect=_safe_test_run_bounded)
                patcher.start()
                self._module_run_patchers.append(patcher)

        # Patch resolve_system_executable to resolve test mocks in memory without production backdoors
        self._orig_resolve = runtime_safety.resolve_system_executable
        def _safe_test_resolve(name):
            if not name or not isinstance(name, str):
                return None
            mock_path = self.iso.mock_bin / name
            if mock_path.is_file():
                return str(mock_path)
            return self._orig_resolve(name)

        self._patcher_resolve = mock.patch("runtime_safety.resolve_system_executable", side_effect=_safe_test_resolve)
        self._patcher_resolve.start()

    def tearDown(self):
        for patcher in reversed(self._module_run_patchers):
            patcher.stop()
        self._patcher_resolve.stop()
        self._patcher_run.stop()
        self.iso.deactivate()
        runtime_safety._RESOLVED_TOOL_CACHE.clear()

    def assert_safe_path(self, target: Any, msg: str = ""):
        self.iso.assert_safe_path(target, msg)
