from __future__ import annotations

import argparse
import json
import shutil
import tomllib
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - exercised in packaging environments
    Image = None


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "branding"


def project_version(pyproject_path: Path | None = None) -> str:
    payload = tomllib.loads((pyproject_path or ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(payload["project"]["version"])


def prepare_branding_assets(output_dir: Path | None = None) -> dict[str, str]:
    if Image is None:
        raise RuntimeError("Pillow is required to generate Windows branding assets. Install the desktop-build extra first.")

    destination = (output_dir or DEFAULT_OUTPUT_DIR).resolve()
    destination.mkdir(parents=True, exist_ok=True)

    icon_source = ROOT / "icon.png"
    header_source = ROOT / "LOGO-HEADER.png"
    hero_source = ROOT / "Shitposting_pitch_refined.png"
    missing = [path for path in (icon_source, header_source, hero_source) if not path.exists()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Missing required branding assets: {missing_text}")

    icon_output = destination / "upskayledd.ico"
    with Image.open(icon_source) as image:
        image.convert("RGBA").save(
            icon_output,
            format="ICO",
            sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
        )

    copied_assets = {
        "app_icon_png": shutil.copy2(icon_source, destination / icon_source.name),
        "repo_header_png": shutil.copy2(header_source, destination / header_source.name),
        "hero_graphic_png": shutil.copy2(hero_source, destination / hero_source.name),
    }

    return {
        "version": project_version(),
        "branding_dir": str(destination),
        "icon_ico": str(icon_output),
        **{key: str(Path(value)) for key, value in copied_assets.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare shared Windows branding assets for portable and installer builds.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where generated branding assets should be written.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the generated asset paths as JSON.",
    )
    args = parser.parse_args(argv)

    payload = prepare_branding_assets(Path(args.output_dir))
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
