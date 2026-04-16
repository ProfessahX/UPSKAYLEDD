from __future__ import annotations

import unittest
from unittest.mock import patch

from upskayledd.integrations.env_probe import classify_path_rules


class EnvProbeTests(unittest.TestCase):
    def test_classify_path_rules_marks_windows_drive_and_unc_paths(self) -> None:
        with patch("upskayledd.integrations.env_probe.os.name", "nt"):
            self.assertIn("windows_drive_letter", classify_path_rules(r"Z:\UPSKAYLEDD\runtime\output"))
            self.assertIn("windows_unc_path", classify_path_rules(r"\\server\share\media"))

    def test_classify_path_rules_marks_linux_case_sensitive_paths(self) -> None:
        with patch("upskayledd.integrations.env_probe.os.name", "posix"):
            self.assertEqual(classify_path_rules("/var/tmp/upskayledd"), ["linux_case_sensitive_paths"])


if __name__ == "__main__":
    unittest.main()
