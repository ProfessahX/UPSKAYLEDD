from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from upskayledd.platform_validation_matrix import _native_payload


class PlatformValidationMatrixInternalTests(unittest.TestCase):
    def test_native_payload_uses_runtime_scratch_exchange_root(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temp_dir:
            scratch_root = Path(temp_dir) / "matrix-scratch"
            recorded_output_paths: list[Path] = []

            def fake_run(
                command: list[str],
                *,
                cwd: Path,
                env: dict[str, str],
                check: bool,
                capture_output: bool,
                text: bool,
            ) -> subprocess.CompletedProcess[str]:
                self.assertEqual(cwd, repo_root)
                self.assertEqual(env["PYTHONPATH"], str(repo_root / "src"))
                output_path = Path(command[-1])
                recorded_output_paths.append(output_path)
                if output_path.name == "doctor.json":
                    payload = {"checks": [], "warnings": [], "path_rules": [], "platform_summary": "native"}
                else:
                    payload = {"actions": []}
                output_path.write_text(json.dumps(payload), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch("upskayledd.platform_validation_matrix.subprocess.run", side_effect=fake_run):
                payload = _native_payload(repo_root, scratch_root)

            self.assertEqual(payload["doctor"]["platform_summary"], "native")
            self.assertEqual(payload["setup_plan"]["actions"], [])
            self.assertEqual(len(recorded_output_paths), 2)
            for output_path in recorded_output_paths:
                self.assertTrue(str(output_path.resolve()).startswith(str(scratch_root.resolve())))

    def test_native_payload_surfaces_stderr_on_subprocess_failure(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temp_dir:
            scratch_root = Path(temp_dir) / "matrix-scratch"
            failure = subprocess.CalledProcessError(
                7,
                ["python", "-m", "upskayledd", "doctor"],
                stderr="native blew up",
            )
            with mock.patch("upskayledd.platform_validation_matrix.subprocess.run", side_effect=failure):
                with self.assertRaisesRegex(RuntimeError, "Native Windows validation command failed: native blew up"):
                    _native_payload(repo_root, scratch_root)


if __name__ == "__main__":
    unittest.main()
