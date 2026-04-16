from __future__ import annotations

import argparse
import json
from pathlib import Path


def checkpoint_paths(repo_root: Path) -> tuple[Path, Path]:
    checkpoint_dir = repo_root / "runtime" / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    return checkpoint_dir / "LATEST.md", checkpoint_dir / "LATEST.json"


def load_state(json_path: Path) -> dict:
    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8"))
    return {"current_track": "", "tracks": {}}


def render_markdown(state: dict) -> str:
    lines: list[str] = []
    current = state.get("current_track", "")
    if current and current in state["tracks"]:
        track = state["tracks"][current]
        next_step = track.get("next") or track.get("next_cmd", "")
        lines.extend(
            [
                "## CURRENT",
                f"- Track: {current}",
                f"- Step: {track['step']}",
                f"- Note: {track['note']}",
                f"- Branch: {track['branch']}",
                f"- Head: {track['head']}",
                f"- Next: {next_step}",
                f"- Next command: `{track['next_cmd']}`",
                f"- Validations: {'; '.join(track['validations'])}",
                "",
            ]
        )

    for track_name, track in state.get("tracks", {}).items():
        next_step = track.get("next") or track.get("next_cmd", "")
        lines.extend(
            [
                f"## {track_name}",
                f"- Step: {track['step']}",
                f"- Note: {track['note']}",
                f"- Branch: {track['branch']}",
                f"- Head: {track['head']}",
                f"- Next: {next_step}",
                f"- Next command: `{track['next_cmd']}`",
                f"- Validations: {'; '.join(track['validations'])}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def save_state(repo_root: Path, state: dict) -> None:
    md_path, json_path = checkpoint_paths(repo_root)
    json_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(state), encoding="utf-8")


def command_resume(args: argparse.Namespace) -> int:
    _, json_path = checkpoint_paths(Path(args.repo_root).resolve())
    state = load_state(json_path)
    track = state["tracks"].get(args.track)
    if not track:
        print(f"Track not found: {args.track}")
        return 1
    next_step = track.get("next") or track.get("next_cmd", "")
    print(f"Track: {args.track}")
    print(f"Step: {track['step']}")
    print(f"Note: {track['note']}")
    print(f"Next: {next_step}")
    print(f"Next command: {track['next_cmd']}")
    return 0


def command_snapshot(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    _, json_path = checkpoint_paths(repo_root)
    state = load_state(json_path)
    state.setdefault("tracks", {})
    state["tracks"][args.track] = {
        "step": args.step,
        "note": args.note,
        "branch": args.branch,
        "head": args.head,
        "next": args.next,
        "next_cmd": args.next_cmd,
        "validations": args.validation or [],
    }
    if not args.no_set_current:
        state["current_track"] = args.track
    save_state(repo_root, state)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)

    resume = subparsers.add_parser("resume")
    resume.add_argument("--track", required=True)
    resume.set_defaults(func=command_resume)

    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("--track", required=True)
    snapshot.add_argument("--step", required=True)
    snapshot.add_argument("--note", required=True)
    snapshot.add_argument("--branch", required=True)
    snapshot.add_argument("--head", required=True)
    snapshot.add_argument("--next", required=True)
    snapshot.add_argument("--next-cmd", required=True)
    snapshot.add_argument("--validation", action="append", default=[])
    snapshot.add_argument("--no-set-current", action="store_true")
    snapshot.set_defaults(func=command_snapshot)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
