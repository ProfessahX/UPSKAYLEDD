from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[2] / "tools" / "context_checkpoint.py"
    spec = importlib.util.spec_from_file_location("context_checkpoint", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ContextCheckpointTests(unittest.TestCase):
    def test_resume_uses_next_cmd_when_next_missing(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            checkpoint_dir = repo_root / "runtime" / "checkpoints"
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            (checkpoint_dir / "LATEST.json").write_text(
                json.dumps(
                    {
                        "current_track": "TEST WORK",
                        "tracks": {
                            "TEST WORK": {
                                "step": "Testing",
                                "note": "Resume should not crash.",
                                "branch": "not-a-git-repo",
                                "head": "no-head",
                                "next_cmd": "python tools/context_checkpoint.py resume",
                                "validations": [],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            exit_code = module.command_resume(Namespace(repo_root=str(repo_root), track="TEST WORK"))
            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
