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

from windows_branding import prepare_branding_assets, project_version


PORTABLE_BUILD_SCRIPT = ROOT / "packaging" / "pyinstaller" / "build_windows_portable.py"
INNO_SCRIPT = ROOT / "packaging" / "inno" / "upskayledd-desktop.iss"
PORTABLE_DIR = ROOT / "dist" / "pyinstaller" / "upskayledd-desktop"
INSTALLER_OUTPUT_DIR = ROOT / "dist" / "installer"


def find_iscc() -> Path | None:
    local_programs = Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe"
    candidates = [
        shutil.which("ISCC.exe"),
        shutil.which("iscc.exe"),
        Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
        Path("C:/Program Files/Inno Setup 6/ISCC.exe"),
        local_programs,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return path
    return None


def build(clean: bool = False, skip_portable: bool = False, portable_validate: bool = True) -> int:
    iscc = find_iscc()
    if iscc is None:
        print("Inno Setup compiler not found. Install JRSoftware.InnoSetup first.")
        return 1

    if not skip_portable:
        command = [sys.executable, str(PORTABLE_BUILD_SCRIPT)]
        if clean:
            command.append("--clean")
        if portable_validate:
            command.append("--validate")
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode != 0:
            return int(completed.returncode)

    if not PORTABLE_DIR.exists():
        print(f"Portable bundle not found at {PORTABLE_DIR}. Build the portable app first.")
        return 1

    branding = prepare_branding_assets()
    INSTALLER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    version = project_version()
    command = [
        str(iscc),
        str(INNO_SCRIPT),
        f"/DAppVersion={version}",
        f"/DPortableDir={PORTABLE_DIR}",
        f"/DOutputDir={INSTALLER_OUTPUT_DIR}",
        f"/DBrandingDir={branding['branding_dir']}",
        f"/DLicenseFile={ROOT / 'LICENSE'}",
    ]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        return int(completed.returncode)

    expected = INSTALLER_OUTPUT_DIR / f"UPSKAYLEDD-Setup-{version}.exe"
    if not expected.exists():
        print(f"Inno Setup reported success, but the installer was not created at {expected}.")
        return 1
    print(f"Installer created at {expected}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Windows installer for UPSKAYLEDD using Inno Setup.")
    parser.add_argument("--clean", action="store_true", help="Clean and rebuild the portable bundle before building the installer.")
    parser.add_argument(
        "--skip-portable",
        action="store_true",
        help="Skip rebuilding the portable PyInstaller bundle and package the current dist/pyinstaller output.",
    )
    parser.add_argument(
        "--no-portable-validate",
        action="store_true",
        help="Skip the portable offscreen validation step when rebuilding the portable bundle.",
    )
    args = parser.parse_args(argv)
    return build(
        clean=args.clean,
        skip_portable=args.skip_portable,
        portable_validate=not args.no_portable_validate,
    )


if __name__ == "__main__":
    raise SystemExit(main())
