#!/usr/bin/env python3
"""Regression tests for the real QML-to-helper live cursor mutation path."""

import importlib.machinery
import importlib.util
import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_isolation import IsolatedTestCase
import runtime_safety
import secure_state

loader = importlib.machinery.SourceFileLoader("ctm_cursorctl_barrier", str(SCRIPTS / "cursorctl"))
spec = importlib.util.spec_from_loader(loader.name, loader)
cursorctl = importlib.util.module_from_spec(spec)
loader.exec_module(cursorctl)


BASELINE = {
    "captured": True,
    "hyprcursorThemeSet": True, "hyprcursorTheme": "Adwaita",
    "hyprcursorSizeSet": True, "hyprcursorSize": 24,
    "xcursorThemeSet": True, "xcursorTheme": "Adwaita",
    "xcursorSizeSet": True, "xcursorSize": 24,
    "gtkThemeSet": True, "gtkTheme": "Adwaita",
    "gtkSizeSet": True, "gtkSize": 24,
    "liveRestoreBackend": "gtk",
    "liveRestoreTheme": "Adwaita", "liveRestoreSize": 24,
    "liveBackend": "gtk", "liveTheme": "Adwaita", "liveSize": 24,
}


class TestFirstMutationBarrier(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.events = []

    def _capture(self):
        self.events.append("baseline-capture-requested")
        return dict(BASELINE)

    def _write(self, state):
        result = self.real_write(state)
        if result:
            self.events.append("baseline-durable")
            if secure_state.read_state().get("cursorModifiedByCtm"):
                self.events.append("modified-flag-durable")
        return result

    def _run(self, argv, **kwargs):
        if len(argv) > 1 and argv[1] == "setcursor":
            self.events.append("hyprctl-setcursor:" + ":".join(argv[2:]))
        return runtime_safety.BoundedResult(0, b"ok\n", b"")

    def _patch_success(self):
        self.real_write = secure_state.write_state
        return (
            mock.patch.object(cursorctl.secure_state, "capture_original_cursor", side_effect=self._capture),
            mock.patch.object(cursorctl.secure_state, "write_state", side_effect=self._write),
            mock.patch.object(cursorctl, "run_bounded", side_effect=self._run),
        )

    def test_first_theme_click_is_durable_before_setcursor(self):
        p1, p2, p3 = self._patch_success()
        with p1, p2, p3:
            cursorctl.perform_live_cursor_mutation("Banana", 64)

        self.assertLess(self.events.index("baseline-durable"), self.events.index("hyprctl-setcursor:Banana:64"))
        self.assertLess(self.events.index("modified-flag-durable"), self.events.index("hyprctl-setcursor:Banana:64"))
        state = secure_state.read_state()
        self.assertTrue(state["preCtmCursor"]["captured"])
        self.assertTrue(state["cursorModifiedByCtm"])

    def test_capture_failure_performs_zero_setcursor_calls(self):
        with mock.patch.object(cursorctl.secure_state, "capture_original_cursor", return_value={"captured": False}), \
             mock.patch.object(cursorctl, "run_bounded", side_effect=self._run):
            with self.assertRaisesRegex(RuntimeError, "no cursor change"):
                cursorctl.perform_live_cursor_mutation("Banana", 64)
        self.assertFalse(any(event.startswith("hyprctl-setcursor") for event in self.events))

    def test_durable_write_failure_performs_zero_setcursor_calls(self):
        with mock.patch.object(cursorctl.secure_state, "capture_original_cursor", side_effect=self._capture), \
             mock.patch.object(cursorctl.secure_state, "write_state", return_value=False), \
             mock.patch.object(cursorctl, "run_bounded", side_effect=self._run):
            with self.assertRaisesRegex(RuntimeError, "durably persist"):
                cursorctl.perform_live_cursor_mutation("Banana", 64)
        self.assertFalse(any(event.startswith("hyprctl-setcursor") for event in self.events))

    def test_subsequent_theme_change_does_not_recapture(self):
        p1, p2, p3 = self._patch_success()
        with p1, p2, p3:
            cursorctl.perform_live_cursor_mutation("Banana", 64)
            cursorctl.perform_live_cursor_mutation("Yaru", 32)
        self.assertEqual(self.events.count("baseline-capture-requested"), 1)
        self.assertIn("hyprctl-setcursor:Yaru:32", self.events)

    def test_first_size_only_change_uses_same_barrier(self):
        p1, p2, p3 = self._patch_success()
        with p1, p2, p3:
            cursorctl.perform_live_cursor_mutation("Adwaita", 64)
        self.assertLess(self.events.index("modified-flag-durable"), self.events.index("hyprctl-setcursor:Adwaita:64"))

    def test_actual_qml_theme_size_and_import_routes_cannot_call_hyprctl_directly(self):
        qml = (ROOT / "CursorService.qml").read_text(encoding="utf-8")
        self.assertNotIn('[root.trustedHyprctlPath, "setcursor"', qml)
        self.assertGreaterEqual(qml.count('[helperPath, "setcursor-live"'), 2)
        # Import publication selects the authoritative imported theme through
        # commitTheme, which reaches the same setcursor-live service path.
        self.assertIn('if (foundTheme) {\n          commitTheme(foundTheme, "import-model-refresh")', qml)
        self.assertIn("function commitTheme(theme, source)", qml)

    def test_qml_mutations_are_bound_to_the_loaded_installation(self):
        qml = (ROOT / "CursorService.qml").read_text(encoding="utf-8")
        helper = (SCRIPTS / "cursorctl").read_text(encoding="utf-8")
        self.assertIn('bound.push("--plugin-fingerprint", integrationPluginFingerprint)', qml)
        for process in (
            "liveThemeProcess", "liveSetcursorProcess", "persistThemeProcess",
            "persistSizeProcess", "stateWriteProcess", "integrationEnableProcess",
            "integrationDisableProcess", "importProcess", "removeImportProcess",
            "renameImportProcess",
        ):
            self.assertRegex(qml, rf"{process}\.command = mutationCommand\(")
        self.assertIn("running_from_installed_plugin and not expected_fingerprint", helper)
        self.assertIn("expected_fingerprint != current_fingerprint", helper)

    def test_transient_durability_replacement_retries_once_before_setcursor(self):
        fingerprint = "a" * 64
        storage = secure_state.validate_state_dict(None)
        writes = []

        def fake_read():
            return copy.deepcopy(storage)

        def fake_write(state):
            writes.append(copy.deepcopy(state))
            if len(writes) == 2:
                storage.clear()
                storage.update(copy.deepcopy(secure_state.validate_state_dict(state)))
            return True

        with mock.patch.object(cursorctl.secure_state, "read_state", side_effect=fake_read), \
             mock.patch.object(cursorctl.secure_state, "write_state", side_effect=fake_write), \
             mock.patch.object(cursorctl.secure_state, "capture_original_cursor", return_value=dict(BASELINE)), \
             mock.patch.object(cursorctl.integration_manager, "get_plugin_installation_fingerprint", return_value=fingerprint), \
             mock.patch.object(cursorctl, "run_bounded", side_effect=self._run):
            cursorctl.perform_live_cursor_mutation("Banana", 64, fingerprint)

        self.assertEqual(len(writes), 2)
        self.assertEqual(self.events.count("hyprctl-setcursor:Banana:64"), 1)
        self.assertTrue(storage["cursorModifiedByCtm"])
        self.assertEqual(storage["integrationPluginFingerprint"], fingerprint)

    def test_repeated_durability_replacement_fails_without_setcursor(self):
        fingerprint = "b" * 64
        empty = secure_state.validate_state_dict(None)
        with mock.patch.object(cursorctl.secure_state, "read_state", side_effect=lambda: copy.deepcopy(empty)), \
             mock.patch.object(cursorctl.secure_state, "write_state", return_value=True), \
             mock.patch.object(cursorctl.secure_state, "capture_original_cursor", return_value=dict(BASELINE)), \
             mock.patch.object(cursorctl.integration_manager, "get_plugin_installation_fingerprint", return_value=fingerprint), \
             mock.patch.object(cursorctl, "run_bounded", side_effect=self._run):
            with self.assertRaisesRegex(RuntimeError, "retry shortly"):
                cursorctl.perform_live_cursor_mutation("Banana", 64, fingerprint)
        self.assertFalse(any(event.startswith("hyprctl-setcursor") for event in self.events))


if __name__ == "__main__":
    unittest.main()
