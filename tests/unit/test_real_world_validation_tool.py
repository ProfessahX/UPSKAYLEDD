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

    def test_sample_copy_fallback_reasons_flags_cadence_and_stream_loss(self) -> None:
        module = _load_module()
        reasons = module.sample_copy_fallback_reasons(
            {
                "audio": {"stream_count": 1},
                "subtitle": {"stream_count": 2},
                "video": {"avg_frame_rate_fps": 59.94},
            },
            {
                "audio": {"stream_count": 1},
                "subtitle": {"stream_count": 1},
                "video": {"avg_frame_rate_fps": 29.97},
            },
            sample_pipeline_fps=28.98,
        )

        self.assertTrue(any("cadence" in reason for reason in reasons))
        self.assertTrue(any("subtitle" in reason for reason in reasons))

    def test_extract_vspipe_fps_parses_info_output(self) -> None:
        module = _load_module()

        self.assertEqual(module._extract_vspipe_fps("Width: 1440\nFPS: 14696/503 (29.217 fps)\n"), 14696 / 503)
        self.assertIsNone(module._extract_vspipe_fps("Width: 1440\nFrames: 240\n"))

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
                    "media_metrics": {
                        "comparison": {
                            "size_ratio": 1.3,
                            "container_changed": True,
                            "guidance": ["Compatibility delivery favors easier playback and can trade size for device support."],
                        },
                        "input": {
                            "container_name": "matroska",
                            "duration_seconds": 42.0,
                            "size_bytes": 100,
                            "overall_bitrate_bps": 1_200_000,
                            "chapter_count": 8,
                            "video": {
                                "codec_name": "mpeg2video",
                                "width": 720,
                                "height": 480,
                                "display_aspect_ratio": "4:3",
                                "avg_frame_rate_fps": 29.97,
                                "field_order": "tt",
                            },
                            "audio": {"stream_count": 1, "codec_names": ["ac3"], "max_channels": 6},
                            "subtitle": {"stream_count": 2, "codec_names": ["dvd_subtitle"]},
                        },
                        "output": {
                            "container_name": "mp4",
                            "duration_seconds": 42.0,
                            "size_bytes": 130,
                            "overall_bitrate_bps": 900_000,
                            "chapter_count": 0,
                            "video": {
                                "codec_name": "h264",
                                "width": 960,
                                "height": 720,
                                "display_aspect_ratio": "4:3",
                                "avg_frame_rate_fps": 29.97,
                                "field_order": "progressive",
                            },
                            "audio": {"stream_count": 1, "codec_names": ["aac"], "max_channels": 2},
                            "subtitle": {"stream_count": 1, "codec_names": ["mov_text"]},
                        },
                    },
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
        self.assertEqual(summary["metric_overview"]["input"]["container"], "MATROSKA")
        self.assertEqual(summary["metric_overview"]["output"]["container"], "MP4")
        self.assertTrue(any("Size ratio" in line for line in summary["metric_overview"]["comparison_highlights"]))
        self.assertEqual(summary["metric_overview"]["guidance"][0], summary["conversion_guidance"][0])

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
                                "guidance": ["Archive lane stayed smaller than the source clip."],
                            },
                            "input": {
                                "container_name": "mpeg",
                                "video": {"avg_frame_rate_fps": 59.94, "codec_name": "mpeg2video", "width": 720, "height": 480},
                            },
                            "output": {
                                "container_name": "matroska",
                                "video": {"avg_frame_rate_fps": 23.98, "codec_name": "hevc", "width": 1440, "height": 1080},
                            },
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
                    "sample_clip_cadence": {
                        "probe_frame_rate_fps": 59.94,
                        "decode_frame_rate_fps": 23.98,
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
                                "guidance": ["Compatibility delivery favors easier playback and can trade size for device support."],
                            },
                            "input": {
                                "container_name": "mpeg",
                                "video": {"avg_frame_rate_fps": 29.97, "codec_name": "mpeg2video", "width": 720, "height": 480},
                            },
                            "output": {
                                "container_name": "mp4",
                                "video": {"avg_frame_rate_fps": 29.97, "codec_name": "h264", "width": 1440, "height": 1080},
                            },
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
        self.assertEqual(summary["canonical"]["decode_cadence_mismatch_count"], 1)
        self.assertEqual(summary["degraded"]["decode_cadence_mismatch_count"], 0)
        self.assertEqual(summary["canonical"]["oversized_delivery_count"], 1)
        self.assertEqual(summary["canonical"]["subtitle_change_count"], 1)
        self.assertEqual(summary["canonical"]["stream_loss_count"], 1)
        self.assertEqual(summary["canonical"]["size_ratio"]["avg"], 0.83)
        self.assertEqual(summary["media_rollup"]["source_containers"], {"mpeg": 2})
        self.assertEqual(summary["media_rollup"]["source_video_codecs"], {"mpeg2video": 2})
        self.assertEqual(summary["canonical"]["output_containers"], {"matroska": 1, "mp4": 1})
        self.assertEqual(summary["canonical"]["output_video_codecs"], {"h264": 1, "hevc": 1})
        self.assertEqual(summary["canonical"]["output_resolutions"], {"1440x1080": 2})
        self.assertEqual(summary["canonical"]["output_frame_rates"], {"23.98 fps": 1, "29.97 fps": 1})
        self.assertEqual(summary["canonical"]["probe_frame_rates"], {"59.94 fps": 1})
        self.assertEqual(summary["canonical"]["decode_frame_rates"], {"23.98 fps": 1})
        self.assertEqual(
            summary["media_rollup"]["guidance_messages"],
            {
                "Archive lane stayed smaller than the source clip.": 1,
                "Compatibility delivery favors easier playback and can trade size for device support.": 1,
            },
        )
        self.assertTrue(any("changed frame rate" in item for item in summary["watch_items"]))
        self.assertTrue(any("decode-aware interpretation" in item for item in summary["watch_items"]))
        self.assertTrue(any("mixed frame-rate groups" in item for item in summary["watch_items"]))
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
                            "comparison": {
                                "subtitle_stream_delta": "oops",
                                "chapter_delta": "still-oops",
                            },
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
        self.assertEqual(summary["canonical"]["subtitle_change_count"], 0)
        self.assertEqual(summary["canonical"]["stream_loss_count"], 0)

    def test_summarize_validation_results_distinguishes_decode_aligned_mixed_groups(self) -> None:
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
                        "size_summary": {"size_ratio": 0.8, "oversized_delivery": False},
                        "media_metrics": {
                            "comparison": {"subtitle_stream_delta": 0, "chapter_delta": 0},
                            "input": {"video": {"avg_frame_rate_fps": 59.94}},
                            "output": {
                                "container_name": "matroska",
                                "video": {
                                    "avg_frame_rate_fps": 23.98,
                                    "codec_name": "hevc",
                                    "width": 1440,
                                    "height": 1080,
                                },
                            },
                        },
                    },
                    "sample_clip_cadence": {
                        "probe_frame_rate_fps": 59.94,
                        "decode_frame_rate_fps": 23.98,
                    },
                },
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
                        "size_summary": {"size_ratio": 0.82, "oversized_delivery": False},
                        "media_metrics": {
                            "comparison": {"subtitle_stream_delta": 0, "chapter_delta": 0},
                            "input": {"video": {"avg_frame_rate_fps": 59.94}},
                            "output": {
                                "container_name": "matroska",
                                "video": {
                                    "avg_frame_rate_fps": 29.97,
                                    "codec_name": "hevc",
                                    "width": 1440,
                                    "height": 1080,
                                },
                            },
                        },
                    },
                    "sample_clip_cadence": {
                        "probe_frame_rate_fps": 59.94,
                        "decode_frame_rate_fps": 29.97,
                    },
                },
            ]
        )

        self.assertEqual(summary["canonical"]["output_frame_rates"], {"23.98 fps": 1, "29.97 fps": 1})
        self.assertEqual(summary["canonical"]["probe_frame_rates"], {"59.94 fps": 2})
        self.assertEqual(summary["canonical"]["decode_frame_rates"], {"23.98 fps": 1, "29.97 fps": 1})
        self.assertTrue(any("match the sampled decode cadence buckets" in item for item in summary["watch_items"]))
        self.assertFalse(
            any(
                item == "Canonical sampled outputs landed in mixed frame-rate groups; verify whether batch cadence expectations actually match the sampled decode cadence before a long run."
                for item in summary["watch_items"]
            )
        )

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

    def test_select_sources_prefers_flagged_and_representative_batch_samples(self) -> None:
        module = _load_module()

        class _FakeInspector:
            def __init__(self, paths):
                self._paths = list(paths)

            def discover_media_files(self, target):
                return list(self._paths)

        class _FakeService:
            def __init__(self, paths, payload):
                self.inspector = _FakeInspector(paths)
                self._payload = payload

            def recommend_target(self, target, output_policy_overrides=None):
                return dict(self._payload)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            alpha = root / "alpha.mkv"
            beta = root / "beta.mkv"
            gamma = root / "gamma.mkv"
            delta = root / "delta.mkv"
            for path in [alpha, beta, gamma, delta]:
                path.write_text(path.stem, encoding="utf-8")

            reports = [
                module.InspectionReport(
                    source_path=str(alpha.resolve()),
                    container_name="matroska",
                    duration_seconds=2700.0,
                    size_bytes=900,
                    streams=[],
                    chapter_count=0,
                    source_fingerprint="alpha",
                    detected_source_class="sd_live_action_ntsc",
                    confidence=0.94,
                    artifact_hints=[],
                    recommended_profile_id="sd_live_action_ntsc",
                    manual_review_required=False,
                    warnings=[],
                    summary=[],
                ).to_dict(),
                module.InspectionReport(
                    source_path=str(beta.resolve()),
                    container_name="matroska",
                    duration_seconds=2750.0,
                    size_bytes=1200,
                    streams=[],
                    chapter_count=0,
                    source_fingerprint="beta",
                    detected_source_class="manual_review",
                    confidence=0.31,
                    artifact_hints=["mixed_cadence"],
                    recommended_profile_id="safe_review_required",
                    manual_review_required=True,
                    warnings=["Manual review strongly recommended."],
                    summary=[],
                ).to_dict(),
                module.InspectionReport(
                    source_path=str(gamma.resolve()),
                    container_name="matroska",
                    duration_seconds=2600.0,
                    size_bytes=1500,
                    streams=[],
                    chapter_count=0,
                    source_fingerprint="gamma",
                    detected_source_class="sd_live_action_pal",
                    confidence=0.72,
                    artifact_hints=[],
                    recommended_profile_id="sd_live_action_pal",
                    manual_review_required=False,
                    warnings=["Profile outlier."],
                    summary=[],
                ).to_dict(),
                module.InspectionReport(
                    source_path=str(delta.resolve()),
                    container_name="matroska",
                    duration_seconds=2800.0,
                    size_bytes=1800,
                    streams=[],
                    chapter_count=0,
                    source_fingerprint="delta",
                    detected_source_class="sd_live_action_ntsc",
                    confidence=0.91,
                    artifact_hints=[],
                    recommended_profile_id="sd_live_action_ntsc",
                    manual_review_required=False,
                    warnings=[],
                    summary=[],
                ).to_dict(),
            ]
            fake_service = _FakeService(
                [alpha, beta, gamma, delta],
                {
                    "inspection_reports": reports,
                    "batch_summary": {
                        "dominant_profile": "sd_live_action_ntsc",
                        "outlier_sources": [str(gamma.resolve())],
                    },
                },
            )

            selected, summary = module.select_sources(fake_service, root, 3)

            self.assertEqual([path.name for path in selected], ["beta.mkv", "gamma.mkv", "alpha.mkv"])
            self.assertEqual(summary["strategy"], "representative_batch_sampling")
            self.assertEqual(summary["dominant_profile"], "sd_live_action_ntsc")
            self.assertEqual(summary["manual_review_count"], 1)
            self.assertEqual(summary["outlier_count"], 2)
            self.assertIn("manual review candidate", summary["chosen_sources"][0]["reasons"])
            self.assertIn("profile outlier", summary["chosen_sources"][1]["reasons"])
            self.assertIn("dominant profile representative", summary["chosen_sources"][2]["reasons"])


if __name__ == "__main__":
    unittest.main()
