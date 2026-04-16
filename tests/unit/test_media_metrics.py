from __future__ import annotations

import unittest

from upskayledd.config import load_app_config
from upskayledd.media_metrics import compare_media_metrics, summarize_media_probe


class MediaMetricsTests(unittest.TestCase):
    def test_summarize_media_probe_extracts_core_stream_metrics(self) -> None:
        payload = {
            "format": {
                "format_name": "matroska,webm",
                "duration": "10.0",
                "size": "2048",
                "bit_rate": "5000000",
            },
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "mpeg2video",
                    "width": 720,
                    "height": 480,
                    "display_aspect_ratio": "4:3",
                    "avg_frame_rate": "30000/1001",
                    "field_order": "tt",
                    "pix_fmt": "yuv420p",
                    "bit_rate": "4000000",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "ac3",
                    "channels": 6,
                    "tags": {"language": "eng"},
                },
                {
                    "codec_type": "subtitle",
                    "codec_name": "dvd_subtitle",
                    "tags": {"language": "eng"},
                },
            ],
            "chapters": [{}, {}],
        }

        metrics = summarize_media_probe(payload)

        self.assertEqual(metrics["container_name"], "matroska")
        self.assertEqual(metrics["stream_counts"]["audio"], 1)
        self.assertEqual(metrics["chapter_count"], 2)
        self.assertEqual(metrics["video"]["codec_name"], "mpeg2video")
        self.assertAlmostEqual(metrics["video"]["avg_frame_rate_fps"], 29.97, places=2)

    def test_compare_media_metrics_builds_guidance_for_size_and_codec_changes(self) -> None:
        config = load_app_config().conversion_guidance
        input_metrics = {
            "container_name": "matroska",
            "size_bytes": 2000,
            "overall_bitrate_bps": 5000000,
            "chapter_count": 2,
            "video": {"codec_name": "mpeg2video", "width": 720, "height": 480, "avg_frame_rate_fps": 29.97},
            "audio": {"stream_count": 1, "codec_names": ["ac3"]},
            "subtitle": {"stream_count": 1, "codec_names": ["dvd_subtitle"]},
        }
        output_metrics = {
            "container_name": "mp4",
            "size_bytes": 2600,
            "overall_bitrate_bps": 3500000,
            "chapter_count": 1,
            "video": {"codec_name": "h264", "width": 1440, "height": 1080, "avg_frame_rate_fps": 23.98},
            "audio": {"stream_count": 1, "codec_names": ["aac"]},
            "subtitle": {"stream_count": 0, "codec_names": []},
        }

        comparison = compare_media_metrics(
            input_metrics,
            output_metrics,
            encode_profile_id="h264_compatibility_mp4",
            preserve_chapters=True,
            config=config,
        )

        self.assertTrue(comparison["container_changed"])
        self.assertTrue(comparison["video_codec_changed"])
        self.assertTrue(comparison["audio_codec_changed"])
        self.assertLess(comparison["chapter_delta"], 0)
        guidance = "\n".join(comparison["guidance"])
        self.assertIn("Compatibility delivery favors easier playback", guidance)
        self.assertIn("Output grew larger than the source sample", guidance)
        self.assertIn("Audio changed from ac3 to aac", guidance)


if __name__ == "__main__":
    unittest.main()
