from __future__ import annotations

import json
import io
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from upskayledd.cli import main


def run_fixture_command(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    options = {
        "check": True,
        "capture_output": True,
        "text": True,
        **kwargs,
    }
    return subprocess.run(command, **options)  # noqa: S603


class CLISmokeTests(unittest.TestCase):
    def test_doctor_writes_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "doctor.json"
            exit_code = main(["doctor", "--json-output", str(output)])
            self.assertEqual(exit_code, 0)
            self.assertTrue(output.exists())
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertIn("platform_context", payload)
            self.assertTrue(str(payload.get("platform_summary", "")).strip())

    def test_list_model_packs_reports_curated_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "model_packs.json"
            exit_code = main(["list-model-packs", "--json-output", str(output)])
            self.assertEqual(exit_code, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            pack_ids = {item["id"] for item in payload["packs"]}
            self.assertIn("dpir_cleanup", pack_ids)

    def test_list_encode_profiles_reports_configured_delivery_lanes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "encode_profiles.json"
            exit_code = main(["list-encode-profiles", "--json-output", str(output)])
            self.assertEqual(exit_code, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            profiles = {item["id"]: item for item in payload["profiles"]}
            profile_ids = set(profiles)
            self.assertEqual(payload["default_profile_id"], "hevc_balanced_archive")
            self.assertIn("hevc_smaller_archive", profile_ids)
            self.assertIn("h264_compatibility_mp4", profile_ids)
            self.assertIn("Archive-first lane", [item["label"] for item in profiles["hevc_balanced_archive"]["facts"]])
            self.assertIn("May grow for compatibility", [item["label"] for item in profiles["h264_compatibility_mp4"]["facts"]])

    def test_setup_plan_writes_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "setup_plan.json"
            exit_code = main(["setup-plan", "--json-output", str(output)])
            self.assertEqual(exit_code, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertIn("actions", payload)
            self.assertIn("platform_summary", payload)

    def test_paths_writes_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "paths.json"
            exit_code = main(["paths", "--json-output", str(output)])
            self.assertEqual(exit_code, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            location_ids = {item["location_id"] for item in payload["locations"]}
            self.assertIn("output_root", location_ids)
            self.assertIn("support_bundle_dir", location_ids)

    def test_platform_matrix_writes_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "platform_matrix.json"
            with mock.patch.dict(
                os.environ,
                {"TMP": temp_dir, "TEMP": temp_dir, "TMPDIR": temp_dir},
                clear=False,
            ):
                exit_code = main(["platform-matrix", "--json-output", str(output)])
            self.assertEqual(exit_code, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            context_ids = {item["context_id"] for item in payload["contexts"]}
            self.assertIn("windows_native", context_ids)
            self.assertIn("linux_wsl", context_ids)
            self.assertIn("generated_at_utc", payload)
            self.assertIn("watch_items", payload)
            self.assertIsInstance(payload["watch_items"], list)

    def test_platform_matrix_prints_context_actions_inline(self) -> None:
        buffer = io.StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.dict(
                os.environ,
                {"TMP": temp_dir, "TEMP": temp_dir, "TMPDIR": temp_dir},
                clear=False,
            ):
                with redirect_stdout(buffer):
                    exit_code = main(["platform-matrix"])

        self.assertEqual(exit_code, 0)
        output = buffer.getvalue()
        self.assertIn("Windows", output)
        self.assertIn("Linux (WSL)", output)
        self.assertIn("Setup actions:", output)
        self.assertIn("- ", output)

    def test_platform_matrix_can_print_execution_smoke_status(self) -> None:
        buffer = io.StringIO()
        payload = {
            "generated_at_utc": "2026-04-16T00:00:00Z",
            "include_execution_smoke": True,
            "repo_root": str(Path.cwd()),
            "contexts": [
                {
                    "context_id": "windows_native",
                    "display_name": "Windows (native)",
                    "platform_summary": "Windows · 10 · AMD64 · Python 3.13.12",
                    "health": "ready",
                    "available": True,
                    "missing_check_count": 0,
                    "degraded_check_count": 0,
                    "action_count": 0,
                    "canonical_runtime_status": "ready",
                    "actions": [],
                    "execution_smoke": {
                        "status": "passed",
                        "execution_mode": "degraded",
                        "detail": "Generated a tiny fixture and completed a degraded execution run.",
                    },
                }
            ],
            "watch_items": [],
        }
        with mock.patch("upskayledd.cli.AppService.platform_validation_matrix", return_value=payload):
            with redirect_stdout(buffer):
                exit_code = main(["platform-matrix", "--include-execution-smoke"])

        self.assertEqual(exit_code, 0)
        output = buffer.getvalue()
        self.assertIn("Canonical runtime: ready", output)
        self.assertIn("Execution smoke: passed (degraded)", output)
        self.assertIn("Generated a tiny fixture", output)

    def test_compare_media_writes_json_output(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg/ffprobe not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.mkv"
            output_media = temp_path / "output.mp4"
            output_json = temp_path / "compare.json"
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
                check=True,
                capture_output=True,
                text=True,
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
                    str(output_media),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            exit_code = main(
                [
                    "compare-media",
                    str(source),
                    str(output_media),
                    "--encode-profile",
                    "h264_compatibility_mp4",
                    "--json-output",
                    str(output_json),
                ]
            )
            self.assertEqual(exit_code, 0)
            payload = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["input_metrics"]["container_name"], "matroska")
            self.assertIn("guidance", payload["comparison"])
            self.assertTrue(payload["comparison"]["guidance"])

    def test_recommend_builds_manifest_for_real_clip(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("ffmpeg not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.mp4"
            manifest = Path(temp_dir) / "project_manifest.json"
            payload_output = Path(temp_dir) / "recommendation.json"
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
                check=True,
                capture_output=True,
                text=True,
            )
            exit_code = main(
                [
                    "recommend",
                    str(source),
                    "--project-output",
                    str(manifest),
                    "--json-output",
                    str(payload_output),
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertTrue(manifest.exists())
            payload = json.loads(payload_output.read_text(encoding="utf-8"))
            self.assertIn("delivery_guidance", payload)
            self.assertTrue(payload["delivery_guidance"]["selected_messages"])

    def test_recommend_accepts_unknown_video_extension_when_probe_finds_video(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("ffmpeg not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.remuxblob"
            manifest = Path(temp_dir) / "project_manifest.json"
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
                    "-f",
                    "matroska",
                    str(source),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            exit_code = main(["recommend", str(source), "--project-output", str(manifest)])
            self.assertEqual(exit_code, 0)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["source_files"], [str(source.resolve())])

    def test_recommend_applies_encode_profile_override(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("ffmpeg not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.mp4"
            manifest = Path(temp_dir) / "project_manifest.json"
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
                check=True,
                capture_output=True,
                text=True,
            )
            exit_code = main(
                [
                    "recommend",
                    str(source),
                    "--encode-profile",
                    "h264_compatibility_mp4",
                    "--project-output",
                    str(manifest),
                ]
            )
            self.assertEqual(exit_code, 0)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["output_policy"]["encode_profile_id"], "h264_compatibility_mp4")
            self.assertEqual(payload["output_policy"]["container"], "mp4")
            self.assertEqual(payload["output_policy"]["audio_codec"], "aac")

    def test_preview_extracts_real_artifacts_for_cleanup_stage(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("ffmpeg not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.mp4"
            result_path = Path(temp_dir) / "preview_result.json"
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
                check=True,
                capture_output=True,
                text=True,
            )
            exit_code = main(
                [
                    "preview",
                    str(source),
                    "--stage",
                    "cleanup",
                    "--json-output",
                    str(result_path),
                ]
            )
            self.assertEqual(exit_code, 0)
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["artifact_paths"])
            self.assertIn("processed", payload["comparison_artifacts"])

    def test_preview_exact_uses_canonical_cleanup_when_available(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        vspipe = shutil.which("vspipe")
        if not ffmpeg or not vspipe:
            self.skipTest("ffmpeg or vspipe not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.mp4"
            result_path = Path(temp_dir) / "preview_exact.json"
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
                check=True,
                capture_output=True,
                text=True,
            )
            exit_code = main(
                [
                    "preview",
                    str(source),
                    "--stage",
                    "cleanup",
                    "--fidelity-mode",
                    "exact",
                    "--json-output",
                    str(result_path),
                ]
            )
            self.assertEqual(exit_code, 0)
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["fidelity_mode"], "exact")
            self.assertIn("processed", payload["comparison_artifacts"])

    def test_preview_exact_uses_canonical_upscale_stage_when_available(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        vspipe = shutil.which("vspipe")
        if not ffmpeg or not vspipe:
            self.skipTest("ffmpeg or vspipe not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.mp4"
            result_path = Path(temp_dir) / "preview_upscale_exact.json"
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
                check=True,
                capture_output=True,
                text=True,
            )
            exit_code = main(
                [
                    "preview",
                    str(source),
                    "--stage",
                    "upscale",
                    "--fidelity-mode",
                    "exact",
                    "--stage-setting",
                    "target_width=640",
                    "--stage-setting",
                    "target_height=480",
                    "--json-output",
                    str(result_path),
                ]
            )
            self.assertEqual(exit_code, 0)
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["fidelity_mode"], "exact")
            self.assertIn("processed", payload["comparison_artifacts"])

    def test_run_execute_degraded_creates_output_file(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("ffmpeg not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.mp4"
            manifest = Path(temp_dir) / "project_manifest.json"
            output_dir = Path(temp_dir) / "output"
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
                check=True,
                capture_output=True,
                text=True,
            )
            recommend_exit = main(["recommend", str(source), "--project-output", str(manifest)])
            self.assertEqual(recommend_exit, 0)
            run_exit = main(
                [
                    "run",
                    str(manifest),
                    "--output-dir",
                    str(output_dir),
                    "--execute-degraded",
                ]
            )
            self.assertEqual(run_exit, 0)
            outputs = list(output_dir.glob("*.mkv"))
            payloads = list(output_dir.glob("*.run_manifest.json"))
            self.assertTrue(outputs)
            self.assertTrue(payloads)
            payload = json.loads(payloads[0].read_text(encoding="utf-8"))
            self.assertGreater(payload["encode_settings"]["input_size_bytes"], 0)
            self.assertGreater(payload["encode_settings"]["output_size_bytes"], 0)
            self.assertGreater(payload["encode_settings"]["size_ratio"], 0)
            self.assertIn("media_metrics", payload["encode_settings"])
            self.assertIn("input", payload["encode_settings"]["media_metrics"])
            self.assertIn("output", payload["encode_settings"]["media_metrics"])
            self.assertIn("comparison", payload["encode_settings"]["media_metrics"])
            self.assertIn("conversion_guidance", payload["encode_settings"])

    def test_run_execute_degraded_preserves_relative_output_layout_for_repeated_batch_stems(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("ffmpeg not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_root = temp_path / "batch"
            season_one = source_root / "season01"
            season_two = source_root / "season02"
            season_one.mkdir(parents=True)
            season_two.mkdir(parents=True)
            fixtures = [
                season_one / "episode01.mp4",
                season_two / "episode01.mp4",
            ]
            manifest = temp_path / "project_manifest.json"
            output_dir = temp_path / "output"
            for source in fixtures:
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
                    check=True,
                    capture_output=True,
                    text=True,
                )

            recommend_exit = main(["recommend", str(source_root), "--project-output", str(manifest)])
            self.assertEqual(recommend_exit, 0)
            run_exit = main(
                [
                    "run",
                    str(manifest),
                    "--output-dir",
                    str(output_dir),
                    "--execute-degraded",
                ]
            )
            self.assertEqual(run_exit, 0)
            self.assertTrue((output_dir / "season01" / "episode01.mkv").exists())
            self.assertTrue((output_dir / "season02" / "episode01.mkv").exists())

    def test_run_execute_degraded_preserves_audio_subtitles_and_chapters(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg/ffprobe not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample_with_streams.mkv"
            manifest = temp_path / "project_manifest.json"
            output_dir = temp_path / "output"
            subtitles = temp_path / "sample.srt"
            metadata = temp_path / "sample.ffmeta"
            subtitles.write_text(
                "1\n00:00:00,000 --> 00:00:00,900\nBridge status nominal.\n",
                encoding="utf-8",
            )
            metadata.write_text(
                ";FFMETADATA1\n"
                "[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=500\ntitle=Cold Open\n"
                "[CHAPTER]\nTIMEBASE=1/1000\nSTART=500\nEND=1000\ntitle=Main Scene\n",
                encoding="utf-8",
            )
            run_fixture_command(
                [
                    ffmpeg,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=720x480:d=1",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=1000:duration=1",
                    "-i",
                    str(subtitles),
                    "-f",
                    "ffmetadata",
                    "-i",
                    str(metadata),
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-map",
                    "2:0",
                    "-map_metadata",
                    "3",
                    "-map_chapters",
                    "3",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-c:s",
                    "srt",
                    "-shortest",
                    str(source),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            recommend_exit = main(["recommend", str(source), "--project-output", str(manifest)])
            self.assertEqual(recommend_exit, 0)
            run_exit = main(
                [
                    "run",
                    str(manifest),
                    "--output-dir",
                    str(output_dir),
                    "--execute-degraded",
                ]
            )
            self.assertEqual(run_exit, 0)

            outputs = list(output_dir.glob("*.mkv"))
            payloads = list(output_dir.glob("*.run_manifest.json"))
            self.assertTrue(outputs)
            self.assertTrue(payloads)

            probe = run_fixture_command(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type:chapter=id",
                    "-show_chapters",
                    "-of",
                    "json",
                    str(outputs[0]),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            probe_payload = json.loads(probe.stdout)
            stream_types = {stream["codec_type"] for stream in probe_payload.get("streams", [])}
            self.assertIn("audio", stream_types)
            self.assertIn("subtitle", stream_types)
            self.assertGreaterEqual(len(probe_payload.get("chapters", [])), 2)

            run_manifest = json.loads(payloads[0].read_text(encoding="utf-8"))
            outcomes = {
                item["stream_type"]: item["action"]
                for item in run_manifest.get("stream_outcomes", [])
            }
            self.assertEqual(outcomes.get("audio"), "preserve")
            self.assertEqual(outcomes.get("subtitle"), "preserve")
            self.assertEqual(outcomes.get("chapter"), "preserve")
            self.assertEqual(run_manifest["encode_settings"]["execution_mode"], "ffmpeg_degraded")

    def test_run_execute_degraded_supports_mp4_compatibility_output(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg/ffprobe not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample_with_streams.mkv"
            manifest = temp_path / "project_manifest.json"
            output_dir = temp_path / "output"
            subtitles = temp_path / "sample.srt"
            metadata = temp_path / "sample.ffmeta"
            subtitles.write_text(
                "1\n00:00:00,000 --> 00:00:00,900\nCompatibility preview.\n",
                encoding="utf-8",
            )
            metadata.write_text(
                ";FFMETADATA1\n"
                "[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=500\ntitle=Act One\n"
                "[CHAPTER]\nTIMEBASE=1/1000\nSTART=500\nEND=1000\ntitle=Act Two\n",
                encoding="utf-8",
            )
            run_fixture_command(
                [
                    ffmpeg,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=720x480:d=1",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=660:duration=1",
                    "-i",
                    str(subtitles),
                    "-f",
                    "ffmetadata",
                    "-i",
                    str(metadata),
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-map",
                    "2:0",
                    "-map_metadata",
                    "3",
                    "-map_chapters",
                    "3",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-c:s",
                    "srt",
                    "-shortest",
                    str(source),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            recommend_exit = main(
                [
                    "recommend",
                    str(source),
                    "--encode-profile",
                    "h264_compatibility_mp4",
                    "--project-output",
                    str(manifest),
                ]
            )
            self.assertEqual(recommend_exit, 0)
            run_exit = main(
                [
                    "run",
                    str(manifest),
                    "--output-dir",
                    str(output_dir),
                    "--execute-degraded",
                ]
            )
            self.assertEqual(run_exit, 0)

            outputs = list(output_dir.glob("*.mp4"))
            payloads = list(output_dir.glob("*.run_manifest.json"))
            self.assertTrue(outputs)
            self.assertTrue(payloads)

            probe = run_fixture_command(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type,codec_name:chapter=id",
                    "-show_chapters",
                    "-of",
                    "json",
                    str(outputs[0]),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            probe_payload = json.loads(probe.stdout)
            streams = probe_payload.get("streams", [])
            stream_types = {stream["codec_type"] for stream in streams}
            subtitle_codecs = {
                stream.get("codec_name", "")
                for stream in streams
                if stream.get("codec_type") == "subtitle"
            }
            self.assertIn("audio", stream_types)
            self.assertIn("subtitle", stream_types)
            self.assertIn("mov_text", subtitle_codecs)
            self.assertGreaterEqual(len(probe_payload.get("chapters", [])), 2)

            run_manifest = json.loads(payloads[0].read_text(encoding="utf-8"))
            self.assertEqual(run_manifest["encode_settings"]["container"], "mp4")
            self.assertEqual(run_manifest["encode_settings"]["audio_codec"], "aac")
            self.assertEqual(run_manifest["encode_settings"]["subtitle_codec"], "mov_text")

    def test_run_execute_uses_canonical_runner_when_available(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        vspipe = shutil.which("vspipe")
        if not ffmpeg or not vspipe:
            self.skipTest("ffmpeg or vspipe not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.mp4"
            manifest = Path(temp_dir) / "project_manifest.json"
            output_dir = Path(temp_dir) / "output"
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
                check=True,
                capture_output=True,
                text=True,
            )
            recommend_exit = main(["recommend", str(source), "--project-output", str(manifest)])
            self.assertEqual(recommend_exit, 0)
            run_exit = main(
                [
                    "run",
                    str(manifest),
                    "--output-dir",
                    str(output_dir),
                    "--execute",
                ]
            )
            self.assertEqual(run_exit, 0)
            outputs = list(output_dir.glob("*.mkv"))
            payloads = list(output_dir.glob("*.run_manifest.json"))
            self.assertTrue(outputs)
            self.assertTrue(payloads)
            payload = json.loads(payloads[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["encode_settings"]["execution_mode"], "vapoursynth_canonical")

    def test_run_execute_canonical_preserves_audio_subtitles_and_chapters(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        vspipe = shutil.which("vspipe")
        if not ffmpeg or not ffprobe or not vspipe:
            self.skipTest("ffmpeg/ffprobe/vspipe not available")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample_with_streams.mkv"
            manifest = temp_path / "project_manifest.json"
            output_dir = temp_path / "output"
            subtitles = temp_path / "sample.srt"
            metadata = temp_path / "sample.ffmeta"
            subtitles.write_text(
                "1\n00:00:00,000 --> 00:00:00,900\nPreview the restored pass.\n",
                encoding="utf-8",
            )
            metadata.write_text(
                ";FFMETADATA1\n"
                "[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=500\ntitle=Act One\n"
                "[CHAPTER]\nTIMEBASE=1/1000\nSTART=500\nEND=1000\ntitle=Act Two\n",
                encoding="utf-8",
            )
            run_fixture_command(
                [
                    ffmpeg,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=720x480:d=1",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=880:duration=1",
                    "-i",
                    str(subtitles),
                    "-f",
                    "ffmetadata",
                    "-i",
                    str(metadata),
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-map",
                    "2:0",
                    "-map_metadata",
                    "3",
                    "-map_chapters",
                    "3",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-c:s",
                    "srt",
                    "-shortest",
                    str(source),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            recommend_exit = main(["recommend", str(source), "--project-output", str(manifest)])
            self.assertEqual(recommend_exit, 0)
            run_exit = main(
                [
                    "run",
                    str(manifest),
                    "--output-dir",
                    str(output_dir),
                    "--execute",
                ]
            )
            self.assertEqual(run_exit, 0)

            outputs = list(output_dir.glob("*.mkv"))
            payloads = list(output_dir.glob("*.run_manifest.json"))
            self.assertTrue(outputs)
            self.assertTrue(payloads)

            probe = run_fixture_command(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type:chapter=id",
                    "-show_chapters",
                    "-of",
                    "json",
                    str(outputs[0]),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            probe_payload = json.loads(probe.stdout)
            stream_types = {stream["codec_type"] for stream in probe_payload.get("streams", [])}
            self.assertIn("audio", stream_types)
            self.assertIn("subtitle", stream_types)
            self.assertGreaterEqual(len(probe_payload.get("chapters", [])), 2)

            run_manifest = json.loads(payloads[0].read_text(encoding="utf-8"))
            outcomes = {
                item["stream_type"]: item["action"]
                for item in run_manifest.get("stream_outcomes", [])
            }
            self.assertEqual(outcomes.get("audio"), "preserve")
            self.assertEqual(outcomes.get("subtitle"), "preserve")
            self.assertEqual(outcomes.get("chapter"), "preserve")
            self.assertEqual(run_manifest["encode_settings"]["execution_mode"], "vapoursynth_canonical")

    def test_export_support_bundle_writes_zip_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = Path(temp_dir) / "support_bundle.zip"
            metadata = Path(temp_dir) / "support_bundle.json"
            exit_code = main(
                [
                    "export-support-bundle",
                    "--output",
                    str(bundle),
                    "--json-output",
                    str(metadata),
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertTrue(bundle.exists())
            payload = json.loads(metadata.read_text(encoding="utf-8"))
            self.assertIn("bundle_manifest.json", payload["entries"])
            with zipfile.ZipFile(bundle) as archive:
                self.assertIn("doctor_report.json", archive.namelist())
                self.assertIn("platform_validation_matrix.json", archive.namelist())


if __name__ == "__main__":
    unittest.main()
