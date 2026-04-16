from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
PACKAGING_DIR = ROOT / "packaging"
if str(PACKAGING_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGING_DIR))

from windows_branding import prepare_branding_assets


class WindowsBrandingTests(unittest.TestCase):
    def test_prepare_branding_assets_generates_icon_and_copies_graphics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payload = prepare_branding_assets(Path(temp_dir))

            self.assertTrue(Path(payload["branding_dir"]).exists())
            self.assertTrue(Path(payload["icon_ico"]).exists())
            self.assertTrue(Path(payload["app_icon_png"]).exists())
            self.assertTrue(Path(payload["repo_header_png"]).exists())
            self.assertTrue(Path(payload["hero_graphic_png"]).exists())


if __name__ == "__main__":
    unittest.main()
