from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
