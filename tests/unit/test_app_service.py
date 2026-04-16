from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from upskayledd.app_service import AppService
from upskayledd.core.errors import ConfigError
from upskayledd.models import ProjectManifest


ROOT = Path(__file__).resolve().parents[2]


def make_temp_config(temp_dir: Path) -> Path:
    config_dir = temp_dir / "config"
    shutil.copytree(ROOT / "config", config_dir)
    defaults_path = config_dir / "defaults.toml"
    defaults = defaults_path.read_text(encoding="utf-8")
    replacements = {
        'default_output_root = "runtime/output"': f'default_output_root = "{(temp_dir / "output").as_posix()}"',
        'state_db_path = "runtime/state/upskayledd.sqlite3"': f'state_db_path = "{(temp_dir / "state.sqlite3").as_posix()}"',
        'preview_cache_dir = "runtime/cache/previews"': f'preview_cache_dir = "{(temp_dir / "preview_cache").as_posix()}"',
        'bundle_output_dir = "runtime/support"': f'bundle_output_dir = "{(temp_dir / "support").as_posix()}"',
    }
    for old, new in replacements.items():
        defaults = defaults.replace(old, new)
    defaults_path.write_text(defaults, encoding="utf-8")
    return config_dir


def normalize_path(value: str | Path) -> str:
    return str(Path(value).resolve()).lower()


def run_fixture_command(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    options = {
        "check": True,
        "capture_output": True,
        "text": True,
        **kwargs,
    }
    return subprocess.run(command, **options)  # noqa: S603


class AppServiceTests(unittest.TestCase):
    def test_list_encode_profiles_reflects_configured_delivery_lanes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = make_temp_config(Path(temp_dir))
            service = AppService(str(config_dir))

            payload = service.list_encode_profiles()

            self.assertEqual(payload["default_profile_id"], "hevc_balanced_archive")
            profile_ids = {item["id"] for item in payload["profiles"]}
            self.assertIn("hevc_smaller_archive", profile_ids)
            self.assertIn("h264_compatibility_mp4", profile_ids)

    def test_recommend_target_includes_delivery_guidance(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg/ffprobe not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = make_temp_config(temp_path)
            service = AppService(str(config_dir))
            source = temp_path / "sample.mp4"
            run_fixture_command(
                [
                    ffmpeg,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=720x480:d=1",
                    "-pix_fmt",
                    "yuv420p",
                    str(source),
                ],
            )

            payload = service.recommend_target(str(source))

            guidance = payload["delivery_guidance"]
            self.assertEqual(guidance["selected_profile_id"], "hevc_balanced_archive")
            self.assertTrue(guidance["selected_messages"])
            alternative_ids = {item["id"] for item in guidance["alternative_profiles"]}
            self.assertIn("hevc_smaller_archive", alternative_ids)
            self.assertIn("h264_compatibility_mp4", alternative_ids)

    def test_session_state_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = make_temp_config(Path(temp_dir))
            service = AppService(str(config_dir))

            service.save_session_state(
                "desktop",
                {
                    "page": "workspace",
                    "simple_mode": False,
                    "comparison_mode": "ab_toggle",
                    "preview_duration_seconds": 4.5,
                },
            )

            payload = service.load_session_state("desktop")
            self.assertEqual(payload["page"], "workspace")
            self.assertFalse(payload["simple_mode"])
            self.assertEqual(payload["comparison_mode"], "ab_toggle")
            self.assertEqual(payload["preview_duration_seconds"], 4.5)

    def test_recent_targets_are_deduped_bounded_and_pruned(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = make_temp_config(temp_path)
            service = AppService(str(config_dir))
            folder = temp_path / "season01"
            folder.mkdir()
            episode = temp_path / "episode01.mkv"
            episode.write_bytes(b"video")
            old_missing = temp_path / "missing.mkv"

            service.remember_recent_target(folder, recommended_profile_id="sd_live_action_pal", source_count=4, manual_review_count=1)
            service.remember_recent_target(episode, recommended_profile_id="sd_live_action_ntsc", source_count=1, manual_review_count=0)
            service.remember_recent_target(folder, recommended_profile_id="sd_live_action_pal", source_count=4, manual_review_count=1)
            recent = service.list_recent_targets()

            self.assertEqual(len(recent), 2)
            self.assertEqual(recent[0]["path"], str(folder.resolve()))
            self.assertEqual(recent[1]["path"], str(episode.resolve()))
            self.assertEqual(recent[0]["recommended_profile_id"], "sd_live_action_pal")
            self.assertEqual(recent[0]["source_count"], 4)
            self.assertEqual(recent[0]["manual_review_count"], 1)

            service.save_session_state(
                service._recent_targets_state_key(),
                {
                    "targets": [
                        {"path": str(old_missing.resolve()), "label": "missing.mkv", "kind": "file", "exists": False},
                        *recent,
                    ]
                },
            )
            pruned = service.prune_recent_targets()
            pruned_paths = [item["path"] for item in pruned]
            self.assertNotIn(str(old_missing.resolve()), pruned_paths)
            self.assertEqual(pruned_paths[0], str(folder.resolve()))

    def test_dashboard_snapshot_and_run_manifest_lookup_use_saved_jobs(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("ffmpeg not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = make_temp_config(temp_path)
            service = AppService(str(config_dir))
            source = temp_path / "sample.mp4"
            manifest_path = temp_path / "project_manifest.json"
            run_fixture_command(
                [
                    ffmpeg,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=320x240:d=0.5",
                    "-pix_fmt",
                    "yuv420p",
                    str(source),
                ],
            )

            recommendation = service.recommend_target(str(source))
            manifest = ProjectManifest.from_dict(recommendation["project_manifest"])
            _, jobs = service.run_project(manifest, execute=False)

            snapshot = service.dashboard_snapshot()
            self.assertEqual(snapshot["counts"]["queued"], 1)
            self.assertTrue(snapshot["jobs"])
            self.assertEqual(snapshot["overview"]["total_jobs"], 1)
            self.assertEqual(snapshot["overview"]["active_job_count"], 1)
            self.assertEqual(snapshot["overview"]["completed_job_count"], 0)
            self.assertEqual(snapshot["overview"]["issue_job_count"], 0)
            self.assertEqual(snapshot["overview"]["focus_job"]["status"], "queued")
            self.assertEqual(snapshot["overview"]["focus_job"]["source_name"], source.name)

            run_manifest = service.run_manifest_for_job(jobs[0].job_id)
            self.assertIsNotNone(run_manifest)
            self.assertEqual(run_manifest["schema_name"], "run_manifest")
            output_location = service.job_output_location(jobs[0].job_id)
            self.assertIsNotNone(output_location)
            assert output_location is not None
            self.assertEqual(normalize_path(output_location["path"]), normalize_path(temp_path / "output"))

    def test_recommend_target_includes_batch_source_rows_and_outliers(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg/ffprobe not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = make_temp_config(temp_path)
            service = AppService(str(config_dir))
            aligned = temp_path / "episode01.mp4"
            outlier = temp_path / "episode02_outlier.mp4"
            fixtures = [
                (aligned, "color=c=black:s=320x240:d=0.5", "25"),
                (outlier, "color=c=black:s=640x480:d=0.5", "15"),
            ]
            for path, source_filter, fps in fixtures:
                run_fixture_command(
                    [
                        ffmpeg,
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        source_filter,
                        "-r",
                        fps,
                        "-pix_fmt",
                        "yuv420p",
                        str(path),
                    ],
                )

            recommendation = service.recommend_target(str(temp_path))
            batch_summary = recommendation["batch_summary"]
            self.assertEqual(batch_summary["source_count"], 2)
            self.assertEqual(len(batch_summary["source_rows"]), 2)
            self.assertIn(str(outlier.resolve()), batch_summary["outlier_sources"])
            self.assertTrue(any(row["profile_outlier"] for row in batch_summary["source_rows"]))

    def test_runtime_action_plan_uses_configured_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = make_temp_config(Path(temp_dir))
            service = AppService(str(config_dir))

            actions = service.runtime_action_plan(
                doctor_report={
                    "checks": [
                        {"name": "ffmpeg", "status": "missing", "detail": "not found"},
                        {"name": "output_root", "status": "missing", "detail": "not writable"},
                    ],
                    "platform_context": {"is_wsl": True},
                },
                model_pack_payload={
                    "packs": [
                        {
                            "id": "dpir_cleanup",
                            "label": "DPIR Cleanup Models",
                            "recommended": True,
                            "installed": False,
                        }
                    ]
                },
            )

            self.assertEqual(actions[0]["action_id"], "check:ffmpeg")
            self.assertTrue(any(action["action_id"] == "context:wsl_environment" for action in actions))
            self.assertTrue(any(action["action_id"] == "pack:dpir_cleanup" for action in actions))
            self.assertTrue(any("writable" in action["detail"].lower() for action in actions))

    def test_doctor_report_includes_platform_context_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = make_temp_config(Path(temp_dir))
            service = AppService(str(config_dir))

            payload = service.doctor_report()

            self.assertIn("platform_context", payload)
            self.assertIn("platform_summary", payload)
            self.assertTrue(str(payload["platform_summary"]).strip())
            self.assertIn("environment_label", payload["platform_context"])

    def test_runtime_locations_resolve_configured_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = make_temp_config(temp_path)
            service = AppService(str(config_dir))

            payload = service.runtime_locations()
            location_lookup = {item["location_id"]: item for item in payload["locations"]}

            self.assertEqual(normalize_path(location_lookup["output_root"]["path"]), normalize_path(temp_path / "output"))
            self.assertEqual(
                normalize_path(location_lookup["preview_cache_dir"]["path"]),
                normalize_path(temp_path / "preview_cache"),
            )
            self.assertEqual(
                normalize_path(location_lookup["support_bundle_dir"]["path"]),
                normalize_path(temp_path / "support"),
            )
            self.assertEqual(normalize_path(location_lookup["app_state_dir"]["path"]), normalize_path(temp_path))
            self.assertIn("primary_model_dir", location_lookup)

    def test_platform_validation_matrix_uses_shared_builder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = make_temp_config(Path(temp_dir))
            service = AppService(str(config_dir))
            payload = {
                "generated_at_utc": "2026-04-16T00:00:00Z",
                "repo_root": "Z:\\UPSKAYLEDD",
                "contexts": [{"context_id": "windows_native", "health": "ready"}],
                "watch_items": ["Everything looks good enough."],
            }

            with mock.patch("upskayledd.app_service.build_platform_validation_payload", return_value=payload) as builder:
                result = service.platform_validation_matrix()

            builder.assert_called_once_with(None)
            self.assertEqual(result["contexts"][0]["context_id"], "windows_native")

    def test_compare_media_files_returns_normalized_metrics_and_guidance(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg/ffprobe not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = make_temp_config(temp_path)
            service = AppService(str(config_dir))
            source = temp_path / "source.mkv"
            output = temp_path / "output.mp4"
            run_fixture_command(
                [
                    ffmpeg,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=320x240:d=0.6",
                    "-pix_fmt",
                    "yuv420p",
                    str(source),
                ],
            )
            run_fixture_command(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(source),
                    "-c:v",
                    "libx264",
                    "-crf",
                    "18",
                    "-c:a",
                    "aac",
                    str(output),
                ],
            )

            payload = service.compare_media_files(
                source,
                output,
                encode_profile_id="  h264_compatibility_mp4  ",
            )

            self.assertEqual(payload["encode_profile_id"], "h264_compatibility_mp4")
            self.assertEqual(payload["input_metrics"]["container_name"], "matroska")
            self.assertEqual(payload["output_metrics"]["container_name"], "mov")
            guidance = "\n".join(payload["comparison"]["guidance"])
            self.assertIn("Compatibility delivery favors easier playback", guidance)

    def test_compare_media_files_rejects_unknown_encode_profile_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = make_temp_config(Path(temp_dir))
            service = AppService(str(config_dir))

            with self.assertRaises(ConfigError):
                service.compare_media_files("before.mkv", "after.mkv", encode_profile_id="not-a-real-profile")

    def test_support_bundle_redacts_paths_by_default_and_includes_selected_job_manifest(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg/ffprobe not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = make_temp_config(temp_path)
            service = AppService(str(config_dir))
            source = temp_path / "season" / "episode01.mp4"
            source.parent.mkdir()
            run_fixture_command(
                [
                    ffmpeg,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=320x240:d=0.5",
                    "-pix_fmt",
                    "yuv420p",
                    str(source),
                ],
            )

            recommendation = service.recommend_target(str(source))
            manifest = ProjectManifest.from_dict(recommendation["project_manifest"])
            _, jobs = service.run_project(manifest, execute=False)
            service.save_session_state(
                "desktop_ui_state",
                {
                    "last_target": str(source.parent),
                    "selected_source": str(source),
                    "selected_job_id": jobs[0].job_id,
                },
            )

            bundle = service.export_support_bundle(
                session_state_key="desktop_ui_state",
                selected_job_id=jobs[0].job_id,
            )
            bundle_path = Path(bundle["bundle_path"])
            self.assertTrue(bundle_path.exists())
            self.assertFalse(bundle["include_full_paths"])

            with zipfile.ZipFile(bundle_path) as archive:
                session_payload = archive.read("session_state.json").decode("utf-8")
                dashboard_payload = archive.read("dashboard_snapshot.json").decode("utf-8")
                run_manifest_payload = archive.read("selected_run_manifest.json").decode("utf-8")
                platform_matrix_payload = archive.read("platform_validation_matrix.json").decode("utf-8")

            self.assertIn("episode01.mp4", session_payload)
            self.assertNotIn(str(source), session_payload)
            self.assertIn("episode01.mp4", dashboard_payload)
            self.assertNotIn(str(source), dashboard_payload)
            self.assertIn("episode01.mp4", run_manifest_payload)
            self.assertNotIn(str(source), run_manifest_payload)
            self.assertIn("contexts", platform_matrix_payload)
            self.assertNotIn(str(ROOT), platform_matrix_payload)


if __name__ == "__main__":
    unittest.main()
