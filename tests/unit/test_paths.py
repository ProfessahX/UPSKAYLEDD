from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from upskayledd.core import paths


class PathResolutionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
