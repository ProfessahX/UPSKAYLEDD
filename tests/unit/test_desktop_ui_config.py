from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
DESKTOP_APPS = ROOT / "apps" / "desktop"
if str(DESKTOP_APPS) not in sys.path:
    sys.path.insert(0, str(DESKTOP_APPS))

from pyside_app.ui_config import load_ui_config


class DesktopUiConfigTests(unittest.TestCase):
    def test_loads_preview_defaults_and_stage_metadata(self) -> None:
        config = load_ui_config()

        self.assertEqual(config.preview.default_comparison_mode, "slider_wipe")
        self.assertIn("side_by_side", config.preview.comparison_modes)
        self.assertEqual(config.theme.background_start, "#0b0f15")
        self.assertEqual(config.assets.app_icon, "icon.png")
        self.assertEqual(config.layout.brand_panel_width, 360)
        self.assertEqual(config.copy.global_text.doctor_button, "Review Runtime")
        self.assertEqual(config.copy.global_text.tagline, "Inspect first. Restore carefully. Batch with confidence.")
        self.assertEqual(config.copy.global_text.support_button, "Export Support Bundle")
        self.assertEqual(config.copy.runtime.actions_title, "Guided Next Steps")
        self.assertEqual(config.copy.runtime.locations_title, "Runtime Paths")
        self.assertEqual(config.copy.runtime.location_labels["output_root"], "Output")
        self.assertEqual(config.copy.ingest.recent_title, "Recent Targets")
        self.assertEqual(config.copy.queue.processing_template, "Processing: {source_name} - {progress_percent:.0f}% complete")
        self.assertEqual(config.copy.dashboard.run_summary_title, "Run Summary")
        self.assertEqual(config.copy.dashboard.overview_title, "Batch Overview")
        self.assertEqual(config.copy.dashboard.open_output_button, "Open Output Folder")
        self.assertIn("drag", config.copy.tooltip("drop_target").lower())
        self.assertIn("queue", config.copy.tooltip("workspace_queue_project").lower())
        self.assertIn("profile-outlier", config.copy.summary.batch_review_attention)

        upscale = config.stage("upscale")
        self.assertIsNotNone(upscale)
        self.assertTrue(any(control.key == "width" for control in upscale.controls))
        self.assertTrue(any(control.key == "mode" and control.tier == "simple" for control in upscale.controls))
        self.assertEqual(upscale.rail_label, "Upscale")

    def test_loads_from_bundled_config_when_frozen(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_root = Path(temp_dir) / "bundle"
            shutil.copytree(ROOT / "config", bundle_root / "config")

            with patch("upskayledd.core.paths.sys.frozen", True, create=True):
                with patch("upskayledd.core.paths.sys._MEIPASS", str(bundle_root), create=True):
                    config = load_ui_config()

            self.assertEqual(config.window.title, "UPSKAYLEDD")
            self.assertEqual(config.copy.global_text.support_button, "Export Support Bundle")
            self.assertEqual(config.assets.hero_graphic, "Shitposting_pitch_refined.png")


if __name__ == "__main__":
    unittest.main()
