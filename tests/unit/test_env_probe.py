from __future__ import annotations

import unittest
from unittest.mock import patch

from upskayledd.integrations.env_probe import classify_path_rules, detect_platform_context


class EnvProbeTests(unittest.TestCase):
    def test_classify_path_rules_marks_windows_drive_and_unc_paths(self) -> None:
        with patch("upskayledd.integrations.env_probe.os.name", "nt"):
            self.assertIn("windows_drive_letter", classify_path_rules(r"Z:\UPSKAYLEDD\runtime\output"))
            self.assertIn("windows_unc_path", classify_path_rules(r"\\server\share\media"))

    def test_classify_path_rules_marks_linux_case_sensitive_paths(self) -> None:
        with patch("upskayledd.integrations.env_probe.os.name", "posix"):
            self.assertEqual(classify_path_rules("/var/tmp/upskayledd"), ["linux_case_sensitive_paths"])

    def test_detect_platform_context_marks_wsl_cleanly(self) -> None:
        with patch("upskayledd.integrations.env_probe.os.name", "posix"):
            with patch("upskayledd.integrations.env_probe.platform.system", return_value="Linux"):
                with patch("upskayledd.integrations.env_probe.platform.release", return_value="6.6.0"):
                    with patch("upskayledd.integrations.env_probe.platform.machine", return_value="x86_64"):
                        with patch.dict(
                            "upskayledd.integrations.env_probe.os.environ",
                            {"WSL_DISTRO_NAME": "Ubuntu-24.04"},
                            clear=False,
                        ):
                            context = detect_platform_context()

        self.assertTrue(context["is_wsl"])
        self.assertEqual(context["environment_label"], "Linux (WSL)")
        self.assertEqual(context["path_style"], "linux")

    def test_detect_platform_context_marks_native_windows_cleanly(self) -> None:
        with patch("upskayledd.integrations.env_probe.os.name", "nt"):
            with patch("upskayledd.integrations.env_probe.platform.system", return_value="Windows"):
                with patch("upskayledd.integrations.env_probe.platform.release", return_value="11"):
                    with patch("upskayledd.integrations.env_probe.platform.machine", return_value="AMD64"):
                        with patch.dict("upskayledd.integrations.env_probe.os.environ", {}, clear=True):
                            context = detect_platform_context()

        self.assertFalse(context["is_wsl"])
        self.assertEqual(context["environment_label"], "Windows")
        self.assertEqual(context["path_style"], "windows")


if __name__ == "__main__":
    unittest.main()
