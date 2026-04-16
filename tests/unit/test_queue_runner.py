from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from upskayledd.config import load_app_config
from upskayledd.manifest_writer import read_artifact
from upskayledd.models import BackendSelection, ProjectManifest
from upskayledd.project_store import ProjectStore
from upskayledd.queue_runner import QueueRunner


class FlakyFFmpeg:
    def __init__(self) -> None:
        self.fail_next_run = True

    def is_available(self) -> bool:
        return True

    def run_processing_pipeline(
        self,
        source_path: str | Path,
        output_path: str | Path,
        video_filters: list[str],
        encode_plan: dict[str, object] | None = None,
    ) -> dict[str, object]:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"partial")
        if self.fail_next_run:
            self.fail_next_run = False
            raise RuntimeError("synthetic ffmpeg failure")
        output.write_bytes(b"complete")
        return {
            "output_path": str(output.resolve()),
            "attempt": "preserve_all",
            "stream_outcomes": [
                {"stream_type": "audio", "action": "preserve", "reason": "ffmpeg_copy"},
                {"stream_type": "subtitle", "action": "preserve", "reason": "ffmpeg_copy"},
                {"stream_type": "chapter", "action": "preserve", "reason": "ffmpeg_copy"},
            ],
            "fallbacks": [],
            "filter_chain": ",".join(video_filters),
        }


class UnavailableVapourSynth:
    def is_available(self) -> bool:
        return False


class QueueRunnerTests(unittest.TestCase):
    def test_enqueue_manifest_writes_run_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProjectStore(Path(temp_dir) / "state.sqlite3")
            runner = QueueRunner(store, load_app_config())
            manifest = ProjectManifest(
                project_id="proj-1",
                created_at="2026-04-14T00:00:00+00:00",
                source_files=[str(Path(temp_dir) / "episode01.mkv")],
                selected_profile_id="sd_live_action_ntsc",
                output_policy={"container": "mkv"},
                resolved_pipeline_stages=[],
                backend_preferences=["tensorrt_nvidia"],
                model_preferences=["real_esrgan_general"],
                batch_settings={},
                per_file_overrides={},
                custom_model_paths=[],
                hook_references=[],
                warnings=[],
            )
            jobs = runner.enqueue_manifest(
                manifest,
                output_dir=Path(temp_dir) / "output",
                backend_selection=BackendSelection(
                    backend_id="planning_only",
                    runtime="plan",
                    reasons=["test"],
                    degraded=True,
                ),
                encode_plan={"container": "mkv"},
            )
            self.assertEqual(len(jobs), 1)
            self.assertTrue(Path(jobs[0].payload_path).exists())

    def test_enqueue_manifest_preserves_relative_layout_and_avoids_name_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            store = ProjectStore(temp_path / "state.sqlite3")
            runner = QueueRunner(store, load_app_config())
            source_root = temp_path / "sources"
            season_one = source_root / "season01"
            season_two = source_root / "season02"
            season_one.mkdir(parents=True)
            season_two.mkdir(parents=True)
            episode_one = season_one / "episode01.mkv"
            episode_two = season_two / "episode01.mkv"
            episode_one.write_bytes(b"one")
            episode_two.write_bytes(b"two")
            output_dir = temp_path / "output"
            collision_path = output_dir / "season01" / "episode01.mkv"
            collision_path.parent.mkdir(parents=True, exist_ok=True)
            collision_path.write_bytes(b"existing")

            manifest = ProjectManifest(
                project_id="proj-batch",
                created_at="2026-04-14T00:00:00+00:00",
                source_files=[str(episode_one), str(episode_two)],
                selected_profile_id="sd_live_action_ntsc",
                output_policy={"container": "mkv"},
                resolved_pipeline_stages=[],
                backend_preferences=["tensorrt_nvidia"],
                model_preferences=[],
                batch_settings={},
                per_file_overrides={},
                custom_model_paths=[],
                hook_references=[],
                warnings=[],
            )

            jobs = runner.enqueue_manifest(
                manifest,
                output_dir=output_dir,
                backend_selection=BackendSelection(
                    backend_id="planning_only",
                    runtime="plan",
                    reasons=["test"],
                    degraded=False,
                ),
                encode_plan={"container": "mkv"},
            )

            self.assertEqual(len(jobs), 2)
            payload_one = read_artifact(jobs[0].payload_path)
            payload_two = read_artifact(jobs[1].payload_path)
            self.assertTrue(payload_one["output_files"][0].endswith("season01\\episode01__dup2.mkv"))
            self.assertTrue(payload_two["output_files"][0].endswith("season02\\episode01.mkv"))

    def test_execute_saved_job_restarts_from_stale_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProjectStore(Path(temp_dir) / "state.sqlite3")
            ffmpeg = FlakyFFmpeg()
            runner = QueueRunner(
                store,
                load_app_config(),
                ffmpeg=ffmpeg,
                vapoursynth=UnavailableVapourSynth(),
            )
            source = Path(temp_dir) / "episode01.mkv"
            source.write_bytes(b"video")
            manifest = ProjectManifest(
                project_id="proj-1",
                created_at="2026-04-14T00:00:00+00:00",
                source_files=[str(source)],
                selected_profile_id="sd_live_action_ntsc",
                output_policy={"container": "mkv"},
                resolved_pipeline_stages=[],
                backend_preferences=["vulkan_ml"],
                model_preferences=[],
                batch_settings={},
                per_file_overrides={},
                custom_model_paths=[],
                hook_references=[],
                warnings=[],
            )
            backend = BackendSelection(
                backend_id="vulkan_ml",
                runtime="test",
                reasons=[],
                degraded=False,
            )
            jobs = runner.enqueue_manifest(
                manifest,
                output_dir=Path(temp_dir) / "output",
                backend_selection=backend,
                encode_plan={"container": "mkv"},
            )

            first = runner.execute_saved_job(jobs[0].job_id, backend_selection=backend, force_degraded=True)
            self.assertIsNotNone(first)
            assert first is not None
            self.assertEqual(first.status.value, "failed")

            payload_after_failure = read_artifact(jobs[0].payload_path)
            partial_path = Path(payload_after_failure["encode_settings"]["working_output_path"])
            self.assertTrue(partial_path.exists())

            second = runner.execute_saved_job(jobs[0].job_id, backend_selection=backend, force_degraded=True)
            self.assertIsNotNone(second)
            assert second is not None
            self.assertEqual(second.status.value, "completed")

            payload_after_resume = read_artifact(jobs[0].payload_path)
            self.assertEqual(payload_after_resume["encode_settings"]["status"], "completed_degraded_execution")
            self.assertIn("restart_removed_partial_output", payload_after_resume["fallbacks"])
            final_output = Path(payload_after_resume["encode_settings"]["final_output_path"])
            self.assertTrue(final_output.exists())
            self.assertFalse(partial_path.exists())


if __name__ == "__main__":
    unittest.main()
