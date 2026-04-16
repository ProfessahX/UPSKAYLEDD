from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[2] / "tools" / "run_real_world_validation.py"
    spec = importlib.util.spec_from_file_location("run_real_world_validation", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RealWorldValidationToolTests(unittest.TestCase):
    def test_normalize_encode_profile_id_handles_missing_values(self) -> None:
        module = _load_module()

        self.assertIsNone(module.normalize_encode_profile_id(None))
        self.assertIsNone(module.normalize_encode_profile_id("   "))
        self.assertEqual(module.normalize_encode_profile_id("hevc_balanced_archive"), "hevc_balanced_archive")

    def test_summarize_run_manifest_surfaces_size_warning_state(self) -> None:
        module = _load_module()
        summary = module.summarize_run_manifest(
            {
                "warnings": ["Output file is larger than the source file; review delivery settings if file size matters for this batch."],
                "fallbacks": [{"reason": "compatibility"}],
                "output_files": ["Z:/tmp/output.mp4"],
                "encode_settings": {
                    "execution_mode": "vapoursynth_canonical",
                    "input_size_bytes": 100,
                    "output_size_bytes": 130,
                    "size_ratio": 1.3,
                    "media_metrics": {"input": {"container_name": "matroska"}, "output": {"container_name": "mp4"}},
                    "conversion_guidance": ["Compatibility delivery favors easier playback and can trade size for device support."],
                },
            }
        )

        self.assertEqual(summary["execution_mode"], "vapoursynth_canonical")
        self.assertEqual(summary["warning_count"], 1)
        self.assertEqual(summary["fallback_count"], 1)
        self.assertTrue(summary["size_summary"]["oversized_delivery"])
        self.assertEqual(summary["size_summary"]["size_ratio"], 1.3)
        self.assertIn("media_metrics", summary)
        self.assertEqual(summary["media_metrics"]["output"]["container_name"], "mp4")
        self.assertEqual(len(summary["conversion_guidance"]), 1)

    def test_summarize_runtime_context_keeps_platform_warnings_and_actions(self) -> None:
        module = _load_module()
        summary = module.summarize_runtime_context(
            {
                "platform_summary": "Linux (WSL) · Python 3.12.3",
                "warnings": ["Canonical restoration stack is incomplete."],
            },
            [
                {
                    "action_id": "context:wsl_environment",
                    "title": "Decide on a Linux-side WSL runtime plan",
                }
            ],
        )

        self.assertEqual(summary["platform_summary"], "Linux (WSL) · Python 3.12.3")
        self.assertEqual(summary["warning_count"], 1)
        self.assertEqual(summary["action_count"], 1)
        self.assertEqual(summary["actions"][0]["action_id"], "context:wsl_environment")

    def test_summarize_validation_results_rolls_up_cadence_size_and_stream_risks(self) -> None:
        module = _load_module()
        summary = module.summarize_validation_results(
            [
                {
                    "inspection": {
                        "detected_source_class": "sd_live_action_ntsc",
                        "recommended_profile_id": "sd_live_action_ntsc",
                    },
                    "output_policy": {
                        "encode_profile_id": "hevc_balanced_archive",
                    },
                    "canonical_run": {
                        "execution_mode": "vapoursynth_canonical",
                        "error": "",
                        "size_summary": {"size_ratio": 0.48, "oversized_delivery": False},
                        "media_metrics": {
                            "comparison": {
                                "subtitle_codec_changed": False,
                                "subtitle_stream_delta": 0,
                                "chapter_delta": 0,
                            },
                            "input": {"video": {"avg_frame_rate_fps": 59.94}},
                            "output": {"video": {"avg_frame_rate_fps": 23.98}},
                        },
                    },
                    "degraded_run": {
                        "execution_mode": "ffmpeg_degraded",
                        "size_summary": {"size_ratio": 0.22, "oversized_delivery": False},
                        "media_metrics": {
                            "comparison": {
                                "subtitle_codec_changed": False,
                                "subtitle_stream_delta": 0,
                                "chapter_delta": 0,
                            }
                        },
                    },
                },
                {
                    "inspection": {
                        "detected_source_class": "sd_live_action_ntsc",
                        "recommended_profile_id": "sd_live_action_ntsc",
                    },
                    "output_policy": {
                        "encode_profile_id": "h264_compatibility_mp4",
                    },
                    "canonical_run": {
                        "execution_mode": "vapoursynth_canonical",
                        "error": "",
                        "size_summary": {"size_ratio": 1.18, "oversized_delivery": True},
                        "media_metrics": {
                            "comparison": {
                                "subtitle_codec_changed": True,
                                "subtitle_stream_delta": -1,
                                "chapter_delta": -1,
                            },
                            "input": {"video": {"avg_frame_rate_fps": 29.97}},
                            "output": {"video": {"avg_frame_rate_fps": 29.97}},
                        },
                    },
                    "degraded_run": {
                        "execution_mode": "ffmpeg_degraded",
                        "size_summary": {"size_ratio": 1.05, "oversized_delivery": False},
                        "media_metrics": {
                            "comparison": {
                                "subtitle_codec_changed": True,
                                "subtitle_stream_delta": -1,
                                "chapter_delta": 0,
                            }
                        },
                    },
                },
            ]
        )

        self.assertEqual(summary["source_count"], 2)
        self.assertEqual(summary["detected_source_classes"], ["sd_live_action_ntsc"])
        self.assertEqual(summary["recommended_profiles"], ["sd_live_action_ntsc"])
        self.assertEqual(summary["encode_profiles"], ["h264_compatibility_mp4", "hevc_balanced_archive"])
        self.assertEqual(summary["canonical"]["completed_runs"], 2)
        self.assertEqual(summary["canonical"]["cadence_change_count"], 1)
        self.assertEqual(summary["canonical"]["oversized_delivery_count"], 1)
        self.assertEqual(summary["canonical"]["subtitle_change_count"], 1)
        self.assertEqual(summary["canonical"]["stream_loss_count"], 1)
        self.assertEqual(summary["canonical"]["size_ratio"]["avg"], 0.83)
        self.assertTrue(any("changed frame rate" in item for item in summary["watch_items"]))
        self.assertTrue(any("larger than its source clip" in item for item in summary["watch_items"]))
        self.assertTrue(any("dropped subtitle or chapter streams" in item for item in summary["watch_items"]))

    def test_summarize_validation_results_handles_empty_and_bad_numeric_values(self) -> None:
        module = _load_module()
        summary = module.summarize_validation_results(
            [
                {
                    "inspection": {},
                    "output_policy": {},
                    "canonical_run": {
                        "execution_mode": "vapoursynth_canonical",
                        "size_summary": {"size_ratio": "not-a-number", "oversized_delivery": False},
                        "media_metrics": {
                            "input": {"video": {"avg_frame_rate_fps": "oops"}},
                            "output": {"video": {"avg_frame_rate_fps": "still-oops"}},
                        },
                    },
                    "degraded_run": {},
                }
            ]
        )

        self.assertEqual(summary["source_count"], 1)
        self.assertEqual(summary["canonical"]["completed_runs"], 1)
        self.assertEqual(summary["canonical"]["size_ratio"]["count"], 0)

    def test_file_stats_reports_missing_and_existing_paths(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            existing = temp_path / "sample.txt"
            existing.write_text("hello", encoding="utf-8")

            missing_stats = module.file_stats(temp_path / "missing.txt")
            existing_stats = module.file_stats(existing)

            self.assertFalse(missing_stats["exists"])
            self.assertEqual(existing_stats["size_bytes"], 5)
            self.assertTrue(existing_stats["exists"])


if __name__ == "__main__":
    unittest.main()
