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

    def test_graphics_setting_preserves_saved_theme(self):
        ui.UI_SETTINGS_FILE.write_text(
            json.dumps({"graphics_quality": "low", "theme": "nanotech_gold"}),
            encoding="utf-8",
        )
        ui.set_graphics_quality("high")
        saved = json.loads(ui.UI_SETTINGS_FILE.read_text(encoding="utf-8"))
        self.assertEqual(saved, {
            "graphics_quality": "high",
            "graphics_quality_mode": "manual",
            "theme": "nanotech_gold",
        })

    def test_legacy_graphics_setting_migrates_to_auto_until_overridden(self):
        ui.UI_SETTINGS_FILE.write_text(
            json.dumps({"graphics_quality": "high"}),
            encoding="utf-8",
        )
        self.assertEqual(ui.get_graphics_mode(), "auto")
        ui.set_graphics_quality("low")
        self.assertEqual(ui.get_graphics_mode(), "manual")
        self.assertEqual(ui.get_graphics_quality(), "low")

    def test_auto_graphics_result_is_saved_with_device_report(self):
        report = {
            "quality": "medium",
            "fingerprint": "device-123",
            "reason": "16 GB RAM · 4-core CPU · Integrated GPU",
        }
        self.assertEqual(ui.save_auto_graphics_result(report), "medium")
        saved = json.loads(ui.UI_SETTINGS_FILE.read_text(encoding="utf-8"))
        self.assertEqual(saved["graphics_quality_mode"], "auto")
        self.assertEqual(saved["graphics_quality"], "medium")
        self.assertEqual(saved["graphics_auto_fingerprint"], "device-123")
        self.assertEqual(saved["graphics_auto_report"], report)

    def test_manual_graphics_choice_wins_over_late_auto_result(self):
        ui.set_graphics_quality("high")
        with patch.object(ui, "save_auto_graphics_result") as save_result, \
             patch.object(self.window, "_apply_graphics_quality_live") as apply_live:
            self.window._finish_auto_graphics_detection({"quality": "low"})
        save_result.assert_not_called()
        apply_live.assert_not_called()
        self.assertEqual(ui.get_graphics_quality(), "high")

    def test_graphics_settings_include_auto_choice(self):
        overlay = ui.SettingsOverlay(
            current_graphics="medium",
            current_graphics_mode="auto",
        )
        self.assertEqual(set(overlay._graphics_btns), {"auto", "low", "medium", "high"})
        overlay.set_auto_graphics_result("high", "Detected discrete graphics")
        self.assertIn("HIGH", overlay._graphics_btns["auto"]._desc.text())
        self.assertIn("Detected discrete graphics", overlay._graphics_note.text())
        overlay.deleteLater()

    def test_explicit_self_quit_commands_route_to_argus(self):
        for command in (
            "quit ARGUS",
            "shut yourself down",
            "ARGUS, turn yourself off",
            "go offline ARGUS",
        ):
            self.assertEqual(ui.route_argus_ui_command(command), ("quit_argus", None))
        self.assertIsNone(ui.route_argus_ui_command("shut down my computer"))
        self.assertIsNone(ui.route_argus_ui_command("stop talking"))

    def test_quit_button_is_visible_and_accessible(self):
        button = self.window._quit_btn
        self.assertEqual(button.objectName(), "ArgusQuitButton")
        self.assertEqual(button.accessibleName(), "Quit ARGUS")
        self.assertEqual(button.toolTip(), "Quit ARGUS")
        self.assertFalse(button.isHidden())

    def test_dock_uses_crisp_command_rail_visual_language(self):
        rail = self.window._dock_frame
        style = rail.styleSheet().lower()
        self.assertEqual(rail.objectName(), "ArgusCommandRail")
        self.assertEqual(rail.accessibleName(), "ARGUS command rail")
        self.assertIsNone(rail.graphicsEffect())
        self.assertNotIn("qlineargradient", style)
        self.assertNotIn("border-radius: 24px", style)
        self.assertIn("border-radius: 6px", style)
        self.assertEqual(self.window._rail_control_track.objectName(), "CommandControlTrack")
        self.assertEqual(self.window._rail_control_track.accessibleName(), "Command controls")
        self.assertEqual(self.window._command_title_lbl.text(), "COMMAND RAIL")
        self.assertIn("LOCAL", self.window._rail_mode_lbl.text())

        buttons = rail.findChildren(ui.QPushButton)
        self.assertEqual(len(buttons), 8)
        for button in buttons:
            self.assertTrue(button.accessibleName().strip(), button.text())
            self.assertTrue(button.toolTip().strip(), button.text())
            self.assertNotIn("🎙", button.text())

        primary_buttons = (
            self.window._mute_btn,
            self.window._tts_btn,
            self.window._name_btn,
            self.window._theme_btn,
            self.window._quit_btn,
        )
        visible_labels = {button.text().split("·", 1)[0].strip() for button in primary_buttons}
        self.assertEqual(visible_labels, {"MIC", "VOICE", "NAME", "THEME", "QUIT"})

    def test_dock_mute_state_reuses_command_rail_style(self):
        original = self.window._muted
        try:
            self.window._muted = True
            self.window._style_mute_btn()
            self.assertIn("MUTED", self.window._mute_btn.text())
            self.assertEqual(self.window._mute_btn.accessibleName(), "Microphone muted")
            self.assertIn("border-radius: 5px", self.window._mute_btn.styleSheet())
            self.assertNotIn("border-radius: 17px", self.window._mute_btn.styleSheet())
        finally:
            self.window._muted = original
            self.window._style_mute_btn()

    def test_quit_command_uses_shared_shutdown_path(self):
        with patch.object(self.window, "_request_quit") as request_quit, \
             patch.object(ui.QTimer, "singleShot", side_effect=lambda _delay, callback: callback()):
            self.assertTrue(self.window._handle_ui_command("quit ARGUS"))
        request_quit.assert_called_once_with()

    def test_setup_overlay_is_centered_after_first_show(self):
        overlay = self.window._overlay
        self.assertIsNotNone(overlay)
        expected_x = (self.window.centralWidget().width() - overlay.width()) // 2
        expected_y = (self.window.centralWidget().height() - overlay.height()) // 2
        self.assertEqual((overlay.x(), overlay.y()), (expected_x, expected_y))

    def test_setup_exposes_replay_preference(self):
        overlay = ui.SetupOverlay(replay_every_launch=True)
        self.assertTrue(overlay.replay_intro_enabled())
        overlay._replay_intro.setChecked(False)
        self.assertFalse(overlay.replay_intro_enabled())
        overlay.deleteLater()

    def test_setup_validation_state_is_visible_and_recoverable(self):
        overlay = ui.SetupOverlay()
        overlay._key_input.setText("AIza-test-key")
        overlay.set_validating()
        self.assertTrue(overlay._setup_status.isVisibleTo(overlay))
        self.assertIn("VALIDATING GEMINI API KEY", overlay._setup_status.text())
        self.assertFalse(overlay._key_input.isEnabled())
        overlay.set_validation_error("API key is not valid.")
        self.assertTrue(overlay._key_input.isEnabled())
        self.assertTrue(overlay._init_btn.isVisibleTo(overlay))
        self.assertIn("API KEY VALIDATION FAILED", overlay._setup_status.text())
        overlay.deleteLater()

    def test_replay_selected_during_setup_applies_to_current_launch(self):
        original_overlay = self.window._overlay
        original_should_play = self.window._intro_should_play
        original_kind = self.window._startup_sequence_kind
        original_gate = self.window._interaction_gated
        overlay = ui.SetupOverlay(replay_every_launch=True)
        self.window._overlay = overlay
        self.window._intro_should_play = False
        self.window._startup_sequence_kind = ""
        try:
            with patch.object(ui.threading, "Thread") as thread:
                self.window._on_setup_done("AIza" + "x" * 30, "mac", False)
            self.assertTrue(self.window._intro_should_play)
            self.assertIn("VALIDATING GEMINI API KEY", overlay._setup_status.text())
            thread.assert_called_once()
        finally:
            self.window._overlay = original_overlay
            self.window._intro_should_play = original_should_play
            self.window._startup_sequence_kind = original_kind
            self.window._interaction_gated = original_gate
            overlay.deleteLater()

    def test_setup_api_guide_expands_without_clearing_the_key(self):
        overlay = ui.SetupOverlay()
        overlay.show()
        overlay._key_input.setText("AIza-test-key")
        self.assertFalse(overlay._guide_scroll.isVisible())
        overlay._guide_button.click()
        self.app.processEvents()
        self.assertTrue(overlay._guide_scroll.isVisible())
        self.assertEqual(overlay._key_input.text(), "AIza-test-key")
        self.assertIn("Hide API key guide", overlay._guide_button.text())
        overlay._guide_button.click()
        self.assertEqual(overlay._key_input.text(), "AIza-test-key")
        overlay.hide()
        overlay.deleteLater()

    def test_setup_api_guide_opens_official_ai_studio_page(self):
        overlay = ui.SetupOverlay()
        with patch.object(ui.QDesktopServices, "openUrl", return_value=True) as open_url:
            overlay._open_api_key_page()
        self.assertEqual(
            open_url.call_args.args[0].toString(),
            "https://aistudio.google.com/apikey",
        )
        overlay.deleteLater()

    def test_startup_backdrop_covers_the_live_console_during_setup(self):
        self.window._ensure_startup_backdrop()
        backdrop = self.window._startup_backdrop
        self.assertIsNotNone(backdrop)
        self.assertTrue(backdrop.isVisible())
        self.assertEqual(backdrop.geometry(), self.window.centralWidget().rect())
        self.assertIs(self.window._overlay.parentWidget(), self.window.centralWidget())

    def test_settings_exposes_replay_preference_after_setup(self):
        overlay = ui.SettingsOverlay(replay_intro=True)
        self.assertTrue(overlay._s_replay_intro.isChecked())
        changes = []
        overlay.intro_replay_changed.connect(changes.append)
        overlay._s_replay_intro.setChecked(False)
        self.assertEqual(changes, [False])
        tour_requests = []
        overlay.tour_replay_requested.connect(lambda: tour_requests.append(True))
        overlay._s_replay_tour.click()
        self.assertEqual(tour_requests, [True])
        overlay.deleteLater()

    def test_manual_tour_replay_activates_hard_interaction_lock(self):
        original = (
            self.window.on_tour_state_change,
            self.window._intro_in_progress,
            self.window._intro_voice_preparing,
            self.window._interaction_gated,
            self.window._manual_tour_replay,
        )
        states = []
        self.window.on_tour_state_change = states.append
        self.window._intro_in_progress = False
        self.window._intro_voice_preparing = False
        try:
            with (
                patch.object(ui, "_intro_voice_cache_path") as cache_path,
                patch.object(self.window, "_prepare_intro_voice") as prepare,
            ):
                cache_path.return_value = Path("/definitely/missing/tour.pcm")
                self.window._request_manual_tour_replay()
            self.assertTrue(self.window._interaction_gated)
            self.assertTrue(self.window._intro_in_progress)
            self.assertEqual(states, [True])
            prepare.assert_called_once()
        finally:
            (
                self.window.on_tour_state_change,
                self.window._intro_in_progress,
                self.window._intro_voice_preparing,
                self.window._interaction_gated,
                self.window._manual_tour_replay,
            ) = original

    def test_failed_tour_replay_returns_to_comms_and_releases_lock(self):
        original = (
            self.window._startup_sequence_kind,
            self.window._manual_tour_replay,
            self.window.on_tour_state_change,
            self.window._mission._active_tab,
        )
        states = []
        try:
            self.window._startup_sequence_kind = "tour"
            self.window._manual_tour_replay = True
            self.window.on_tour_state_change = states.append
            self.window._mission._switch_tab(3)
            self.window._on_intro_playback_failed("test failure", report=False)
            self.app.processEvents()
            self.assertEqual(self.window._mission._active_tab, 0)
            self.assertEqual(states, [False])
        finally:
            (
                self.window._startup_sequence_kind,
                self.window._manual_tour_replay,
                self.window.on_tour_state_change,
                original_tab,
            ) = original
            self.window._mission._switch_tab(original_tab)

    def test_segmented_tts_retries_when_model_returns_no_audio(self):
        empty_response = SimpleNamespace(candidates=[])
        client = MagicMock()
        client.aio.models.generate_content = AsyncMock(return_value=empty_response)
        with (
            patch("google.genai.Client", return_value=client),
        ):
            with self.assertRaisesRegex(RuntimeError, "returned no audio"):
                asyncio.run(ui._render_intro_segments_with_live(
                    ("Good evening.",), "charon", "test-key"
                ))
        self.assertEqual(
            client.aio.models.generate_content.await_count,
            ui.INTRO_CHAPTER_RENDER_ATTEMPTS * len(ui.INTRO_TTS_MODELS),
        )

    def test_segmented_tts_stops_immediately_on_quota_error(self):
        client = MagicMock()
        client.aio.models.generate_content = AsyncMock(
            side_effect=RuntimeError("429 RESOURCE_EXHAUSTED")
        )
        with patch("google.genai.Client", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "429"):
                asyncio.run(ui._render_intro_segments_with_live(
                    ("Good evening.",), "charon", "test-key"
                ))
        self.assertEqual(client.aio.models.generate_content.await_count, 1)

    def test_single_render_stops_immediately_on_quota_error(self):
        client = MagicMock()
        client.aio.models.generate_content = AsyncMock(
            side_effect=RuntimeError("429 RESOURCE_EXHAUSTED")
        )
        with patch("google.genai.Client", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "429"):
                asyncio.run(ui._render_intro_with_live(
                    "Good evening.", "kore", "test-key"
                ))
        self.assertEqual(client.aio.models.generate_content.await_count, 1)

    def test_full_tour_is_chaptered_for_a_ninety_second_delivery(self):
        chapters = ui._tour_chapters(datetime(2026, 1, 1, 19))
        narration = ui._tour_narration(datetime(2026, 1, 1, 19))
        captions = ui._tour_captions(datetime(2026, 1, 1, 19))
        self.assertEqual(len(chapters), 14)
        self.assertEqual(captions, tuple(chapter.caption for chapter in chapters))
        self.assertEqual(narration, " ".join(captions))
        self.assertGreaterEqual(len(narration.split()), 190)
        self.assertLessEqual(len(narration.split()), 225)
        self.assertEqual(ui.FirstRunIntroOverlay._TOUR_DURATION_S, 90.0)
        self.assertEqual(ui.FirstRunIntroOverlay._GREETING_DURATION_S, 18.0)
        self.assertEqual(ui.INTRO_SEQUENCE_VERSION, 5)

    def test_tour_chapters_cover_every_guided_region(self):
        chapters = ui._tour_chapters(datetime(2026, 1, 1, 19))
        self.assertEqual(
            {chapter.focus for chapter in chapters},
            {
                "core", "subtitles", "header", "awareness", "mission_comms",
                "mission_tasks", "mission_assets", "mission_tools", "input",
                "dock", "handoff",
            },
        )
        self.assertEqual(
            [chapter.tab_index for chapter in chapters if chapter.tab_index >= 0],
            [0, 1, 2, 3, 0, 0],
        )

    def test_chapter_signal_tracks_caption_boundaries(self):
        chapters = ui._tour_chapters(datetime(2026, 1, 1, 19))
        overlay = ui.FirstRunIntroOverlay(
            duration_s=90.0,
            speak=False,
            chapters=chapters,
            narration=" ".join(chapter.caption for chapter in chapters),
            captions=tuple(chapter.caption for chapter in chapters),
        )
        emitted = []
        overlay.chapter_changed.connect(lambda focus, label, tab: emitted.append((focus, label, tab)))
        overlay._started_at = ui.time.monotonic()
        overlay._tick()
        self.assertEqual(emitted[0], (chapters[0].focus, chapters[0].label, chapters[0].tab_index))
        last_index = overlay._caption_index_for_timeline(overlay._timeline_duration)
        self.assertEqual(last_index, len(chapters) - 1)
        overlay._timer.stop()
        overlay.deleteLater()

    def test_guided_tour_switches_real_tabs_and_restores_original(self):
        original_kind = self.window._startup_sequence_kind
        original_tab = self.window._mission._active_tab
        intro = ui.FirstRunIntroOverlay(
            self.window.centralWidget(), duration_s=90.0, speak=False,
        )
        try:
            self.window._mission._switch_tab(2)
            self.window._startup_sequence_kind = "tour"
            self.window._prepare_live_intro_widgets("tour")
            self.window._intro_overlay = intro
            intro.setGeometry(self.window.centralWidget().rect())
            self.window._on_intro_chapter_changed("mission_tools", "TOOLS", 3)
            self.assertEqual(self.window._mission._active_tab, 3)
            self.assertEqual(self.window._intro_focus_key, "mission_tools")
            self.assertTrue(intro._spotlight_target.isValid())
            self.assertTrue(intro._persistent_cutouts)
            self.window._restore_live_intro_widgets()
            self.assertEqual(self.window._mission._active_tab, 2)
        finally:
            self.window._intro_overlay = None
            self.window._startup_sequence_kind = original_kind
            self.window._mission._switch_tab(original_tab)
            intro.hide()
            intro.deleteLater()

    def test_tour_leaves_tools_for_comms_on_the_next_non_tool_chapter(self):
        original_kind = self.window._startup_sequence_kind
        original_tab = self.window._mission._active_tab
        intro = ui.FirstRunIntroOverlay(
            self.window.centralWidget(), duration_s=90.0, speak=False,
        )
        try:
            self.window._startup_sequence_kind = "tour"
            self.window._intro_overlay = intro
            intro.setGeometry(self.window.centralWidget().rect())
            self.window._on_intro_chapter_changed(
                "mission_tools", "TOOLS", 3
            )
            self.assertEqual(self.window._mission._active_tab, 3)

            self.window._on_intro_chapter_changed(
                "core", "REACTOR CORE", -1
            )
            self.assertEqual(self.window._mission._active_tab, 0)
        finally:
            self.window._intro_overlay = None
            self.window._startup_sequence_kind = original_kind
            self.window._mission._switch_tab(original_tab)
            intro.hide()
            intro.deleteLater()

    def test_mission_empty_states_are_visible_until_real_activity_arrives(self):
        task_widget = ui.TaskQueueWidget()
        tool_widget = ui.ToolLogWidget()
        task_widget.show()
        tool_widget.show()
        self.app.processEvents()
        self.assertTrue(task_widget._empty_state.isVisible())
        self.assertTrue(tool_widget._empty_state.isVisible())

        task_widget._on_task("Web Search", "calling")
        tool_widget._on_entry("🔧 web_search")
        self.app.processEvents()
        self.assertFalse(task_widget._empty_state.isVisible())
        self.assertFalse(tool_widget._empty_state.isVisible())
        task_widget.deleteLater()
        tool_widget.deleteLater()

    def test_tools_panel_ignores_generic_system_lifecycle_messages(self):
        entries = self.window._mission.tool_widget._entries
        original_entries = list(entries)
        entries.clear()
        try:
            self.window._parse_log_for_context("SYS: ARGUS online.")
            self.app.processEvents()
            self.assertEqual(entries, [])

            self.window._parse_log_for_context("🔧 web_search calling")
            self.app.processEvents()
            self.assertEqual(len(entries), 1)
            self.assertIn("web_search", entries[0]["text"])
        finally:
            entries[:] = original_entries
            self.window._mission.tool_widget._rebuild()

    def test_reduced_motion_spotlight_moves_without_animation(self):
        overlay = ui.FirstRunIntroOverlay(duration_s=90.0, speak=False)
        overlay.set_reduced_motion(True)
        target = ui.QRect(20, 30, 200, 100)
        overlay.set_spotlight(target, "AWARENESS")
        self.assertEqual(overlay._current_spotlight_rect(), ui.QRectF(target))
        self.assertEqual(overlay._spotlight_label, "AWARENESS")
        overlay.deleteLater()

    def test_core_spotlight_is_compact_and_circular(self):
        intro = ui.FirstRunIntroOverlay(
            self.window.centralWidget(), duration_s=90.0, speak=False
        )
        original_intro = self.window._intro_overlay
        original_kind = self.window._startup_sequence_kind
        try:
            self.window._intro_overlay = intro
            self.window._startup_sequence_kind = "tour"
            intro.setGeometry(self.window.centralWidget().rect())
            self.window._on_intro_chapter_changed("core", "REACTOR CORE", -1)
            full = self.window._intro_rect_for_widget(self.window.hud, 0)
            target = intro._spotlight_target
            self.assertEqual(int(target.width()), int(target.height()))
            self.assertLess(target.width(), full.width())
            self.assertEqual(intro._spotlight_shape, "ellipse")
        finally:
            self.window._intro_overlay = original_intro
            self.window._startup_sequence_kind = original_kind
            intro.deleteLater()

    def test_successful_tour_handoff_finishes_on_comms(self):
        original_kind = self.window._startup_sequence_kind
        original_tab = self.window._mission._active_tab
        try:
            self.window._startup_sequence_kind = "tour"
            self.window._mission._switch_tab(3)
            self.window._prepare_live_intro_widgets("tour")
            handoff = ui._tour_chapters(datetime(2026, 1, 1, 19))[-1]
            self.window._on_intro_chapter_changed(
                handoff.focus, handoff.label, handoff.tab_index
            )
            self.assertEqual(self.window._mission._active_tab, 0)
            self.window._restore_live_intro_widgets(handoff_to_comms=True)
            self.assertEqual(self.window._mission._active_tab, 0)
        finally:
            self.window._startup_sequence_kind = original_kind
            self.window._mission._switch_tab(original_tab)

    def test_tour_mask_uses_quieter_single_focus_treatment(self):
        source = inspect.getsource(ui.FirstRunIntroOverlay.paintEvent)
        self.assertIn("qcol(C.BG, 96)", source)
        self.assertIn('self._spotlight_shape == "ellipse"', source)
        self.assertIn("if spotlight.isEmpty():", source)

    def test_tour_temporarily_suppresses_presence_popups(self):
        timer = self.window._presence_system._presence_tmr
        timer.start()
        self.window._prepare_live_intro_widgets("tour")
        self.assertFalse(timer.isActive())
        self.window._restore_live_intro_widgets()
        self.assertTrue(timer.isActive())

    def test_tour_popup_cleanup_ignores_deleted_qt_wrappers(self):
        class DeletedPopup:
            def _dismiss(self):
                raise RuntimeError(
                    "wrapped C/C++ object of type BasePopup has been deleted"
                )

        manager = ui.PopupManager(self.window._ai_core_wrap)
        manager.active_popups = [DeletedPopup()]
        manager.dismiss_all_popups()
        self.assertEqual(manager.active_popups, [])

    def test_tour_start_failure_is_reported_and_does_not_escape_qt_slot(self):
        original = (
            self.window._startup_sequence_kind,
            self.window._startup_chapters,
            self.window._startup_captions,
            self.window._startup_narration,
            self.window._manual_tour_replay,
            self.window._intro_in_progress,
            self.window._interaction_gated,
        )
        chapters = ui._tour_chapters(datetime(2026, 1, 1, 19))
        self.window._startup_sequence_kind = "tour"
        self.window._startup_chapters = chapters
        self.window._startup_captions = tuple(chapter.caption for chapter in chapters)
        self.window._startup_narration = " ".join(self.window._startup_captions)
        self.window._manual_tour_replay = True
        self.window._intro_in_progress = True
        self.window._interaction_gated = True
        try:
            with (
                patch.object(
                    self.window._popup_manager,
                    "dismiss_all_popups",
                    side_effect=RuntimeError(
                        "wrapped C/C++ object of type BasePopup has been deleted"
                    ),
                ),
                patch.object(self.window, "_intro_terminal_report") as report,
                patch.object(ui.traceback, "print_exc"),
            ):
                self.window._start_first_run_intro()
            states = [call.args[0] for call in report.call_args_list]
            self.assertIn("FAILED", states)
            self.assertFalse(self.window._intro_in_progress)
            self.assertFalse(self.window._interaction_gated)
        finally:
            (
                self.window._startup_sequence_kind,
                self.window._startup_chapters,
                self.window._startup_captions,
                self.window._startup_narration,
                self.window._manual_tour_replay,
                self.window._intro_in_progress,
                self.window._interaction_gated,
            ) = original

    def test_startup_gate_blocks_text_callbacks_until_ready(self):
        original_ready = self.window._ready
        original_intro = self.window._intro_in_progress
        original_callback = self.window.on_text_command
        callback = MagicMock()
        self.window.on_text_command = callback
        self.window._ready = False
        self.window._intro_in_progress = True
        try:
            self.window._send("run a task")
            callback.assert_not_called()
        finally:
            self.window._ready = original_ready
            self.window._intro_in_progress = original_intro
            self.window.on_text_command = original_callback

    def test_operational_readiness_requires_every_startup_gate_to_clear(self):
        original = (
            self.window._ready,
            self.window._interaction_gated,
            self.window._intro_in_progress,
            self.window._intro_voice_preparing,
            self.window._intro_overlay,
            self.window._overlay,
        )
        try:
            self.window._ready = True
            self.window._interaction_gated = False
            self.window._intro_in_progress = False
            self.window._intro_voice_preparing = False
            self.window._intro_overlay = None
            self.window._overlay = None
            facade = ui.ArgusUI.__new__(ui.ArgusUI)
            facade._win = self.window
            self.assertTrue(facade.operational_ready)
            self.window._intro_in_progress = True
            self.assertFalse(facade.operational_ready)
            self.window._intro_in_progress = False
            self.window._intro_voice_preparing = True
            self.assertFalse(facade.operational_ready)
        finally:
            (
                self.window._ready,
                self.window._interaction_gated,
                self.window._intro_in_progress,
                self.window._intro_voice_preparing,
                self.window._intro_overlay,
                self.window._overlay,
            ) = original

    def test_splitter_uses_evaluated_stylesheet(self):
        sheet = self.window._splitter.styleSheet()
        self.assertNotIn('f"""', sheet)
        self.assertNotIn("{C.", sheet)
        self.assertIn("QSplitter::handle", sheet)

    def test_qss_alpha_colors_are_explicit_rgba(self):
        self.assertEqual(ui.qss_rgba("#ff2244", 0x22), "rgba(255, 34, 68, 34)")
        source = Path(ui.__file__).read_text(encoding="utf-8")
        self.assertNotRegex(source, r"\{C\.[A-Z_]+\}[0-9A-Fa-f]{2}")

    def test_unavailable_hardware_metrics_are_not_fabricated(self):
        self.window._gpu_info_cached = True
        self.window._gpu_chip = "GPU unavailable"
        self.window._gpu_vram_str = "N/A"
        with patch.object(ui, "_get_metrics", return_value=_MetricsSnapshot()):
            self.original_update_metrics(self.window)
        self.assertEqual(self.window._gpu_pct_lbl.text(), "N/A")
        self.assertEqual(self.window._spark_tmp._value, "N/A")
        self.assertEqual(self.window._gpu_load_bar.value(), 0)



if __name__ == "__main__":
    unittest.main()
