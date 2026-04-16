from __future__ import annotations

import unittest

from upskayledd.config import load_app_config


class ConfigTests(unittest.TestCase):
    def test_loads_profiles_and_defaults(self) -> None:
        config = load_app_config()
        self.assertEqual(config.app.name, "UPSKAYLEDD")
        self.assertTrue(config.profiles)
        self.assertEqual(config.profile_by_id("safe_review_required").label, "Safe Manual Review")
        self.assertEqual(config.app.output_layout, "preserve_relative")
        self.assertEqual(config.app.output_name_template, "{stem}")
        self.assertEqual(config.app.output_collision_template, "__dup{index}")
        self.assertTrue(config.app.probe_unknown_extensions)
        self.assertTrue(config.app.probe_extensionless_files)
        self.assertEqual(config.app.default_encode_profile_id, "hevc_balanced_archive")
        self.assertEqual(config.encode.default_profile_id, "hevc_balanced_archive")
        self.assertEqual(config.encode_profile_by_id("h264_compatibility_mp4").container, "mp4")
        self.assertEqual(config.encode_profile_by_id("h264_compatibility_mp4").audio_codec, "aac")
        self.assertIn("mov", config.supported_output_containers())
        self.assertIn("h264_compatibility_mp4", config.conversion_guidance.compatibility_profile_ids)
        self.assertGreater(config.conversion_guidance.oversized_ratio, 1.0)
        cleanup_mode = config.stage_mode("cleanup", "light_cleanup")
        self.assertIsNotNone(cleanup_mode)
        assert cleanup_mode is not None
        self.assertEqual(cleanup_mode.operation, "dpir")
        self.assertEqual(config.stage_mode("cleanup", "preserve_source").operation, "noop")
        self.assertEqual(config.stage_mode("cleanup", "balanced_cleanup").strength, 8.0)
        self.assertEqual(config.stage_mode("upscale", "faithful_resize").operation, "resize")
        self.assertEqual(config.stage_mode("upscale", "detail_recovery_live_action").model_name, "realSR_BSRGAN_DFO_s64w8_SwinIR_M_x4_PSNR")
        self.assertTrue(any(pack.id == "dpir_cleanup" for pack in config.model_packs.packs))


if __name__ == "__main__":
    unittest.main()
