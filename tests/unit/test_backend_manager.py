from __future__ import annotations

import unittest

from upskayledd.backend_manager import BackendManager
from upskayledd.config import load_app_config
from upskayledd.integrations.env_probe import ToolStatus


class BackendManagerTests(unittest.TestCase):
    def test_prefers_nvidia_when_stack_is_available(self) -> None:
        config = load_app_config()
        env = {
            "python": ToolStatus("python", True, "3.12"),
            "ffmpeg": ToolStatus("ffmpeg", True, "ffmpeg"),
            "ffprobe": ToolStatus("ffprobe", True, "ffprobe"),
            "vspipe": ToolStatus("vspipe", True, "vspipe"),
            "vapoursynth": ToolStatus("vapoursynth", True, "installed"),
            "vsmlrt": ToolStatus("vsmlrt", True, "installed"),
            "ffms2": ToolStatus("ffms2", True, "loaded"),
            "vsmlrt_ncnn": ToolStatus("vsmlrt_ncnn", True, "loaded"),
            "vsmlrt_trt": ToolStatus("vsmlrt_trt", True, "loaded"),
            "vsmlrt_trt_rtx": ToolStatus("vsmlrt_trt_rtx", False, "not loaded"),
            "nvidia": ToolStatus("nvidia", True, "RTX"),
            "vulkan": ToolStatus("vulkan", True, "sdk"),
        }
        selection = BackendManager(config, env).choose_backend()
        self.assertEqual(selection.backend_id, "tensorrt_nvidia")

    def test_doctor_sanitizes_python_executable_path(self) -> None:
        config = load_app_config()
        payload = BackendManager(config).doctor().to_dict()

        python_executable = str(payload.get("platform_context", {}).get("python_executable", ""))
        self.assertTrue(python_executable)
        self.assertNotIn("\\", python_executable)
        self.assertNotIn("/", python_executable)


if __name__ == "__main__":
    unittest.main()
