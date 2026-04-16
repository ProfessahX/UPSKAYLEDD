from __future__ import annotations

import unittest

from upskayledd.config import load_app_config
from upskayledd.models import InspectionReport
from upskayledd.profile_resolver import ProfileResolver


class ProfileResolverTests(unittest.TestCase):
    def test_manual_review_uses_safe_profile(self) -> None:
        config = load_app_config()
        resolver = ProfileResolver(config)
        report = InspectionReport(
            source_path="Z:/tmp/source.mkv",
            container_name="matroska",
            duration_seconds=1.0,
            size_bytes=1,
            streams=[],
            chapter_count=0,
            source_fingerprint="abc",
            detected_source_class="manual_review",
            confidence=0.2,
            artifact_hints=[],
            recommended_profile_id="safe_review_required",
            manual_review_required=True,
            warnings=[],
            summary=[],
        )
        resolved = resolver.resolve_report(report)
        self.assertEqual(resolved.profile.id, "safe_review_required")
        self.assertTrue(resolved.warnings)


if __name__ == "__main__":
    unittest.main()

