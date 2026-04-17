from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from upskayledd.app_service import AppService
from upskayledd.manifest_writer import read_artifact, write_artifact
from upskayledd.models import ComparisonMode, FidelityMode, ProjectManifest


def _print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _write_optional_json(path: str | None, payload: dict[str, Any]) -> None:
    if path:
        write_artifact(path, payload)


def _coerce_value(raw: str) -> Any:
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _parse_key_value_pairs(items: list[str] | None) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"Stage setting must be key=value, got: {item}")
        key, value = item.split("=", maxsplit=1)
        parsed[key.strip()] = _coerce_value(value.strip())
    return parsed


def _build_output_policy_overrides(args: argparse.Namespace) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    mapping = {
        "encode_profile": "encode_profile_id",
        "output_container": "container",
        "video_codec": "video_codec",
        "video_preset": "video_preset",
        "video_crf": "video_crf",
        "video_pixel_format": "video_pixel_format",
        "audio_codec": "audio_codec",
        "audio_bitrate_kbps": "audio_bitrate_kbps",
        "subtitle_codec": "subtitle_codec",
    }
    for arg_name, policy_key in mapping.items():
        value = getattr(args, arg_name, None)
        if value not in (None, ""):
            overrides[policy_key] = value
    if getattr(args, "drop_chapters", False):
        overrides["preserve_chapters"] = False
    return overrides


def command_doctor(args: argparse.Namespace) -> int:
    payload = AppService(args.config_dir).doctor_report()
    _write_optional_json(args.json_output, payload)
    _print_json(payload)
    return 0


def command_list_model_packs(args: argparse.Namespace) -> int:
    payload = AppService(args.config_dir).list_model_packs()
    _write_optional_json(args.json_output, payload)
    _print_json(payload)
    return 0


def command_list_encode_profiles(args: argparse.Namespace) -> int:
    payload = AppService(args.config_dir).list_encode_profiles()
    _write_optional_json(args.json_output, payload)
    for profile in payload["profiles"]:
        default_marker = " (default)" if profile["id"] == payload["default_profile_id"] else ""
        summary = (
            f"{profile['label']}{default_marker}: {profile['container']} / "
            f"{profile['video_codec']} / CRF {profile['video_crf']} / audio {profile['audio_codec']}"
        )
        print(summary)
        print(f"  {profile['description']}")
        fact_labels = [str(item.get("label", "")).strip() for item in profile.get("facts", []) if str(item.get("label", "")).strip()]
        if fact_labels:
            print(f"  Facts: {' | '.join(fact_labels[:4])}")
    return 0


def command_setup_plan(args: argparse.Namespace) -> int:
    service = AppService(args.config_dir)
    doctor_report = service.doctor_report()
    payload = {
        "platform_summary": doctor_report.get("platform_summary", ""),
        "actions": service.runtime_action_plan(doctor_report=doctor_report),
    }
    _write_optional_json(args.json_output, payload)
    platform_summary = str(payload.get("platform_summary", "")).strip()
    if platform_summary:
        print(f"Runtime context: {platform_summary}")
    if not payload["actions"]:
        print("No immediate setup actions. The current runtime looks ready for normal use.")
        return 0
    for index, action in enumerate(payload["actions"], start=1):
        print(f"{index}. {action['title']}")
        print(f"   {action['detail']}")
    return 0


def command_paths(args: argparse.Namespace) -> int:
    payload = AppService(args.config_dir).runtime_locations()
    _write_optional_json(args.json_output, payload)
    for location in payload["locations"]:
        state = "ready" if location.get("exists") else "planned"
        print(f"{location['location_id']}: {location['path']} ({state})")
    return 0


def command_platform_matrix(args: argparse.Namespace) -> int:
    payload = AppService(args.config_dir).platform_validation_matrix(
        repo_root=args.repo_root,
        include_execution_smoke=args.include_execution_smoke,
    )
    _write_optional_json(args.json_output, payload)
    for context in payload["contexts"]:
        summary = str(context.get("platform_summary", "")).strip() or str(context.get("display_name", "Context"))
        health = str(context.get("health", "unknown")).strip()
        print(f"{summary}: {health}")
        if not context.get("available", True):
            error = str(context.get("error", "")).strip()
            if error:
                print(f"  {error}")
            continue
        missing = int(context.get("missing_check_count", 0) or 0)
        degraded = int(context.get("degraded_check_count", 0) or 0)
        actions = int(context.get("action_count", 0) or 0)
        print(f"  Missing checks: {missing} | Degraded checks: {degraded} | Setup actions: {actions}")
        execution_smoke = dict(context.get("execution_smoke", {}))
        smoke_status = str(execution_smoke.get("status", "")).strip()
        if smoke_status:
            print(f"  Execution smoke: {smoke_status}")
            smoke_detail = str(execution_smoke.get("detail", "")).strip()
            if smoke_detail:
                print(f"    {smoke_detail}")
        for action in context.get("actions", []):
            if not isinstance(action, dict):
                continue
            title = str(action.get("title", "")).strip()
            detail = str(action.get("detail", "")).strip()
            if title:
                print(f"  - {title}")
            if detail:
                print(f"    {detail}")
    if payload["watch_items"]:
        print("Watch items:")
        for item in payload["watch_items"]:
            print(f"- {item}")
    return 0


def command_compare_media(args: argparse.Namespace) -> int:
    payload = AppService(args.config_dir).compare_media_files(
        args.input_path,
        args.output_path,
        encode_profile_id=args.encode_profile,
        preserve_chapters=not args.drop_chapters,
    )
    _write_optional_json(args.json_output, payload)
    print(f"Input: {payload['input_path']}")
    print(f"Output: {payload['output_path']}")
    comparison = dict(payload.get("comparison", {}))
    if comparison:
        size_ratio = comparison.get("size_ratio")
        resolution_scale = comparison.get("resolution_scale")
        if size_ratio not in (None, ""):
            print(f"Size ratio: {float(size_ratio):.2f}x")
        if resolution_scale not in (None, ""):
            print(f"Resolution scale: {float(resolution_scale):.2f}x")
        guidance = list(comparison.get("guidance", []))
        if guidance:
            print("Guidance:")
            for item in guidance:
                print(f"- {item}")
    return 0


def command_install_model_pack(args: argparse.Namespace) -> int:
    payload = AppService(args.config_dir).install_model_pack(args.pack_id, force=args.force)
    _write_optional_json(args.json_output, payload)
    _print_json(payload)
    return 0


def command_inspect(args: argparse.Namespace) -> int:
    reports = AppService(args.config_dir).inspect_target(args.target)
    payload = {"reports": reports}
    _write_optional_json(args.json_output, payload)
    for report in reports:
        print(f"\n[{Path(report['source_path']).name}]")
        for line in report["summary"]:
            print(f"- {line}")
        if report["warnings"]:
            print("- Warnings: " + "; ".join(report["warnings"]))
    return 0


def command_recommend(args: argparse.Namespace) -> int:
    service = AppService(args.config_dir)
    payload = service.recommend_target(
        args.target,
        custom_model_paths=args.custom_model_path or [],
        hook_references=args.hook_reference or [],
        output_policy_overrides=_build_output_policy_overrides(args),
    )
    reports = payload["inspection_reports"]
    manifest = ProjectManifest.from_dict(payload["project_manifest"])
    backend = payload["backend_selection"]
    delivery_guidance = dict(payload.get("delivery_guidance", {}))
    if not reports:
        print("No supported media files found.")
        return 1
    _write_optional_json(args.json_output, payload)
    if args.project_output:
        write_artifact(args.project_output, manifest.to_dict())
    print(f"Selected profile: {manifest.selected_profile_id}")
    print(f"Backend plan: {backend['backend_id']} ({backend['runtime']})")
    if manifest.warnings:
        print("Warnings:")
        for warning in manifest.warnings:
            print(f"- {warning}")
    selected_messages = list(delivery_guidance.get("selected_messages", []))
    if selected_messages:
        print("Delivery guidance:")
        for message in selected_messages:
            print(f"- {message}")
    print(f"Sources: {len(manifest.source_files)}")
    return 0


def command_preview(args: argparse.Namespace) -> int:
    service = AppService(args.config_dir)
    stage_settings = _parse_key_value_pairs(args.stage_setting)
    request = service.preview_engine.create_request(
        source_path=args.source_path,
        stage_id=args.stage,
        comparison_mode=ComparisonMode(args.comparison_mode),
        stage_settings=stage_settings,
        sample_start_seconds=args.start,
        sample_duration_seconds=args.duration,
        fidelity_mode_request=FidelityMode(args.fidelity_mode),
        backend_id=args.backend_id,
        model_ids=args.model_id or [],
    )
    if args.request_output:
        write_artifact(args.request_output, request.to_dict())
    result = service.prepare_preview(
        source_path=args.source_path,
        stage_id=args.stage,
        comparison_mode=ComparisonMode(args.comparison_mode),
        stage_settings=stage_settings,
        sample_start_seconds=args.start,
        sample_duration_seconds=args.duration,
        fidelity_mode=FidelityMode(args.fidelity_mode),
        backend_id=args.backend_id,
        model_ids=args.model_id or [],
    )
    _write_optional_json(args.json_output, result.to_dict())
    print(f"Preview cache key: {result.cache_key}")
    print(f"Preview fidelity: {result.fidelity_mode.value}")
    print(f"Metadata path: {result.metadata_path}")
    if result.warnings:
        for warning in result.warnings:
            print(f"- {warning}")
    return 0


def command_run(args: argparse.Namespace) -> int:
    service = AppService(args.config_dir)
    manifest = ProjectManifest.from_dict(read_artifact(args.project_manifest))
    manifest.output_policy = service.encode_mux_planner.apply_output_overrides(
        manifest.output_policy,
        _build_output_policy_overrides(args),
    )
    backend_selection, jobs = service.run_project(
        manifest,
        output_dir=args.output_dir,
        execute=args.execute,
        execute_degraded=args.execute_degraded,
    )
    print(f"Backend plan: {backend_selection['backend_id']} ({backend_selection['runtime']})")
    if args.execute:
        completed = [job for job in jobs if job.status.value == "completed"]
        failed = [job for job in jobs if job.status.value == "failed"]
        print(f"Executed pipeline for {len(jobs)} job(s): {len(completed)} completed, {len(failed)} failed.")
        return 0 if not failed else 1

    if args.execute_degraded:
        completed = [job for job in jobs if job.status.value == "completed"]
        failed = [job for job in jobs if job.status.value == "failed"]
        print(f"Executed degraded pipeline for {len(jobs)} job(s): {len(completed)} completed, {len(failed)} failed.")
        return 0 if not failed else 1

    print(f"Queued {len(jobs)} job(s).")
    print("Run metadata and queue state were created. Use --execute for the best available path or --execute-degraded for the FFmpeg fallback path.")
    return 0


def command_resume(args: argparse.Namespace) -> int:
    service = AppService(args.config_dir)
    record = service.resume_job(
        job_id=args.job_id,
        execute=args.execute,
        execute_degraded=args.execute_degraded,
    )
    if record is None:
        print(f"Job not found: {args.job_id}")
        return 1
    if args.execute or args.execute_degraded:
        print(f"Job {record.job_id} finished with status {record.status.value}.")
        return 0 if record.status.value == "completed" else 1
    print(f"Job {record.job_id} set to {record.status.value}.")
    return 0


def command_export_manifest(args: argparse.Namespace) -> int:
    payload = read_artifact(args.project_manifest)
    if args.output:
        write_artifact(args.output, payload)
    else:
        _print_json(payload)
    return 0


def command_export_support_bundle(args: argparse.Namespace) -> int:
    payload = AppService(args.config_dir).export_support_bundle(
        output_path=args.output,
        include_full_paths=args.include_full_paths,
        session_state_key=args.session_state_key,
        selected_job_id=args.job_id,
    )
    _write_optional_json(args.json_output, payload)
    print(f"Support bundle: {payload['bundle_path']}")
    print(f"Entries: {', '.join(payload['entries'])}")
    print("Full paths included." if payload["include_full_paths"] else "Paths were redacted in the exported bundle.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="upskayledd")
    parser.add_argument("--config-dir", default=None, help="Optional config directory override.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Validate the local environment.")
    doctor.add_argument("--json-output", help="Optional path to write the doctor report.")
    doctor.set_defaults(func=command_doctor)

    list_model_packs = subparsers.add_parser("list-model-packs", help="List curated model packs and whether they are installed.")
    list_model_packs.add_argument("--json-output", help="Optional path to write model-pack status.")
    list_model_packs.set_defaults(func=command_list_model_packs)

    list_encode_profiles = subparsers.add_parser(
        "list-encode-profiles",
        help="List configured delivery profiles and the codecs/containers they resolve to.",
    )
    list_encode_profiles.add_argument("--json-output", help="Optional path to write encode-profile details.")
    list_encode_profiles.set_defaults(func=command_list_encode_profiles)

    setup_plan = subparsers.add_parser("setup-plan", help="Show the highest-priority runtime setup actions for this machine.")
    setup_plan.add_argument("--json-output", help="Optional path to write the setup action plan.")
    setup_plan.set_defaults(func=command_setup_plan)

    runtime_paths = subparsers.add_parser("paths", help="Show the runtime/output/support/model locations this install will use.")
    runtime_paths.add_argument("--json-output", help="Optional path to write resolved runtime locations.")
    runtime_paths.set_defaults(func=command_paths)

    platform_matrix = subparsers.add_parser(
        "platform-matrix",
        help="Collect native Windows and Linux-side WSL runtime readiness into one validation snapshot.",
    )
    platform_matrix.add_argument("--repo-root", default=None, help="Optional repo root override for native and WSL collection.")
    platform_matrix.add_argument(
        "--include-execution-smoke",
        action="store_true",
        help="Also run a tiny degraded recommend/run smoke lane inside each collected runtime context.",
    )
    platform_matrix.add_argument("--json-output", help="Optional path to write the platform validation matrix.")
    platform_matrix.set_defaults(func=command_platform_matrix)

    compare_media = subparsers.add_parser(
        "compare-media",
        help="Compare two media files and emit normalized before/after metrics plus plain-language guidance.",
    )
    compare_media.add_argument("input_path", help="Source or before file.")
    compare_media.add_argument("output_path", help="Output or after file.")
    compare_media.add_argument("--encode-profile", help="Optional delivery profile id to guide compatibility/archive messaging.")
    compare_media.add_argument("--drop-chapters", action="store_true", help="Do not warn about chapter loss in the comparison guidance.")
    compare_media.add_argument("--json-output", help="Optional path to write the comparison payload.")
    compare_media.set_defaults(func=command_compare_media)

    install_model_pack = subparsers.add_parser("install-model-pack", help="Download and extract a curated model pack.")
    install_model_pack.add_argument("pack_id", help="Model pack id or 'recommended'.")
    install_model_pack.add_argument("--force", action="store_true", help="Reinstall even if the pack already looks present.")
    install_model_pack.add_argument("--json-output", help="Optional path to write install results.")
    install_model_pack.set_defaults(func=command_install_model_pack)

    inspect = subparsers.add_parser("inspect", help="Inspect one file or a directory of media files.")
    inspect.add_argument("target")
    inspect.add_argument("--json-output", help="Optional path to write inspection output.")
    inspect.set_defaults(func=command_inspect)

    recommend = subparsers.add_parser("recommend", help="Inspect a source and build a project manifest recommendation.")
    recommend.add_argument("target")
    recommend.add_argument("--json-output", help="Optional path to write the combined recommendation payload.")
    recommend.add_argument("--project-output", help="Optional path to write the project manifest.")
    recommend.add_argument("--custom-model-path", action="append", help="Custom model path override.", default=[])
    recommend.add_argument("--hook-reference", action="append", help="Optional in-process hook reference.", default=[])
    recommend.add_argument("--encode-profile", help="Encode profile id from config/encode_profiles.toml.")
    recommend.add_argument("--output-container", help="Container override such as mkv, mp4, or mov.")
    recommend.add_argument("--video-codec", help="Video codec override such as libx265 or libx264.")
    recommend.add_argument("--video-preset", help="Encoder preset override.")
    recommend.add_argument("--video-crf", type=int, help="Video CRF override.")
    recommend.add_argument("--video-pixel-format", help="Video pixel format override.")
    recommend.add_argument("--audio-codec", help="Audio codec override such as copy or aac.")
    recommend.add_argument("--audio-bitrate-kbps", type=int, help="Audio bitrate override when transcoding.")
    recommend.add_argument("--subtitle-codec", help="Subtitle codec override such as copy, mov_text, or none.")
    recommend.add_argument("--drop-chapters", action="store_true", help="Disable chapter preservation for the generated manifest.")
    recommend.set_defaults(func=command_recommend)

    preview = subparsers.add_parser("preview", help="Prepare preview request metadata and cache records.")
    preview.add_argument("source_path")
    preview.add_argument("--stage", default="inspect")
    preview.add_argument("--comparison-mode", choices=[mode.value for mode in ComparisonMode], default=ComparisonMode.SLIDER_WIPE.value)
    preview.add_argument("--start", type=float, default=0.0)
    preview.add_argument("--duration", type=float)
    preview.add_argument("--fidelity-mode", choices=[mode.value for mode in FidelityMode], default=FidelityMode.APPROXIMATE.value)
    preview.add_argument("--backend-id", default="planning_only")
    preview.add_argument("--model-id", action="append", default=[])
    preview.add_argument("--stage-setting", action="append", default=[], help="Stage setting override in key=value form.")
    preview.add_argument("--request-output", help="Optional path to write the preview request.")
    preview.add_argument("--json-output", help="Optional path to write the preview result.")
    preview.set_defaults(func=command_preview)

    run = subparsers.add_parser("run", help="Queue a project manifest for execution planning.")
    run.add_argument("project_manifest")
    run.add_argument("--output-dir", help="Optional directory for queued run-manifest artifacts.")
    run.add_argument("--execute", action="store_true", help="Execute the best available path, preferring the canonical VapourSynth runner.")
    run.add_argument("--execute-degraded", action="store_true", help="Execute the FFmpeg degraded fallback path.")
    run.add_argument("--encode-profile", help="Override the manifest encode profile id for this run.")
    run.add_argument("--output-container", help="Override the output container for this run.")
    run.add_argument("--video-codec", help="Override the video codec for this run.")
    run.add_argument("--video-preset", help="Override the encoder preset for this run.")
    run.add_argument("--video-crf", type=int, help="Override the video CRF for this run.")
    run.add_argument("--video-pixel-format", help="Override the video pixel format for this run.")
    run.add_argument("--audio-codec", help="Override the audio codec for this run.")
    run.add_argument("--audio-bitrate-kbps", type=int, help="Override the audio bitrate for this run when transcoding.")
    run.add_argument("--subtitle-codec", help="Override the subtitle codec for this run.")
    run.add_argument("--drop-chapters", action="store_true", help="Disable chapter preservation for this run.")
    run.set_defaults(func=command_run)

    resume = subparsers.add_parser("resume", help="Resume a queued or failed job record.")
    resume.add_argument("job_id")
    resume.add_argument("--execute", action="store_true", help="Resume and execute the best available path.")
    resume.add_argument("--execute-degraded", action="store_true", help="Resume and execute the FFmpeg degraded path.")
    resume.set_defaults(func=command_resume)

    export_manifest = subparsers.add_parser("export-manifest", help="Export a project manifest to a new path or stdout.")
    export_manifest.add_argument("project_manifest")
    export_manifest.add_argument("--output")
    export_manifest.set_defaults(func=command_export_manifest)

    export_support_bundle = subparsers.add_parser(
        "export-support-bundle",
        help="Export a support bundle with runtime health, model-pack state, and recent job context.",
    )
    export_support_bundle.add_argument("--output", help="Optional path for the support bundle zip file.")
    export_support_bundle.add_argument(
        "--include-full-paths",
        action="store_true",
        help="Include full paths instead of redacting them down to display names.",
    )
    export_support_bundle.add_argument("--session-state-key", help="Optional session-state key to include in the bundle.")
    export_support_bundle.add_argument("--job-id", help="Optional job id whose run manifest should be included in the bundle.")
    export_support_bundle.add_argument("--json-output", help="Optional path to write support-bundle metadata.")
    export_support_bundle.set_defaults(func=command_export_support_bundle)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
