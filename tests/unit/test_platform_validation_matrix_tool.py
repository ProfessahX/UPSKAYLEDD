from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from upskayledd import platform_validation_matrix as matrix_module


def _load_module():
    module_path = Path(__file__).resolve().parents[2] / "tools" / "run_platform_validation_matrix.py"
    spec = importlib.util.spec_from_file_location("run_platform_validation_matrix", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PlatformValidationMatrixToolTests(unittest.TestCase):
    def test_windows_to_wsl_path_converts_drive_letter_paths(self) -> None:
        module = _load_module()
        converted = module.windows_to_wsl_path(Path("Z:/UPSKAYLEDD/src"))
        self.assertEqual(converted, "/mnt/z/UPSKAYLEDD/src")

    def test_summarize_context_and_watch_items_flag_missing_runtime_gaps(self) -> None:
        module = _load_module()
        native = module.summarize_context(
            "windows_native",
            "Windows (native)",
            {
                "platform_summary": "Windows · 10 · AMD64 · Python 3.13.12",
                "checks": [{"name": "ffmpeg", "status": "healthy"}],
                "warnings": [],
                "path_rules": [],
            },
            {"actions": []},
        )
        wsl = module.summarize_context(
            "linux_wsl",
            "Linux (WSL)",
            {
                "platform_summary": "Linux (WSL) · 6.6.87.2-microsoft-standard-WSL2 · x86_64 · Python 3.12.3",
                "checks": [
                    {"name": "vspipe", "status": "missing"},
                    {"name": "model_dir", "status": "degraded"},
                ],
                "warnings": ["Canonical restoration stack is incomplete."],
                "path_rules": [],
            },
            {"actions": [{"action_id": "context:wsl_environment"}]},
        )

        watch_items = module.build_watch_items([native, wsl])

        self.assertEqual(native["health"], "ready")
        self.assertEqual(wsl["health"], "attention")
        self.assertEqual(wsl["missing_check_count"], 1)
        self.assertEqual(wsl["degraded_check_count"], 1)
        self.assertEqual(wsl["action_count"], 1)
        self.assertEqual(wsl["canonical_runtime_status"], "incomplete")
        self.assertIn("vspipe", wsl["missing_check_names"])
        self.assertTrue(any("Linux (WSL) still has missing runtime checks." == item for item in watch_items))
        self.assertTrue(any("Native Windows and Linux-side WSL currently differ in runtime readiness." == item for item in watch_items))

    def test_missing_checks_without_actions_still_surface_watch_item(self) -> None:
        module = _load_module()
        context = module.summarize_context(
            "linux_wsl",
            "Linux (WSL)",
            {
                "platform_summary": "Linux (WSL) · 6.6.87.2-microsoft-standard-WSL2 · x86_64 · Python 3.12.3",
                "checks": [{"name": "vspipe", "status": "missing"}],
                "warnings": [],
                "path_rules": [],
            },
            {"actions": []},
        )

        watch_items = module.build_watch_items([context])

        self.assertEqual(context["health"], "watch")
        self.assertIn("Linux (WSL) still has missing runtime checks.", watch_items)

    def test_degraded_checks_without_warnings_still_surface_watch_item(self) -> None:
        module = _load_module()
        context = module.summarize_context(
            "linux_wsl",
            "Linux (WSL)",
            {
                "platform_summary": "Linux (WSL) · 6.6.87.2-microsoft-standard-WSL2 · x86_64 · Python 3.12.3",
                "checks": [{"name": "vspipe", "status": "degraded"}],
                "warnings": [],
                "path_rules": [],
            },
            {"actions": []},
        )

        watch_items = module.build_watch_items([context])

        self.assertEqual(context["health"], "watch")
        self.assertIn("Linux (WSL) is usable but still carries degraded runtime checks.", watch_items)

    def test_execution_smoke_failure_downgrades_context_and_surfaces_watch_item(self) -> None:
        module = _load_module()
        context = module.summarize_context(
            "linux_wsl",
            "Linux (WSL)",
            {
                "platform_summary": "Linux (WSL) · 6.6.87.2-microsoft-standard-WSL2 · x86_64 · Python 3.12.3",
                "checks": [
                    {"name": "ffmpeg", "status": "healthy"},
                    {"name": "vapoursynth", "status": "missing"},
                ],
                "warnings": [],
                "path_rules": [],
            },
            {"actions": []},
            execution_smoke={"status": "failed", "detail": "ffmpeg was not available"},
        )

        watch_items = module.build_watch_items([context])

        self.assertEqual(context["health"], "attention")
        self.assertEqual(context["execution_smoke"]["status"], "failed")
        self.assertIn("Linux (WSL) could not complete the lightweight execution smoke.", watch_items)

    def test_degraded_smoke_success_still_flags_incomplete_canonical_runtime(self) -> None:
        module = _load_module()
        context = module.summarize_context(
            "linux_wsl",
            "Linux (WSL)",
            {
                "platform_summary": "Linux (WSL) · 6.6.87.2-microsoft-standard-WSL2 · x86_64 · Python 3.12.3",
                "checks": [
                    {"name": "ffmpeg", "status": "healthy"},
                    {"name": "vapoursynth", "status": "missing"},
                ],
                "warnings": [],
                "path_rules": [],
            },
            {
                "actions": [
                    {
                        "action_id": "check:vapoursynth",
                        "category": "runtime",
                        "title": "Install VapourSynth",
                    }
                ]
            },
            execution_smoke={"status": "passed", "execution_mode": "degraded", "detail": "tiny degraded run passed"},
        )

        watch_items = module.build_watch_items([context])

        self.assertFalse(context["canonical_runtime_ready"])
        self.assertEqual(context["canonical_runtime_status"], "incomplete")
        self.assertIn(
            "Linux (WSL) passed a degraded smoke run, but the canonical runtime is still incomplete.",
            watch_items,
        )

    def test_non_actionable_missing_checks_do_not_downgrade_ready_state(self) -> None:
        module = _load_module()
        context = module.summarize_context(
            "windows_native",
            "Windows (native)",
            {
                "platform_summary": "Windows · 10 · AMD64 · Python 3.13.12",
                "checks": [
                    {"name": "trt", "status": "missing"},
                    {"name": "trt_rtx", "status": "missing"},
                    {"name": "model_dir:C:/Users/example/AppData/Local/UPSKAYLEDD/models", "status": "degraded"},
                ],
                "warnings": [],
                "path_rules": [],
            },
            {"actions": []},
            actionable_check_names={"ffmpeg", "ffprobe", "vapoursynth", "vsmlrt", "ffms2", "vspipe", "preview_cache_dir", "output_root"},
        )

        watch_items = module.build_watch_items([context])

        self.assertEqual(context["missing_check_count"], 2)
        self.assertEqual(context["degraded_check_count"], 1)
        self.assertEqual(context["actionable_missing_check_count"], 0)
        self.assertEqual(context["actionable_degraded_check_count"], 0)
        self.assertEqual(context["health"], "ready")
        self.assertEqual(
            watch_items,
            ["Native and collected secondary runtime contexts look aligned enough for the current release-hardening pass."],
        )

    def test_canonical_runtime_gaps_ignore_actionable_filtering(self) -> None:
        module = _load_module()
        context = module.summarize_context(
            "linux_wsl",
            "Linux (WSL)",
            {
                "platform_summary": "Linux (WSL) · 6.6.87.2-microsoft-standard-WSL2 · x86_64 · Python 3.12.3",
                "checks": [
                    {"name": "vapoursynth", "status": "missing"},
                    {"name": "ffmpeg", "status": "healthy"},
                ],
                "warnings": [],
                "path_rules": [],
            },
            {"actions": []},
            actionable_check_names={"ffmpeg"},
            execution_smoke={"status": "passed", "execution_mode": "degraded", "detail": "tiny degraded run passed"},
        )

        watch_items = module.build_watch_items([context])

        self.assertEqual(context["actionable_missing_check_count"], 0)
        self.assertFalse(context["canonical_runtime_ready"])
        self.assertEqual(context["canonical_runtime_status"], "incomplete")
        self.assertIn(
            "Linux (WSL) passed a degraded smoke run, but the canonical runtime is still incomplete.",
            watch_items,
        )

    def test_unavailable_native_context_still_participates_in_watch_items(self) -> None:
        module = _load_module()
        native = module.summarize_context(
            "windows_native",
            "Windows (native)",
            None,
            None,
            available=False,
            error="native failure",
        )
        wsl = module.summarize_context(
            "linux_wsl",
            "Linux (WSL)",
            {
                "platform_summary": "Linux (WSL) · 6.6.87.2-microsoft-standard-WSL2 · x86_64 · Python 3.12.3",
                "checks": [{"name": "ffmpeg", "status": "healthy"}],
                "warnings": [],
                "path_rules": [],
            },
            {"actions": []},
        )

        watch_items = module.build_watch_items([native, wsl])

        self.assertEqual(native["health"], "unavailable")
        self.assertIn("Windows (native) validation could not be collected automatically.", watch_items)
        self.assertTrue(any("Native Windows and Linux-side WSL currently differ in runtime readiness." == item for item in watch_items))

    def test_resolve_output_path_prefers_flag_and_rejects_duplicates(self) -> None:
        module = _load_module()
        parser = module.build_parser()
        args = parser.parse_args(["--output-json", "runtime/validation/custom.json"])

        output_path = module.resolve_output_path(args, parser)

        self.assertEqual(output_path.name, "custom.json")

        duplicate_args = parser.parse_args(["legacy.json", "--output-json", "flag.json"])
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            module.resolve_output_path(duplicate_args, parser)

    def test_main_writes_flagged_output_path_with_collection_metadata(self) -> None:
        module = _load_module()
        payload = {
            "generated_at_utc": "2026-04-16T00:00:00Z",
            "include_execution_smoke": False,
            "repo_root": str(module.ROOT),
            "contexts": [
                module.summarize_context(
                    "windows_native",
                    "Windows (native)",
                    {
                        "platform_summary": "Windows · 10 · AMD64 · Python 3.13.12",
                        "checks": [{"name": "ffmpeg", "status": "healthy"}],
                        "warnings": [],
                        "path_rules": [],
                    },
                    {"actions": []},
                )
            ],
            "watch_items": [
                "Native and collected secondary runtime contexts look aligned enough for the current release-hardening pass."
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "matrix.json"
            with mock.patch.object(module, "build_platform_validation_payload", return_value=payload):
                with redirect_stdout(io.StringIO()):
                    result = module.main(["--output-json", str(output_path)])

            self.assertEqual(result, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["repo_root"], str(module.ROOT))
            self.assertIn("generated_at_utc", payload)
            self.assertEqual(payload["contexts"][0]["context_id"], "windows_native")
            self.assertIn(
                "Native and collected secondary runtime contexts look aligned enough for the current release-hardening pass.",
                payload["watch_items"],
            )

    def test_collect_contexts_marks_windows_native_unavailable_on_non_windows_hosts(self) -> None:
        fake_config = mock.Mock()
        fake_config.runtime_actions.checks.keys.return_value = {"ffmpeg"}
        fake_config.app.scratch_dir = "runtime/scratch"
        wsl_payload = {
            "doctor": {
                "platform_summary": "Linux (WSL)",
                "checks": [{"name": "ffmpeg", "status": "healthy"}],
                "warnings": [],
                "path_rules": [],
            },
            "setup_plan": {"actions": []},
        }

        with (
            mock.patch.object(matrix_module, "load_app_config", return_value=fake_config),
            mock.patch.object(matrix_module.platform, "system", return_value="Linux"),
            mock.patch.object(matrix_module, "_native_payload") as native_payload,
            mock.patch.object(matrix_module, "_wsl_payload", return_value=wsl_payload),
        ):
            contexts = matrix_module.collect_contexts(Path("Z:/UPSKAYLEDD"))

        native_payload.assert_not_called()
        native = next(item for item in contexts if item["context_id"] == "windows_native")
        self.assertFalse(native["available"])
        self.assertIn("not running on a Windows host", native["error"])

    def test_main_passes_execution_smoke_flag_through_to_builder(self) -> None:
        module = _load_module()
        payload = {
            "generated_at_utc": "2026-04-16T00:00:00Z",
            "include_execution_smoke": True,
            "repo_root": str(module.ROOT),
            "contexts": [],
            "watch_items": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "matrix.json"
            with mock.patch.object(module, "build_platform_validation_payload", return_value=payload) as builder:
                with redirect_stdout(io.StringIO()):
                    result = module.main(["--output-json", str(output_path), "--include-execution-smoke"])

        self.assertEqual(result, 0)
        builder.assert_called_once_with(module.ROOT.resolve(), include_execution_smoke=True)

    def test_native_payload_timeout_reports_clear_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "src").mkdir()
            with mock.patch.object(
                matrix_module.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(["python"], timeout=matrix_module.SUBPROCESS_TIMEOUT_SECONDS),
            ):
                with self.assertRaises(RuntimeError) as raised:
                    matrix_module._native_payload(repo_root, "runtime/scratch")

        self.assertIn("timed out", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
