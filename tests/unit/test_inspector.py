from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from upskayledd.config import load_app_config
from upskayledd.inspector import Inspector


class FakeFFprobe:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def is_available(self) -> bool:
        return True

    def probe(self, path: str | Path) -> dict:
        return self.payload


class MappingFFprobe(FakeFFprobe):
    def __init__(self, payloads: dict[str, dict]) -> None:
        self.payloads = payloads

    def probe(self, path: str | Path) -> dict:
        return self.payloads[Path(path).name]


class InspectorTests(unittest.TestCase):
    def test_detects_ntsc_sd_profile(self) -> None:
        config = load_app_config()
        payload = {
            "format": {"format_name": "matroska", "duration": "120.0", "size": "1000"},
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "mpeg2video",
                    "width": 720,
                    "height": 480,
                    "display_aspect_ratio": "4:3",
                    "avg_frame_rate": "30000/1001",
                    "field_order": "progressive",
                }
            ],
            "chapters": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "sample.mkv"
            sample.write_bytes(b"fake")
            report = Inspector(config, ffprobe=FakeFFprobe(payload)).inspect_path(sample)
        self.assertEqual(report.detected_source_class, "sd_live_action_ntsc")
        self.assertEqual(report.recommended_profile_id, "sd_live_action_ntsc")
        self.assertFalse(report.manual_review_required)

    def test_flags_manual_review_when_no_video_stream(self) -> None:
        config = load_app_config()
        payload = {"format": {"format_name": "matroska"}, "streams": [], "chapters": []}
        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "audio_only.mkv"
            sample.write_bytes(b"fake")
            report = Inspector(config, ffprobe=FakeFFprobe(payload)).inspect_path(sample)
        self.assertTrue(report.manual_review_required)
        self.assertEqual(report.recommended_profile_id, "safe_review_required")

    def test_detects_double_rate_ntsc_dvd_profile(self) -> None:
        config = load_app_config()
        payload = {
            "format": {"format_name": "matroska", "duration": "120.0", "size": "1000"},
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "mpeg2video",
                    "width": 720,
                    "height": 480,
                    "display_aspect_ratio": "4:3",
                    "avg_frame_rate": "19001/317",
                    "field_order": "progressive",
                }
            ],
            "chapters": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "sample_double_rate.mkv"
            sample.write_bytes(b"fake")
            report = Inspector(config, ffprobe=FakeFFprobe(payload)).inspect_path(sample)
        self.assertEqual(report.detected_source_class, "sd_live_action_ntsc")
        self.assertEqual(report.recommended_profile_id, "sd_live_action_ntsc")
        self.assertFalse(report.manual_review_required)
        self.assertIn("double_rate_ntsc_cadence_suspected", report.artifact_hints)

    def test_discovers_unknown_extension_when_ffprobe_confirms_video(self) -> None:
        config = load_app_config()
        payloads = {
            "episode01.unknown": {
                "format": {"format_name": "matroska"},
                "streams": [{"codec_type": "video", "codec_name": "mpeg2video", "width": 720, "height": 480}],
                "chapters": [],
            },
            "notes.txt": {
                "format": {"format_name": "tty"},
                "streams": [],
                "chapters": [],
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "episode01.unknown").write_bytes(b"video")
            (root / "notes.txt").write_text("not video", encoding="utf-8")
            files = Inspector(config, ffprobe=MappingFFprobe(payloads)).discover_media_files(root)
        self.assertEqual([path.name for path in files], ["episode01.unknown"])

    def test_discovers_extensionless_video_when_enabled(self) -> None:
        config = load_app_config()
        payloads = {
            "episode01": {
                "format": {"format_name": "matroska"},
                "streams": [{"codec_type": "video", "codec_name": "mpeg2video", "width": 720, "height": 480}],
                "chapters": [],
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "episode01").write_bytes(b"video")
            files = Inspector(config, ffprobe=MappingFFprobe(payloads)).discover_media_files(root)
        self.assertEqual([path.name for path in files], ["episode01"])


if __name__ == "__main__":
    unittest.main()
