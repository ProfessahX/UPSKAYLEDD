from __future__ import annotations

import unittest

from upskayledd.config import load_app_config
from upskayledd.delivery_guidance import DeliveryGuidanceBuilder
from upskayledd.models import InspectionReport, StreamInfo


def make_report(
    *,
    source_path: str,
    recommended_profile_id: str = "sd_live_action_ntsc",
    manual_review_required: bool = False,
    subtitle_codec: str = "dvd_subtitle",
) -> InspectionReport:
    return InspectionReport(
        source_path=source_path,
        container_name="matroska",
        duration_seconds=10.0,
        size_bytes=6_700_000,
        streams=[
            StreamInfo(
                index=0,
                codec_type="video",
                codec_name="mpeg2video",
                width=720,
                height=480,
                sample_aspect_ratio="8:9",
                display_aspect_ratio="4:3",
                avg_frame_rate="19001/317",
                field_order="progressive",
            ),
            StreamInfo(
                index=1,
                codec_type="audio",
                codec_name="ac3",
                channels=6,
            ),
            StreamInfo(
                index=2,
                codec_type="subtitle",
                codec_name=subtitle_codec,
                language="eng",
            ),
        ],
        chapter_count=2,
        source_fingerprint=f"fingerprint-{source_path}",
        detected_source_class="sd_live_action_ntsc",
        confidence=0.74,
        artifact_hints=["telecine"],
        recommended_profile_id=recommended_profile_id,
        manual_review_required=manual_review_required,
        warnings=[],
        summary=["Representative NTSC DVD-era source."],
    )


class DeliveryGuidanceTests(unittest.TestCase):
    def test_archive_lane_guidance_prefers_subtitle_and_audio_preservation(self) -> None:
        builder = DeliveryGuidanceBuilder(load_app_config())
        report = make_report(source_path="episode01.mkv")

        payload = builder.build(
            [report],
            {
                "encode_profile_id": "hevc_balanced_archive",
                "container": "mkv",
                "width": 1440,
                "height": 1080,
                "audio_codec": "copy",
                "subtitle_codec": "copy",
                "preserve_chapters": True,
            },
        )

        self.assertEqual(payload["selected_profile_id"], "hevc_balanced_archive")
        selected_blob = "\n".join(payload["selected_messages"])
        selected_facts = [item["label"] for item in payload["selected_facts"]]
        self.assertIn("preservation-minded batches", selected_blob)
        self.assertIn("Archive-first lane", selected_facts)
        self.assertIn("Usually smaller than source", selected_facts)
        self.assertIn("Keeps source audio", selected_facts)
        self.assertIn("Keeps source subtitles", selected_facts)
        self.assertIn("image-based subtitles", selected_blob)
        self.assertIn("up to 6 audio channels", selected_blob)
        self.assertIn("1440x1080", selected_blob)
        self.assertIn("Chapters stay enabled", selected_blob)

        compatibility = next(item for item in payload["alternative_profiles"] if item["id"] == "h264_compatibility_mp4")
        compatibility_blob = "\n".join(compatibility["messages"])
        compatibility_facts = [item["label"] for item in compatibility["facts"]]
        self.assertEqual(compatibility["status"], "watch")
        self.assertIn("Compatibility-first lane", compatibility_facts)
        self.assertIn("May grow for compatibility", compatibility_facts)
        self.assertIn("Transcodes audio to aac", compatibility_facts)
        self.assertIn("Image subtitle risk", compatibility_facts)
        self.assertIn("picky devices", compatibility_blob)
        self.assertIn("may convert or drop", compatibility_blob)
        self.assertIn("transcodes audio to aac", compatibility_blob.lower())

    def test_batch_outlier_guidance_surfaces_on_selected_lane(self) -> None:
        builder = DeliveryGuidanceBuilder(load_app_config())
        reports = [
            make_report(source_path="episode01.mkv", recommended_profile_id="sd_live_action_ntsc"),
            make_report(
                source_path="episode02.mkv",
                recommended_profile_id="safe_review_required",
                manual_review_required=True,
                subtitle_codec="subrip",
            ),
        ]

        payload = builder.build(
            reports,
            {
                "encode_profile_id": "hevc_smaller_archive",
                "container": "mkv",
                "width": 1440,
                "height": 1080,
                "audio_codec": "copy",
                "subtitle_codec": "copy",
                "preserve_chapters": True,
            },
        )

        selected_blob = "\n".join(payload["selected_messages"])
        self.assertIn("smaller files", selected_blob)
        self.assertIn("flagged episode", selected_blob)

    def test_unknown_selected_encode_profile_falls_back_to_default_lane(self) -> None:
        builder = DeliveryGuidanceBuilder(load_app_config())
        report = make_report(source_path="episode01.mkv")

        payload = builder.build(
            [report],
            {
                "encode_profile_id": "  stale_profile_id  ",
                "container": "mkv",
                "width": 1440,
                "height": 1080,
                "audio_codec": "copy",
                "subtitle_codec": "copy",
                "preserve_chapters": True,
            },
        )

        self.assertEqual(payload["selected_profile_id"], "hevc_balanced_archive")
        self.assertEqual(payload["selected_profile_label"], "HEVC Balanced Archive")

    def test_selected_encode_profile_id_is_trimmed_before_lookup(self) -> None:
        builder = DeliveryGuidanceBuilder(load_app_config())
        report = make_report(source_path="episode01.mkv")

        payload = builder.build(
            [report],
            {
                "encode_profile_id": "  hevc_balanced_archive  ",
                "container": "mkv",
                "width": 1440,
                "height": 1080,
                "audio_codec": "copy",
                "subtitle_codec": "copy",
                "preserve_chapters": True,
            },
        )

        self.assertEqual(payload["selected_profile_id"], "hevc_balanced_archive")
        self.assertEqual(payload["selected_profile_label"], "HEVC Balanced Archive")

    def test_selected_compatibility_lane_preserves_watch_status(self) -> None:
        builder = DeliveryGuidanceBuilder(load_app_config())
        report = make_report(source_path="episode01.mkv")

        payload = builder.build(
            [report],
            {
                "encode_profile_id": "h264_compatibility_mp4",
                "container": "mp4",
                "width": 1440,
                "height": 1080,
                "audio_codec": "aac",
                "subtitle_codec": "mov_text",
                "preserve_chapters": True,
            },
        )

        self.assertEqual(payload["selected_profile_id"], "h264_compatibility_mp4")
        self.assertEqual(payload["selected_status"], "watch")
        self.assertTrue(payload["selected_is_selected"])
        self.assertIn(
            "Compatibility-first lane",
            [item["label"] for item in payload["selected_facts"]],
        )


if __name__ == "__main__":
    unittest.main()
