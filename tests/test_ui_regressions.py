import json
import inspect
import os
import tempfile
import unittest
import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

import ui


class _NoSecrets:
    def get(self, _key):
        return None


class _MetricsSnapshot:
    def snapshot(self):
        return {"cpu": 1.0, "mem": 1.0, "net": 0.0, "gpu": -1.0, "tmp": -1.0}


class UIRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(cls.temp_dir.name)

        cls.original_update_metrics = staticmethod(ui.MainWindow._update_metrics)
        cls.patchers = [
            patch.object(ui, "UI_SETTINGS_FILE", temp_path / "ui_settings.json"),
            patch.object(ui, "LAYOUT_SETTINGS_FILE", temp_path / "layout_settings.json"),
            patch.object(ui, "API_FILE", temp_path / "api_keys.json"),
            patch.object(ui, "get_secret_store", return_value=_NoSecrets()),
            patch.object(ui.MainWindow, "_setup_system_tray", lambda self: None),
            patch.object(ui.MainWindow, "_update_metrics", lambda self: None),
            patch.object(ui.MainWindow, "_restore_detached_panels", lambda self: None),
            patch.object(ui.MainWindow, "_start_layout_autosave", lambda self: None),
            patch.object(ui.MainWindow, "_start_auto_graphics_detection", lambda self: None),
        ]
        for patcher in cls.patchers:
            patcher.start()

        ui.UI_SETTINGS_FILE.write_text(
            json.dumps({"intro_completed": True, "intro_every_launch": False}),
            encoding="utf-8",
        )
        cls.window = ui.MainWindow("face.png")
        cls.window.show()
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.window.hide()
        cls.window.deleteLater()
        cls.app.processEvents()
        for patcher in reversed(cls.patchers):
            patcher.stop()
        cls.temp_dir.cleanup()

    def test_every_theme_has_a_complete_valid_palette(self):
        required = set(ui.ThemeManager._COLOR_KEYS)
        for name, theme in ui.ThemeManager._THEMES.items():
            self.assertFalse(required - set(theme), name)
            for key in required:
                self.assertRegex(theme[key], r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")

    def test_theme_change_updates_existing_widget_styles(self):
        ui.ThemeManager.set_theme("arc_reactor")
        ui.ThemeManager.set_theme("stealth_red")
        self.app.processEvents()
        self.assertEqual(ui.C.BG, "#080203")
        self.assertIn("#080203", self.window.centralWidget().styleSheet().lower())

    def test_quit_button_is_visible_and_accessible(self):
        button = self.window._quit_btn
        self.assertEqual(button.objectName(), "ArgusQuitButton")
        self.assertEqual(button.accessibleName(), "Quit ARGUS")
        self.assertEqual(button.toolTip(), "Quit ARGUS")
        self.assertFalse(button.isHidden())

    def test_quit_command_uses_shared_shutdown_path(self):
        with patch.object(self.window, "_request_quit") as request_quit, \
             patch.object(ui.QTimer, "singleShot", side_effect=lambda _delay, callback: callback()):
            self.assertTrue(self.window._handle_ui_command("quit ARGUS"))
        request_quit.assert_called_once_with()

    def test_splitter_uses_evaluated_stylesheet(self):
        sheet = self.window._splitter.styleSheet()
        self.assertNotIn('f"""', sheet)
        self.assertNotIn("{C.", sheet)
        self.assertIn("QSplitter::handle", sheet)

if __name__ == "__main__":
    unittest.main()
