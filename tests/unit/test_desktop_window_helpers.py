from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESKTOP_APPS = ROOT / "apps" / "desktop"
if str(DESKTOP_APPS) not in sys.path:
    sys.path.insert(0, str(DESKTOP_APPS))

from pyside_app.ui_config import load_ui_config
from pyside_app.window import build_dashboard_focus_text, build_run_summary


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
        summary = build_run_summary(
            {
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
        )

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


if __name__ == "__main__":
    unittest.main()
