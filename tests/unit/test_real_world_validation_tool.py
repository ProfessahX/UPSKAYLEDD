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
