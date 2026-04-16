from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


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
        contexts = [
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
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "matrix.json"
            with mock.patch.object(module, "collect_contexts", return_value=contexts):
                with redirect_stdout(io.StringIO()):
                    result = module.main(["--output-json", str(output_path)])

            self.assertEqual(result, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["repo_root"], str(module.ROOT))
            self.assertIn("generated_at_utc", payload)
            self.assertEqual(payload["contexts"][0]["context_id"], "windows_native")


if __name__ == "__main__":
    unittest.main()
