from __future__ import annotations

import unittest

from upskayledd.core.errors import CompatibilityError
from upskayledd.models import ProjectManifest, ensure_compatible_schema


class ModelTests(unittest.TestCase):
    def test_schema_compatibility_accepts_current_version(self) -> None:
        ensure_compatible_schema("project_manifest", "0.1")

    def test_schema_compatibility_rejects_future_version(self) -> None:
        with self.assertRaises(CompatibilityError):
            ensure_compatible_schema("project_manifest", "0.9")

    def test_project_manifest_round_trip(self) -> None:
        manifest = ProjectManifest(
            project_id="proj",
            created_at="2026-04-14T00:00:00+00:00",
            source_files=["a.mkv"],
            selected_profile_id="safe_review_required",
            output_policy={"container": "mkv"},
            resolved_pipeline_stages=[],
            backend_preferences=["planning_only"],
            model_preferences=[],
            batch_settings={},
            per_file_overrides={},
            custom_model_paths=[],
            hook_references=[],
            warnings=[],
        )
        restored = ProjectManifest.from_dict(manifest.to_dict())
        self.assertEqual(restored.project_id, "proj")
        self.assertEqual(restored.schema_version, "0.1")


if __name__ == "__main__":
    unittest.main()

