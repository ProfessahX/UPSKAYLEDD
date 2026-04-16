from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from upskayledd.config import _normalize_model_dirs, load_app_config
from upskayledd.core.errors import ConfigError


class ConfigTests(unittest.TestCase):
    def test_loads_profiles_and_defaults(self) -> None:
        config = load_app_config()
        self.assertEqual(config.app.name, "UPSKAYLEDD")
        self.assertTrue(config.profiles)
        self.assertEqual(config.profile_by_id("safe_review_required").label, "Safe Manual Review")
        self.assertEqual(config.app.output_layout, "preserve_relative")
        self.assertEqual(config.app.output_name_template, "{stem}")
        self.assertEqual(config.app.output_collision_template, "__dup{index}")
        self.assertEqual(config.app.scratch_dir, "runtime/scratch")
        self.assertTrue(config.app.probe_unknown_extensions)
        self.assertTrue(config.app.probe_extensionless_files)
        self.assertEqual(config.app.default_encode_profile_id, "hevc_balanced_archive")
        self.assertEqual(config.encode.default_profile_id, "hevc_balanced_archive")
        self.assertEqual(config.encode_profile_by_id("h264_compatibility_mp4").container, "mp4")
        self.assertEqual(config.encode_profile_by_id("h264_compatibility_mp4").audio_codec, "aac")
        self.assertIn("mov", config.supported_output_containers())
        self.assertIn("h264_compatibility_mp4", config.conversion_guidance.compatibility_profile_ids)
        self.assertIn("hevc_balanced_archive", config.delivery_guidance.archive_profile_ids)
        self.assertIn("hevc_smaller_archive", config.delivery_guidance.smaller_profile_ids)
        self.assertIn("h264_compatibility_mp4", config.delivery_guidance.compatibility_profile_ids)
        self.assertIn("wsl_environment", config.runtime_actions.contexts)
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

    def test_normalize_model_dirs_filters_non_native_platform_defaults(self) -> None:
        raw_dirs = (
            "runtime/models",
            "%LOCALAPPDATA%/UPSKAYLEDD/models",
            "$HOME/.local/share/upskayledd/models",
        )

        with patch("upskayledd.config.os.name", "nt"):
            windows_dirs = _normalize_model_dirs(raw_dirs)
        with patch("upskayledd.config.os.name", "posix"):
            linux_dirs = _normalize_model_dirs(raw_dirs)

        self.assertIn("runtime/models", windows_dirs)
        self.assertIn("%LOCALAPPDATA%/UPSKAYLEDD/models", windows_dirs)
        self.assertNotIn("$HOME/.local/share/upskayledd/models", windows_dirs)
        self.assertIn("runtime/models", linux_dirs)
        self.assertIn("$HOME/.local/share/upskayledd/models", linux_dirs)
        self.assertNotIn("%LOCALAPPDATA%/UPSKAYLEDD/models", linux_dirs)

    def test_load_app_config_rejects_unknown_delivery_guidance_profile_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = temp_path / "config"
            shutil.copytree(Path(__file__).resolve().parents[2] / "config", config_dir)
            guidance_path = config_dir / "delivery_guidance.toml"
            payload = guidance_path.read_text(encoding="utf-8")
            guidance_path.write_text(
                payload.replace('compatibility_ids = ["h264_compatibility_mp4"]', 'compatibility_ids = ["missing_profile"]'),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigError):
                load_app_config(str(config_dir))

    def test_load_app_config_uses_resolved_encode_default_consistently(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = temp_path / "config"
            shutil.copytree(Path(__file__).resolve().parents[2] / "config", config_dir)
            encode_profiles_path = config_dir / "encode_profiles.toml"
            payload = encode_profiles_path.read_text(encoding="utf-8")
            encode_profiles_path.write_text(
                payload.replace('default_profile_id = "hevc_balanced_archive"', 'default_profile_id = "h264_compatibility_mp4"', 1),
                encoding="utf-8",
            )

            config = load_app_config(str(config_dir))

            self.assertEqual(config.encode.default_profile_id, "h264_compatibility_mp4")
            self.assertEqual(config.app.default_encode_profile_id, "h264_compatibility_mp4")

    def test_load_app_config_uses_default_delivery_guidance_when_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = temp_path / "config"
            shutil.copytree(Path(__file__).resolve().parents[2] / "config", config_dir)
            (config_dir / "delivery_guidance.toml").unlink()

            config = load_app_config(str(config_dir))

            self.assertEqual(config.delivery_guidance.archive_profile_ids[0], config.encode.default_profile_id)
            self.assertIn("h264_compatibility_mp4", config.delivery_guidance.compatibility_profile_ids)
            self.assertTrue(config.delivery_guidance.messages)

    def test_normalize_model_dirs_keeps_windows_and_unix_paths_inside_wsl(self) -> None:
        raw_dirs = (
            "runtime/models",
            "%LOCALAPPDATA%/UPSKAYLEDD/models",
            "$HOME/.local/share/upskayledd/models",
        )

        with patch("upskayledd.config.os.name", "posix"), patch("upskayledd.config._is_wsl_environment", return_value=True):
            model_dirs = _normalize_model_dirs(raw_dirs)

        self.assertIn("runtime/models", model_dirs)
        self.assertIn("%LOCALAPPDATA%/UPSKAYLEDD/models", model_dirs)
        self.assertIn("$HOME/.local/share/upskayledd/models", model_dirs)


if __name__ == "__main__":
    unittest.main()
