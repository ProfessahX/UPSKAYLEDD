from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from upskayledd.core import paths


class PathResolutionTests(unittest.TestCase):
    def test_runtime_temporary_directory_uses_workspace_root_by_default(self) -> None:
        with paths.RuntimeTemporaryDirectory("runtime/test-path-scratch", prefix="path-test-") as temp_dir:
            temp_path = Path(temp_dir)
            self.assertTrue(temp_path.exists())
            self.assertIn(str((Path(__file__).resolve().parents[2] / "runtime" / "test-path-scratch")).lower(), str(temp_path).lower())
        self.assertFalse(temp_path.exists())

    def test_runtime_paths_move_to_local_app_data_when_frozen(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_root = Path(temp_dir) / "bundle"
            bundle_root.mkdir()
            local_app_data = Path(temp_dir) / "localappdata"
            local_app_data.mkdir()
            with patch.object(paths.sys, "frozen", True, create=True):
                with patch.object(paths.sys, "_MEIPASS", str(bundle_root), create=True):
                    with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}, clear=False):
                        self.assertEqual(
                            str(paths.repo_root().resolve()).lower(),
                            str(bundle_root.resolve()).lower(),
                        )
                        self.assertEqual(
                            str(paths.resolve_repo_path("config").resolve()).lower(),
                            str((bundle_root / "config").resolve()).lower(),
                        )
                        self.assertEqual(
                            str(paths.resolve_runtime_path("runtime/output").resolve()).lower(),
                            str((local_app_data / "UPSKAYLEDD" / "runtime" / "output").resolve()).lower(),
                        )
                        with paths.RuntimeTemporaryDirectory("runtime/test-frozen-scratch", prefix="frozen-path-test-") as scratch_dir:
                            scratch_path = Path(scratch_dir)
                            self.assertTrue(scratch_path.exists())
                        self.assertIn(
                                str((local_app_data / "UPSKAYLEDD" / "runtime" / "test-frozen-scratch")).lower(),
                                str(scratch_path).lower(),
                            )
                        self.assertFalse(scratch_path.exists())

    def test_runtime_temporary_directory_cleanup_is_idempotent(self) -> None:
        with paths.RuntimeTemporaryDirectory("runtime/test-path-scratch", prefix="path-test-") as temp_dir:
            temp_path = Path(temp_dir)

        self.assertFalse(temp_path.exists())
        temp_dir_handle = paths.RuntimeTemporaryDirectory("runtime/test-path-scratch", prefix="path-test-")
        handle_path = Path(temp_dir_handle.name)
        temp_dir_handle.cleanup()
        temp_dir_handle.cleanup()
        self.assertFalse(handle_path.exists())

    def test_expand_config_path_translates_windows_env_paths_inside_wsl(self) -> None:
        with (
            patch.object(paths.os, "name", "posix"),
            patch.dict(paths.os.environ, {"WSL_DISTRO_NAME": "Ubuntu-24.04", "LOCALAPPDATA": r"C:\Users\TestUser\AppData\Local"}, clear=False),
        ):
            expanded = paths.expand_config_path("%LOCALAPPDATA%/UPSKAYLEDD/models")

        self.assertEqual(
            str(expanded),
            "/mnt/c/Users/TestUser/AppData/Local/UPSKAYLEDD/models",
        )


if __name__ == "__main__":
    unittest.main()
