from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DIST_DIR = ROOT / "dist" / "pyinstaller" / "upskayledd-desktop"


def validate(dist_dir: Path, launch_seconds: int = 5) -> int:
    exe_path = dist_dir / "upskayledd-desktop.exe"
    required_paths = [
        exe_path,
        dist_dir / "_internal" / "config" / "defaults.toml",
        dist_dir / "_internal" / "config" / "desktop_ui.toml",
        dist_dir / "_internal" / "config" / "runtime_actions.toml",
        dist_dir / "_internal" / "PySide6" / "plugins" / "platforms" / "qwindows.dll",
        dist_dir / "_internal" / "PySide6" / "plugins" / "platforms" / "qoffscreen.dll",
        dist_dir / "_internal" / "PySide6" / "plugins" / "multimedia" / "ffmpegmediaplugin.dll",
    ]

    missing = [path for path in required_paths if not path.exists()]
    if missing:
        for path in missing:
            print(f"Missing required build artifact: {path}")
        return 1

    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    process = subprocess.Popen([str(exe_path)], env=env)  # noqa: S603
    try:
        time.sleep(max(1, launch_seconds))
        if process.poll() is not None:
            print(f"Portable app exited early with code {process.returncode}.")
            return 1
        print(f"Portable app booted successfully for {launch_seconds} second(s) in offscreen mode.")
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the UPSKAYLEDD portable PyInstaller build.")
    parser.add_argument(
        "--dist-dir",
        default=str(DIST_DIR),
        help="Portable build directory containing upskayledd-desktop.exe.",
    )
    parser.add_argument(
        "--launch-seconds",
        type=int,
        default=5,
        help="How long to keep the portable app alive in offscreen mode before treating boot as healthy.",
    )
    args = parser.parse_args(argv)
    return validate(Path(args.dist_dir), launch_seconds=args.launch_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
