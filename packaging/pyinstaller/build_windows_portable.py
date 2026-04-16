from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGING_DIR = ROOT / "packaging"
if str(PACKAGING_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGING_DIR))

from windows_branding import prepare_branding_assets

SPEC_PATH = ROOT / "packaging" / "pyinstaller" / "upskayledd-desktop.spec"
BUILD_DIR = ROOT / "build" / "pyinstaller"
DIST_DIR = ROOT / "dist" / "pyinstaller"
VALIDATE_SCRIPT = ROOT / "packaging" / "pyinstaller" / "validate_windows_portable.py"


def build(clean: bool = False, validate: bool = False) -> int:
    if clean:
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
        shutil.rmtree(DIST_DIR, ignore_errors=True)
    prepare_branding_assets()
    command = [
        sys.executable,
        "-m",
        "PyInstaller.__main__",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        str(SPEC_PATH),
    ]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0 or not validate:
        return int(completed.returncode)
    validate_completed = subprocess.run(
        [
            sys.executable,
            str(VALIDATE_SCRIPT),
        ],
        cwd=ROOT,
        check=False,
    )
    return int(validate_completed.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the portable Windows PyInstaller bundle for UPSKAYLEDD.")
    parser.add_argument("--clean", action="store_true", help="Remove existing build/dist artifacts before building.")
    parser.add_argument("--validate", action="store_true", help="Run the portable-build validator after a successful build.")
    args = parser.parse_args(argv)
    return build(clean=args.clean, validate=args.validate)


if __name__ == "__main__":
    raise SystemExit(main())
