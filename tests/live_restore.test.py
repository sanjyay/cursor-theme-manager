#!/usr/bin/env python3
"""Hermetic regression tests for persistent versus live cursor restoration."""

import contextlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import cleanup_helper
import secure_state
from test_isolation import IsolatedTestCase


class TestLiveRestore(IsolatedTestCase):
    def baseline(self):
        return {
            "captured": True,
            "liveRestoreBackend": "gtk",
            "liveRestoreTheme": "Adwaita",
            "liveRestoreSize": 24,
            "gtkThemeSet": True,
            "gtkTheme": "Adwaita",
            "gtkSizeSet": True,
            "gtkSize": 24,
            "hyprcursorThemeSet": False,
            "xcursorThemeSet": False,
        }

    def exercise(self, live_result, signature="test-instance"):
        calls = []

        def fake_run(args, env_override=None, **kwargs):
            calls.append((list(args), dict(env_override or {})))
            if "setcursor" in args:
                live_result.argv = list(args)
                return live_result
            return cleanup_helper.CommandResult(ok=True, exit_code=0, argv=list(args))

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), \
             mock.patch.object(cleanup_helper, "run_cmd", side_effect=fake_run), \
             mock.patch.object(cleanup_helper, "find_hyprland_instance", return_value=signature), \
             mock.patch.object(cleanup_helper, "resolve_system_executable", return_value="/usr/bin/hyprctl"), \
             mock.patch.object(cleanup_helper, "has_cursor_data", return_value=True):
            ok = cleanup_helper.restore_cursor(self.baseline())
        return ok, calls, stderr.getvalue()

    def test_success_restores_persistent_then_exact_live_baseline(self):
        ok, calls, log = self.exercise(cleanup_helper.CommandResult(ok=True, exit_code=0))
        self.assertTrue(ok)
        self.assertEqual(calls[-1][0], ["/usr/bin/hyprctl", "setcursor", "Adwaita", "24"])
        self.assertEqual(calls[-1][1], {"HYPRLAND_INSTANCE_SIGNATURE": "test-instance"})
        self.assertTrue(any(call[0][0] == "gsettings" for call in calls[:-1]))
        self.assertTrue(any(call[0][0] == "systemctl" for call in calls[:-1]))
        self.assertIn("live_restore_ok=true", log)

    def test_nonzero_live_restore_fails(self):
        ok, _, log = self.exercise(cleanup_helper.CommandResult(ok=False, exit_code=1, stderr="connection failed"))
        self.assertFalse(ok)
        self.assertIn("exit=1", log)
        self.assertIn("live_restore_ok=false", log)

    def test_timed_out_live_restore_fails(self):
        ok, _, log = self.exercise(cleanup_helper.CommandResult(ok=False, exit_code=124, timed_out=True, error="command timed out"))
        self.assertFalse(ok)
        self.assertIn("timeout=true", log)
        self.assertIn("live_restore_ok=false", log)

    def test_missing_signature_cannot_report_success(self):
        ok, calls, log = self.exercise(cleanup_helper.CommandResult(ok=True, exit_code=0), signature=None)
        self.assertFalse(ok)
        self.assertFalse(any("setcursor" in call[0] for call in calls))
        self.assertIn("source=missing", log)

    def test_failed_live_restore_preserves_all_recovery_material(self):
        state = secure_state.read_state()
        state["cursorModifiedByCtm"] = True
        state["preCtmCursor"] = self.baseline()
        state["originalCursor"] = self.baseline()
        secure_state.write_state(state)

        paths = cleanup_helper.get_paths()
        Path(paths["cleanup_exe"]).parent.mkdir(parents=True, exist_ok=True)
        Path(paths["cleanup_exe"]).write_text("recovery helper", encoding="utf-8")
        Path(paths["path_unit"]).parent.mkdir(parents=True, exist_ok=True)
        Path(paths["path_unit"]).write_text("recovery unit", encoding="utf-8")
        cache = self.iso.user_icons / "CursorSwitcher-XCursor-Failure-deadbeef0000"
        cache.mkdir(parents=True)
        (cache / ".cursor-theme-manager-generated").write_text(
            "version=1\nkind=conversion-cache\nsourceTheme=Failure\n", encoding="utf-8"
        )

        stderr = io.StringIO()
        stdout = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout), \
             mock.patch.object(cleanup_helper, "restore_cursor", return_value=False):
            with self.assertRaises(SystemExit) as exited:
                cleanup_helper.execute_cleanup()
        self.assertEqual(exited.exception.code, 1)
        self.assertTrue((self.iso.state_dir / "state.json").is_file())
        self.assertTrue(Path(paths["cleanup_exe"]).is_file())
        self.assertTrue(Path(paths["path_unit"]).is_file())
        self.assertTrue(cache.is_dir())
        self.assertNotIn("Previous cursor configuration restored", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
