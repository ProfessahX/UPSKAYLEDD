from __future__ import annotations

import unittest

from upskayledd.config import load_app_config
from upskayledd.model_registry import ModelRegistry
from upskayledd.models import InspectionReport, StreamInfo
from upskayledd.pipeline_builder import PipelineBuilder


class PipelineBuilderTests(unittest.TestCase):
    def test_mp4_output_warns_when_source_has_image_based_subtitles(self) -> None:
        config = load_app_config()
        builder = PipelineBuilder(config, ModelRegistry(config))
        profile = config.profile_by_id("sd_live_action_ntsc")
        report = InspectionReport(
            source_path="Z:/sample.mkv",
            container_name="matroska",
            duration_seconds=10.0,
            size_bytes=1024,
            streams=[
                StreamInfo(index=0, codec_type="video", codec_name="mpeg2video", width=720, height=480),
                StreamInfo(index=1, codec_type="subtitle", codec_name="dvd_subtitle"),
            ],
            chapter_count=1,
            source_fingerprint="abcd1234efgh5678",
            detected_source_class="sd_live_action_ntsc",
            confidence=0.8,
            artifact_hints=[],
            recommended_profile_id="sd_live_action_ntsc",
            manual_review_required=False,
            warnings=[],
            summary=[],
        )

        manifest = builder.build_manifest(
            reports=[report],
            profile=profile,
            output_policy_overrides={"encode_profile_id": "h264_compatibility_mp4"},
        )

        warning_blob = "\n".join(manifest.warnings)
        self.assertIn("MP4 delivery may drop subtitle codecs", warning_blob)
        self.assertIn("dvd_subtitle", warning_blob)


if __name__ == "__main__":
    unittest.main()
