from __future__ import annotations

import unittest

from upskayledd.config import load_app_config
from upskayledd.runtime_guidance import RuntimeGuidanceBuilder


class RuntimeGuidanceTests(unittest.TestCase):
    def test_wsl_context_action_requires_runtime_issue(self) -> None:
        builder = RuntimeGuidanceBuilder(load_app_config())

        actions = builder.build(
            doctor_report={
                "checks": [
                    {"name": "output_root", "status": "missing", "detail": "not writable"},
                    {"name": "preview_cache_dir", "status": "degraded", "detail": "slow"},
                ],
                "platform_context": {"is_wsl": True},
            },
            model_pack_payload={"packs": []},
        )

        self.assertFalse(any(action.action_id == "context:wsl_environment" for action in actions))

    def test_wsl_context_action_survives_max_action_trimming(self) -> None:
        builder = RuntimeGuidanceBuilder(load_app_config())

        actions = builder.build(
            doctor_report={
                "checks": [
                    {"name": "ffmpeg", "status": "missing", "detail": "not found"},
                    {"name": "ffprobe", "status": "missing", "detail": "not found"},
                    {"name": "vapoursynth", "status": "missing", "detail": "not installed"},
                    {"name": "vsmlrt", "status": "missing", "detail": "not installed"},
                    {"name": "ffms2", "status": "missing", "detail": "not loaded"},
                    {"name": "vspipe", "status": "missing", "detail": "not found"},
                ],
                "platform_context": {"is_wsl": True},
            },
            model_pack_payload={"packs": []},
        )

        self.assertEqual(len(actions), builder.config.runtime_actions.max_actions)
        self.assertTrue(any(action.action_id == "context:wsl_environment" for action in actions))


if __name__ == "__main__":
    unittest.main()
