from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from upskayledd.platform_validation_matrix import (  # noqa: E402
    build_platform_validation_payload,
    build_watch_items,
    collect_contexts,
    summarize_context,
    windows_to_wsl_path,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect native Windows and Linux-side WSL runtime readiness into one validation artifact."
    )
    parser.add_argument(
        "output_path",
        nargs="?",
        help="Optional legacy positional output path for the JSON artifact.",
    )
    parser.add_argument(
        "--output-json",
        dest="output_json",
        help="Write the validation matrix JSON to this path.",
    )
    parser.add_argument(
        "--repo-root",
        default=str(ROOT),
        help="Repository root used for native and WSL collection.",
    )
    parser.add_argument(
        "--include-execution-smoke",
        action="store_true",
        help="Also run a tiny degraded recommend/run smoke lane in each collected runtime context.",
    )
    return parser


def resolve_output_path(args: argparse.Namespace, parser: argparse.ArgumentParser) -> Path:
    if args.output_json and args.output_path:
        parser.error("Use either the positional output path or --output-json, not both.")
    raw_output = args.output_json or args.output_path
    if raw_output:
        return Path(raw_output).resolve()
    return ROOT / "runtime" / "validation" / "platform_validation_matrix.json"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    output_path = resolve_output_path(args, parser)
    payload = build_platform_validation_payload(
        repo_root,
        include_execution_smoke=args.include_execution_smoke,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
