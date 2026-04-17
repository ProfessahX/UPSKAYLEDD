from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESKTOP_APPS = ROOT / "apps" / "desktop"
if str(DESKTOP_APPS) not in sys.path:
    sys.path.insert(0, str(DESKTOP_APPS))

from pyside_app.ui_config import load_ui_config
from pyside_app.window import (
    build_dashboard_focus_text,
    build_media_change_highlights,
    build_media_metrics_snapshot,
    build_result_review_read,
    build_run_summary,
)


def sample_run_payload() -> dict[str, object]:
    return {
        "actual_backend": {"backend_id": "vulkan_ml"},
        "output_files": [str(ROOT / "runtime" / "output" / "episode01.mkv")],
        "encode_settings": {
            "execution_mode": "vapoursynth_canonical",
            "input_size_bytes": 2000,
            "output_size_bytes": 1500,
            "size_ratio": 0.75,
            "media_metrics": {
                "input": {
                    "container_name": "matroska",
                    "duration_seconds": 10.0,
                    "size_bytes": 2000,
                    "overall_bitrate_bps": 5000000,
                    "chapter_count": 2,
                    "video": {
                        "codec_name": "mpeg2video",
                        "width": 720,
                        "height": 480,
                        "display_aspect_ratio": "4:3",
                        "avg_frame_rate_fps": 29.97,
                        "field_order": "tt",
                        "bit_rate_bps": 4000000,
                        "pixel_format": "yuv420p",
                    },
                    "audio": {"stream_count": 2, "codec_names": ["ac3"], "languages": ["eng"], "max_channels": 6},
                    "subtitle": {"stream_count": 1, "codec_names": ["dvd_subtitle"], "languages": ["eng"]},
                },
                "output": {
                    "container_name": "matroska",
                    "duration_seconds": 10.0,
                    "size_bytes": 1500,
                    "overall_bitrate_bps": 2500000,
                    "chapter_count": 2,
                    "video": {
                        "codec_name": "hevc",
                        "width": 1440,
                        "height": 1080,
                        "display_aspect_ratio": "4:3",
                        "avg_frame_rate_fps": 23.98,
                        "field_order": "progressive",
                        "bit_rate_bps": 2000000,
                        "pixel_format": "yuv420p10le",
                    },
                    "audio": {"stream_count": 2, "codec_names": ["aac"], "languages": ["eng"], "max_channels": 2},
                    "subtitle": {"stream_count": 1, "codec_names": ["mov_text"], "languages": ["eng"]},
                },
                "comparison": {
                    "size_ratio": 0.75,
                    "overall_bitrate_ratio": 0.5,
                    "resolution_scale": 4.5,
                    "container_changed": False,
                    "video_codec_changed": True,
                    "audio_codec_changed": True,
                    "subtitle_codec_changed": True,
                    "subtitle_stream_delta": 0,
                    "chapter_delta": 0,
                },
            },
            "conversion_guidance": [
                "Output landed smaller than the source sample with the current delivery settings.",
                "Audio changed from ac3 to aac; this usually improves compatibility rather than preserving bit-perfect audio.",
            ],
        },
        "stream_outcomes": [
            {"stream_type": "audio", "action": "preserve", "reason": "ffmpeg_copy"},
            {"stream_type": "subtitle", "action": "drop", "reason": "ffmpeg_subtitle_copy_failed"},
        ],
        "fallbacks": ["subtitle_copy_failed_retry_without_subtitles"],
        "warnings": ["Subtitle stream could not be preserved on the first pass."],
    }


class DesktopWindowHelperTests(unittest.TestCase):
    def test_build_dashboard_focus_text_tracks_running_and_completed_states(self) -> None:
        dashboard_copy = load_ui_config().copy.dashboard

        running_focus = build_dashboard_focus_text(
            {
                "focus_job": {
                    "source_name": "episode07.mkv",
                    "status": "running",
                    "progress": 0.42,
                }
            },
            dashboard_copy,
        )
        completed_focus = build_dashboard_focus_text(
            {
                "focus_job": {
                    "source_name": "episode08.mkv",
                    "status": "completed",
                    "progress": 1.0,
                }
            },
            dashboard_copy,
        )

        self.assertIn("episode07.mkv is running at 42%", running_focus)
        self.assertIn("episode08.mkv completed and is ready for result review.", completed_focus)

    def test_build_run_summary_surfaces_backend_streams_and_fallbacks(self) -> None:
        summary = build_run_summary(sample_run_payload())

        self.assertIn("Execution mode: vapoursynth_canonical", summary)
        self.assertIn("Backend: vulkan_ml", summary)
        self.assertIn("Primary output: episode01.mkv", summary)
        self.assertIn("1,500 bytes out vs 2,000 bytes in (0.75x)", summary)
        self.assertIn("Media metrics:", summary)
        self.assertIn("Input: MATROSKA", summary)
        self.assertIn("Output: MATROSKA", summary)
        self.assertIn("Video codec changed during delivery.", summary)
        self.assertIn("Conversion guidance:", summary)
        self.assertIn("Audio changed from ac3 to aac", summary)
        self.assertIn("audio: preserve", summary)
        self.assertIn("subtitle: drop", summary)
        self.assertIn("subtitle copy failed retry without subtitles", summary)
        self.assertIn("Subtitle stream could not be preserved", summary)

    def test_build_media_metrics_snapshot_surfaces_before_after_rows_and_guidance(self) -> None:
        snapshot = build_media_metrics_snapshot(sample_run_payload())

        rows = snapshot["rows"]
        self.assertTrue(rows)
        self.assertIn(("Container", "MATROSKA", "MATROSKA"), rows)
        self.assertTrue(any(row[0] == "File size" and "2,000 bytes" in row[1] and "1,500 bytes" in row[2] for row in rows))
        self.assertTrue(any(row[0] == "Video" and "mpeg2video" in row[1] and "hevc" in row[2] for row in rows))
        self.assertTrue(any(row[0] == "Subtitles" and "dvd_subtitle" in row[1] and "mov_text" in row[2] for row in rows))
        self.assertIn(
            "Output landed smaller than the source sample with the current delivery settings.",
            snapshot["guidance"],
        )

    def test_build_media_change_highlights_surfaces_size_resolution_cadence_and_stream_state(self) -> None:
        highlights = build_media_change_highlights(sample_run_payload())

        self.assertEqual(4, len(highlights))
        self.assertEqual("Size", highlights[0]["title"])
        self.assertEqual("75% of source", highlights[0]["value"])
        self.assertEqual("Resolution", highlights[1]["title"])
        self.assertIn("720x480 -> 1440x1080", highlights[1]["value"])
        self.assertEqual("Cadence", highlights[2]["title"])
        self.assertIn("29.97 -> 23.98 fps", highlights[2]["value"])
        self.assertEqual("warning", highlights[2]["tone"])
        self.assertEqual("Streams", highlights[3]["title"])
        self.assertEqual("Delivery changed", highlights[3]["value"])

    def test_build_result_review_read_flags_stream_loss_as_danger(self) -> None:
        payload = copy.deepcopy(sample_run_payload())
        payload["encode_settings"]["media_metrics"]["comparison"]["subtitle_stream_delta"] = -1

        review_read = build_result_review_read(payload)

        self.assertEqual("danger", review_read["tone"])
        self.assertIn("trust", review_read["headline"].lower())
        self.assertTrue(any("mkv archive lane" in step.lower() for step in review_read["next_steps"]))

    def test_build_result_review_read_flags_cadence_shift_as_warning(self) -> None:
        review_read = build_result_review_read(sample_run_payload())

        self.assertEqual("warning", review_read["tone"])
        self.assertIn("motion", review_read["headline"].lower())
        self.assertTrue(any("side-by-side" in step.lower() or "a/b" in step.lower() for step in review_read["next_steps"]))

    def test_build_result_review_read_marks_aligned_output_as_success(self) -> None:
        payload = copy.deepcopy(sample_run_payload())
        comparison = payload["encode_settings"]["media_metrics"]["comparison"]
        input_video = payload["encode_settings"]["media_metrics"]["input"]["video"]
        output_video = payload["encode_settings"]["media_metrics"]["output"]["video"]
        comparison["audio_codec_changed"] = False
        comparison["subtitle_codec_changed"] = False
        comparison["size_ratio"] = 0.92
        input_video["avg_frame_rate_fps"] = 23.98
        output_video["avg_frame_rate_fps"] = 23.98
        payload["encode_settings"]["conversion_guidance"] = [
            "Output landed smaller than the source sample with the current delivery settings."
        ]
        payload["warnings"] = []

        review_read = build_result_review_read(payload)

        self.assertEqual("success", review_read["tone"])
        self.assertIn("aligned", review_read["headline"].lower())
        self.assertTrue(any("spot-check" in step.lower() or "looks good" in step.lower() for step in review_read["next_steps"]))


if __name__ == "__main__":
    unittest.main()
