from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from upskayledd.config import load_app_config
from upskayledd.models import ComparisonMode
from upskayledd.preview_engine import PreviewEngine
from upskayledd.project_store import ProjectStore


class FakeFFmpeg:
    def is_available(self) -> bool:
        return True

    def extract_preview_clip(
        self,
        source_path: str,
        output_path: str,
        start_seconds: float,
        duration_seconds: float,
        video_filter: str | None = None,
    ) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"clip")
        return output


class PreviewEngineTests(unittest.TestCase):
    def test_prepare_preview_writes_metadata_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_app_config()
            db_path = Path(temp_dir) / "state.sqlite3"
            store = ProjectStore(db_path)
            source = Path(temp_dir) / "source.mkv"
            source.write_bytes(b"video")
            engine = PreviewEngine(config, store, ffmpeg=FakeFFmpeg())
            request = engine.create_request(
                source_path=str(source),
                stage_id="cleanup",
                comparison_mode=ComparisonMode.SLIDER_WIPE,
            )
            result = engine.prepare_preview(request)
            cached = store.get_preview_cache(result.cache_key)
            self.assertEqual(result.fidelity_mode.value, "approximate")
            self.assertIsNotNone(cached)
            self.assertTrue(Path(result.metadata_path).exists())
            self.assertTrue(result.artifact_paths)
            self.assertIn("source", result.comparison_artifacts)
            self.assertIn("processed", result.comparison_artifacts)

    def test_prepare_preview_rerenders_when_cached_artifact_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_app_config()
            db_path = Path(temp_dir) / "state.sqlite3"
            store = ProjectStore(db_path)
            source = Path(temp_dir) / "source.mkv"
            source.write_bytes(b"video")
            engine = PreviewEngine(config, store, ffmpeg=FakeFFmpeg())
            request = engine.create_request(
                source_path=str(source),
                stage_id="cleanup",
                comparison_mode=ComparisonMode.SLIDER_WIPE,
            )
            first = engine.prepare_preview(request)
            Path(first.comparison_artifacts["processed"]).unlink()

            second = engine.prepare_preview(request)

            self.assertFalse(second.cache_hit)
            self.assertTrue(any("rerendered" in warning for warning in second.warnings))
            self.assertTrue(Path(second.comparison_artifacts["processed"]).exists())


if __name__ == "__main__":
    unittest.main()
