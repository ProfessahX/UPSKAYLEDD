from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from upskayledd.platform_validation_matrix import SUBPROCESS_TIMEOUT_SECONDS, _native_payload


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
                timeout: int,
            ) -> subprocess.CompletedProcess[str]:
                self.assertEqual(cwd, repo_root)
                self.assertEqual(env["PYTHONPATH"], str(repo_root / "src"))
                self.assertEqual(timeout, SUBPROCESS_TIMEOUT_SECONDS)
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

    def test_native_payload_can_attach_execution_smoke(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temp_dir:
            scratch_root = Path(temp_dir) / "matrix-scratch"

            def fake_run(
                command: list[str],
                *,
                cwd: Path,
                env: dict[str, str] | None,
                check: bool,
                capture_output: bool,
                text: bool,
                timeout: int,
            ) -> subprocess.CompletedProcess[str]:
                self.assertEqual(cwd, repo_root)
                output_path = Path(command[-1])
                if output_path.name == "doctor.json":
                    payload = {"checks": [], "warnings": [], "path_rules": [], "platform_summary": "native"}
                    output_path.write_text(json.dumps(payload), encoding="utf-8")
                elif output_path.name == "setup.json":
                    output_path.write_text(json.dumps({"actions": []}), encoding="utf-8")
                elif output_path.name == "smoke-project.json":
                    output_path.write_text(json.dumps({"project": "ok"}), encoding="utf-8")
                elif "run" in command:
                    output_dir = Path(command[command.index("--output-dir") + 1])
                    output_dir.mkdir(parents=True, exist_ok=True)
                    (output_dir / "smoke.mp4").write_text("ok", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                mock.patch("upskayledd.platform_validation_matrix.shutil.which", return_value="ffmpeg"),
                mock.patch("upskayledd.platform_validation_matrix.subprocess.run", side_effect=fake_run),
            ):
                payload = _native_payload(repo_root, scratch_root, include_execution_smoke=True)

        self.assertEqual(payload["doctor"]["platform_summary"], "native")
        self.assertEqual(payload["execution_smoke"]["status"], "passed")
        self.assertEqual(payload["execution_smoke"]["output_container"], "mp4")


if __name__ == "__main__":
    unittest.main()
