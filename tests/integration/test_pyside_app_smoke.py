from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover - optional dependency in test environments
    QApplication = None

ROOT = Path(__file__).resolve().parents[2]
DESKTOP_APPS = ROOT / "apps" / "desktop"
if str(DESKTOP_APPS) not in sys.path:
    sys.path.insert(0, str(DESKTOP_APPS))

from upskayledd.app_service import AppService
from pyside_app.controller import DesktopController
from pyside_app.ui_config import load_ui_config
from pyside_app.window import DesktopMainWindow


def make_temp_config(temp_dir: Path) -> Path:
    config_dir = temp_dir / "config"
    shutil.copytree(ROOT / "config", config_dir)
    defaults_path = config_dir / "defaults.toml"
    defaults = defaults_path.read_text(encoding="utf-8")
    replacements = {
        'default_output_root = "runtime/output"': f'default_output_root = "{(temp_dir / "output").as_posix()}"',
        'state_db_path = "runtime/state/upskayledd.sqlite3"': f'state_db_path = "{(temp_dir / "state.sqlite3").as_posix()}"',
        'preview_cache_dir = "runtime/cache/previews"': f'preview_cache_dir = "{(temp_dir / "preview_cache").as_posix()}"',
    }
    for old, new in replacements.items():
        defaults = defaults.replace(old, new)
    defaults_path.write_text(defaults, encoding="utf-8")
    return config_dir


class PySideAppSmokeTests(unittest.TestCase):
    def test_offscreen_desktop_flow_ingests_previews_and_queues(self) -> None:
        if QApplication is None:
            self.skipTest("PySide6 not available")
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("ffmpeg not available")

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = make_temp_config(temp_path)
            season_dir = temp_path / "season"
            season_dir.mkdir()
            aligned_source = season_dir / "episode01.mp4"
            outlier_source = season_dir / "episode02_outlier.mp4"
            fixtures = [
                (aligned_source, "color=c=black:s=320x240:d=0.6", "25"),
                (outlier_source, "color=c=black:s=640x480:d=0.6", "15"),
            ]
            for path, source_filter, fps in fixtures:
                subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        source_filter,
                        "-r",
                        fps,
                        "-pix_fmt",
                        "yuv420p",
                        str(path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )

            controller = DesktopController(
                service=AppService(str(config_dir)),
                ui_config=load_ui_config(),
            )
            window = DesktopMainWindow(controller, load_ui_config())
            window.show()
            app.processEvents()
            self.assertFalse(window.windowIcon().isNull())
            self.assertTrue(bool(window.ingest_page.drop_target.toolTip()))
            self.assertTrue(window.queue_bar.isHidden())
            self._wait_for(
                app,
                lambda: window.ingest_page.runtime_doctor_summary.text() != "Waiting for the first environment refresh.",
            )
            self.assertNotEqual(
                window.ingest_page.runtime_platform_summary.text(),
                window.ui_config.copy.runtime.platform_empty,
            )
            self.assertGreater(window.ingest_page.focus_table.rowCount(), 0)
            self.assertGreater(window.ingest_page.pack_table.rowCount(), 0)
            self.assertGreater(window.ingest_page.locations_stack.count(), 0)

            controller.ingest_target(str(season_dir))
            self._wait_for(app, lambda: controller.current_project is not None)
            self.assertEqual(controller.session.current_page, "summary")
            self.assertGreater(window.workspace_page.stage_rail.count(), 0)
            self.assertEqual(window.summary_page.batch_table.rowCount(), 2)
            self.assertTrue(window.summary_page.review_flagged_button.isEnabled())
            summary_text = window.summary_page.recommendation_view.toPlainText()
            self.assertIn(f"{window.ui_config.copy.summary.delivery_guidance_label}:", summary_text)
            self.assertIn(f"{window.ui_config.copy.summary.alternative_profiles_label}:", summary_text)

            window.summary_page.review_flagged_button.click()
            app.processEvents()
            app.processEvents()
            self.assertEqual(controller.session.current_page, "workspace")
            self.assertEqual(window.workspace_page.comparison_mode.currentText(), controller.session.comparison_mode)
            self.assertEqual(controller.session.selected_source, str(outlier_source.resolve()))
            self.assertIn("manual review", window.workspace_page.source_context_label.text().lower())
            self.assertTrue(bool(window.workspace_page.source_picker.toolTip()))
            self.assertTrue(bool(window.dashboard_page.jobs_table.toolTip()))

            controller.select_stage("encode")
            app.processEvents()
            encode_profile_widget = window.workspace_page._setting_widgets.get("encode:output_policy:encode_profile_id")
            container_widget = window.workspace_page._setting_widgets.get("encode:output_policy:container")
            chapter_widget = window.workspace_page._setting_widgets.get("encode:output_policy:preserve_chapters")
            self.assertIsNotNone(encode_profile_widget)
            self.assertIsNotNone(container_widget)
            self.assertIsNotNone(chapter_widget)
            assert encode_profile_widget is not None
            assert container_widget is not None
            self.assertTrue(bool(encode_profile_widget.toolTip()))
            self.assertIn("MP4", [container_widget.itemText(index) for index in range(container_widget.count())])
            compatibility_index = next(
                (
                    index
                    for index in range(encode_profile_widget.count())
                    if encode_profile_widget.itemData(index) == "h264_compatibility_mp4"
                ),
                -1,
            )
            self.assertGreaterEqual(compatibility_index, 0)
            encode_profile_widget.setCurrentIndex(compatibility_index)
            app.processEvents()
            self.assertEqual(controller.current_project.manifest.output_policy["encode_profile_id"], "h264_compatibility_mp4")
            self.assertEqual(controller.current_project.manifest.output_policy["container"], "mp4")
            self.assertEqual(controller.current_project.delivery_guidance["selected_profile_id"], "h264_compatibility_mp4")

            controller.select_stage("cleanup")
            app.processEvents()

            controller.request_preview(
                comparison_mode="slider_wipe",
                fidelity_mode="approximate",
                sample_start_seconds=0.0,
                sample_duration_seconds=0.5,
            )
            self._wait_for(app, lambda: controller.preview_payload is not None)
            self.assertIn("processed", controller.preview_payload["comparison_artifacts"])

            controller.select_source(str(aligned_source.resolve()))
            app.processEvents()
            self.assertIsNone(controller.preview_payload)
            self.assertIn("representative preview target", window.workspace_page.source_context_label.text().lower())

            controller.queue_current_project()
            self._wait_for(app, lambda: bool(controller.dashboard_payload.get("jobs")))
            self.assertTrue(controller.dashboard_payload["jobs"])
            self.assertTrue(window.queue_bar.isVisible())
            self.assertIn("Next up:", window.queue_bar.summary_label.text())
            self.assertEqual(window.dashboard_page.overall_progress_bar.value(), 0)
            self.assertIn("queued and ready for execution", window.dashboard_page.focus_label.text().lower())
            self.assertTrue(window.dashboard_page.open_output_button.isEnabled())

            window.workspace_page.preview_compare.clear_preview()
            window.close()
            window.deleteLater()
            app.processEvents()

            second_controller = DesktopController(
                service=AppService(str(config_dir)),
                ui_config=load_ui_config(),
            )
            second_window = DesktopMainWindow(second_controller, load_ui_config())
            second_window.show()
            app.processEvents()
            self._wait_for(app, lambda: second_window.ingest_page.recent_list.count() > 0)
            first_recent = second_window.ingest_page.recent_list.item(0)
            self.assertIsNotNone(first_recent)
            assert first_recent is not None
            self.assertIn("season", first_recent.text().lower())
            self.assertIn("sources", first_recent.text().lower())
            second_window.close()
            second_window.deleteLater()
            app.processEvents()

    def _wait_for(self, app: QApplication, predicate, timeout_seconds: float = 20.0) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            app.processEvents()
            if predicate():
                return
            time.sleep(0.05)
        self.fail("Timed out waiting for desktop flow to complete.")


if __name__ == "__main__":
    unittest.main()
