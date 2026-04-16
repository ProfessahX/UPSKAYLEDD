from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from upskayledd.app_service import AppService
from upskayledd.models import ComparisonMode, FidelityMode, ProjectManifest


def _replace_default_path(content: str, key: str, replacement: Path) -> str:
    return content.replace(key, replacement.as_posix())


def normalize_encode_profile_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def create_temp_config(temp_root: Path) -> Path:
    config_dir = temp_root / "config"
    shutil.copytree(ROOT / "config", config_dir)
    defaults_path = config_dir / "defaults.toml"
    defaults = defaults_path.read_text(encoding="utf-8")
    replacements = {
        "runtime/output": temp_root / "output",
        "runtime/state/upskayledd.sqlite3": temp_root / "state.sqlite3",
        "runtime/cache/previews": temp_root / "preview_cache",
        "runtime/support": temp_root / "support",
    }
    for old, new in replacements.items():
        defaults = _replace_default_path(defaults, old, new)
    defaults_path.write_text(defaults, encoding="utf-8")
    return config_dir


def select_sources(service: AppService, target: Path, limit: int) -> list[Path]:
    matches = [path.resolve() for path in service.inspector.discover_media_files(target)]
    return matches[:limit]


def extract_sample(source: Path, sample_path: Path, *, sample_seconds: float, start_seconds: float) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for real-world validation.")

    copy_command = [
        ffmpeg,
        "-y",
        "-ss",
        f"{start_seconds:.3f}",
        "-i",
        str(source),
        "-t",
        f"{sample_seconds:.3f}",
        "-map",
        "0",
        "-c",
        "copy",
        str(sample_path),
    ]
    copy_run = subprocess.run(copy_command, capture_output=True, text=True, check=False)
    if copy_run.returncode == 0 and sample_path.exists() and sample_path.stat().st_size > 0:
        return {"mode": "stream_copy", "sample_path": str(sample_path)}

    transcode_command = [
        ffmpeg,
        "-y",
        "-ss",
        f"{start_seconds:.3f}",
        "-i",
        str(source),
        "-t",
        f"{sample_seconds:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(sample_path),
    ]
    transcode_run = subprocess.run(transcode_command, capture_output=True, text=True, check=False)
    if transcode_run.returncode != 0 or not sample_path.exists() or sample_path.stat().st_size <= 0:
        stderr = transcode_run.stderr.strip() or copy_run.stderr.strip()
        raise RuntimeError(f"Could not extract sample from {source.name}: {stderr}")
    return {"mode": "transcode_fallback", "sample_path": str(sample_path)}


def summarize_preview(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(payload or {})
    artifacts = dict(payload.get("comparison_artifacts", {}))
    return {
        "fidelity_mode": payload.get("fidelity_mode"),
        "warning_count": len(payload.get("warnings", [])),
        "warnings": list(payload.get("warnings", [])),
        "artifacts_present": sorted(key for key, value in artifacts.items() if value),
    }


def file_stats(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {"exists": False, "size_bytes": 0}
    resolved = Path(path)
    if not resolved.exists():
        return {"exists": False, "size_bytes": 0, "path": str(resolved)}
    return {
        "exists": True,
        "path": str(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def summarize_run_manifest(manifest: dict[str, Any] | None) -> dict[str, Any]:
    payload = manifest or {}
    encode_settings = dict(payload.get("encode_settings", {}))
    size_summary = {
        "input_size_bytes": encode_settings.get("input_size_bytes"),
        "output_size_bytes": encode_settings.get("output_size_bytes"),
        "size_ratio": encode_settings.get("size_ratio"),
    }
    size_ratio = size_summary.get("size_ratio")
    size_summary["oversized_delivery"] = bool(size_ratio and size_ratio > 1.05)
    return {
        "execution_mode": encode_settings.get("execution_mode"),
        "warning_count": len(payload.get("warnings", [])),
        "warnings": list(payload.get("warnings", [])),
        "fallback_count": len(payload.get("fallbacks", [])),
        "output_files": list(payload.get("output_files", [])),
        "output_stats": [file_stats(path) for path in payload.get("output_files", [])],
        "size_summary": size_summary,
        "media_metrics": dict(encode_settings.get("media_metrics", {})),
        "conversion_guidance": list(encode_settings.get("conversion_guidance", [])),
    }


def summarize_runtime_context(
    doctor_report: dict[str, Any] | None,
    setup_actions: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    payload = dict(doctor_report or {})
    actions = list(setup_actions or [])
    return {
        "platform_summary": str(payload.get("platform_summary", "")).strip(),
        "warning_count": len(payload.get("warnings", [])),
        "warnings": list(payload.get("warnings", [])),
        "action_count": len(actions),
        "actions": actions,
    }


def summarize_validation_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    def summarize_mode(items: list[dict[str, Any]], key: str) -> dict[str, Any]:
        size_ratios: list[float] = []
        cadence_change_count = 0
        subtitle_change_count = 0
        stream_loss_count = 0
        oversized_delivery_count = 0
        completed_runs = 0
        errored_runs = 0
        for item in items:
            run = dict(item.get(key, {}))
            if str(run.get("error", "")).strip():
                errored_runs += 1
            elif run.get("execution_mode"):
                completed_runs += 1
            size_summary = dict(run.get("size_summary", {}))
            size_ratio = size_summary.get("size_ratio")
            if size_ratio not in (None, ""):
                size_ratios.append(float(size_ratio))
            if size_summary.get("oversized_delivery"):
                oversized_delivery_count += 1
            comparison = dict(run.get("media_metrics", {})).get("comparison", {})
            input_video = dict(dict(run.get("media_metrics", {})).get("input", {})).get("video", {})
            output_video = dict(dict(run.get("media_metrics", {})).get("output", {})).get("video", {})
            input_fps = input_video.get("avg_frame_rate_fps")
            output_fps = output_video.get("avg_frame_rate_fps")
            if input_fps not in (None, "") and output_fps not in (None, ""):
                if abs(float(input_fps) - float(output_fps)) >= 0.5:
                    cadence_change_count += 1
            if comparison.get("subtitle_codec_changed") or int(comparison.get("subtitle_stream_delta", 0) or 0) != 0:
                subtitle_change_count += 1
            if int(comparison.get("subtitle_stream_delta", 0) or 0) < 0 or int(comparison.get("chapter_delta", 0) or 0) < 0:
                stream_loss_count += 1
        size_summary_payload: dict[str, Any] = {"count": len(size_ratios)}
        if size_ratios:
            size_summary_payload.update(
                {
                    "min": round(min(size_ratios), 4),
                    "avg": round(sum(size_ratios) / len(size_ratios), 4),
                    "max": round(max(size_ratios), 4),
                }
            )
        return {
            "completed_runs": completed_runs,
            "errored_runs": errored_runs,
            "oversized_delivery_count": oversized_delivery_count,
            "cadence_change_count": cadence_change_count,
            "subtitle_change_count": subtitle_change_count,
            "stream_loss_count": stream_loss_count,
            "size_ratio": size_summary_payload,
        }

    canonical = summarize_mode(results, "canonical_run")
    degraded = summarize_mode(results, "degraded_run")
    detected_source_classes = sorted(
        {
            str(dict(item.get("inspection", {})).get("detected_source_class", "")).strip()
            for item in results
            if str(dict(item.get("inspection", {})).get("detected_source_class", "")).strip()
        }
    )
    recommended_profiles = sorted(
        {
            str(dict(item.get("inspection", {})).get("recommended_profile_id", "")).strip()
            for item in results
            if str(dict(item.get("inspection", {})).get("recommended_profile_id", "")).strip()
        }
    )
    encode_profiles = sorted(
        {
            str(dict(item.get("output_policy", {})).get("encode_profile_id", "")).strip()
            for item in results
            if str(dict(item.get("output_policy", {})).get("encode_profile_id", "")).strip()
        }
    )
    watch_items: list[str] = []
    source_count = len(results)
    if canonical["cadence_change_count"]:
        watch_items.append(
            f"Canonical runs changed frame rate on {canonical['cadence_change_count']}/{source_count} sampled source(s)."
        )
    if canonical["oversized_delivery_count"] or degraded["oversized_delivery_count"]:
        watch_items.append(
            "At least one sampled delivery landed larger than its source clip. Review the chosen encode lane before scaling up."
        )
    if canonical["stream_loss_count"] or degraded["stream_loss_count"]:
        watch_items.append(
            "At least one sampled run dropped subtitle or chapter streams. Verify preservation before trusting that delivery lane."
        )
    if canonical["subtitle_change_count"] or degraded["subtitle_change_count"]:
        watch_items.append(
            "At least one sampled run changed subtitle delivery. Double-check compatibility-focused lanes against preservation goals."
        )
    if canonical["errored_runs"]:
        watch_items.append(
            f"The canonical path failed on {canonical['errored_runs']}/{source_count} sampled source(s)."
        )
    if not watch_items:
        watch_items.append("No immediate batch-level watch items were detected in the sampled validation runs.")
    return {
        "source_count": source_count,
        "detected_source_classes": detected_source_classes,
        "recommended_profiles": recommended_profiles,
        "encode_profiles": encode_profiles,
        "canonical": canonical,
        "degraded": degraded,
        "watch_items": watch_items,
    }


def run_validation_for_source(
    service: AppService,
    source: Path,
    working_root: Path,
    *,
    encode_profile_id: str | None,
    sample_seconds: float,
    sample_start_seconds: float,
    preview_seconds: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    output_overrides = {"encode_profile_id": encode_profile_id} if encode_profile_id else {}
    recommendation = service.recommend_target(str(source), output_policy_overrides=output_overrides)
    backend = dict(recommendation["backend_selection"])
    report = dict(recommendation["inspection_reports"][0])
    delivery_guidance = dict(recommendation.get("delivery_guidance", {}))

    sample_dir = working_root / "samples"
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_path = sample_dir / f"{source.stem}.sample.mkv"
    sample_info = extract_sample(
        source,
        sample_path,
        sample_seconds=sample_seconds,
        start_seconds=sample_start_seconds,
    )

    sample_recommendation = service.recommend_target(str(sample_path), output_policy_overrides=output_overrides)
    manifest = ProjectManifest.from_dict(sample_recommendation["project_manifest"])
    stage_lookup = {stage.stage_id: stage for stage in manifest.resolved_pipeline_stages}
    model_ids = list(manifest.model_preferences)
    backend_id = str(sample_recommendation["backend_selection"].get("backend_id", "planning_only"))

    cleanup_preview = None
    if "cleanup" in stage_lookup:
        cleanup_preview = service.prepare_preview(
            source_path=str(sample_path),
            stage_id="cleanup",
            comparison_mode=ComparisonMode.SLIDER_WIPE,
            stage_settings=dict(stage_lookup["cleanup"].settings),
            sample_start_seconds=0.0,
            sample_duration_seconds=preview_seconds,
            fidelity_mode=FidelityMode.EXACT,
            backend_id=backend_id,
            model_ids=model_ids,
        ).to_dict()

    upscale_preview = None
    if "upscale" in stage_lookup:
        upscale_settings = dict(stage_lookup["upscale"].settings)
        upscale_settings.setdefault("target_width", int(manifest.output_policy.get("width", 0) or 0))
        upscale_settings.setdefault("target_height", int(manifest.output_policy.get("height", 0) or 0))
        upscale_preview = service.prepare_preview(
            source_path=str(sample_path),
            stage_id="upscale",
            comparison_mode=ComparisonMode.SLIDER_WIPE,
            stage_settings=upscale_settings,
            sample_start_seconds=0.0,
            sample_duration_seconds=preview_seconds,
            fidelity_mode=FidelityMode.EXACT,
            backend_id=backend_id,
            model_ids=model_ids,
        ).to_dict()

    run_root = working_root / "runs" / source.stem
    run_root.mkdir(parents=True, exist_ok=True)
    _, degraded_jobs = service.run_project(manifest, output_dir=run_root / "degraded", execute_degraded=True)
    degraded_manifest = service.run_manifest_for_job(degraded_jobs[0].job_id) if degraded_jobs else None

    canonical_manifest = None
    canonical_error = ""
    try:
        _, canonical_jobs = service.run_project(manifest, output_dir=run_root / "canonical", execute=True)
        canonical_manifest = service.run_manifest_for_job(canonical_jobs[0].job_id) if canonical_jobs else None
    except Exception as exc:  # noqa: BLE001
        canonical_error = str(exc)

    return {
        "source_path": str(source),
        "source_name": source.name,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "output_policy": {
            "encode_profile_id": manifest.output_policy.get("encode_profile_id"),
            "container": manifest.output_policy.get("container"),
            "video_codec": manifest.output_policy.get("video_codec"),
            "video_preset": manifest.output_policy.get("video_preset"),
            "video_crf": manifest.output_policy.get("video_crf"),
            "audio_codec": manifest.output_policy.get("audio_codec"),
            "subtitle_codec": manifest.output_policy.get("subtitle_codec"),
        },
        "delivery_guidance": delivery_guidance,
        "inspection": {
            "detected_source_class": report.get("detected_source_class"),
            "recommended_profile_id": report.get("recommended_profile_id"),
            "manual_review_required": report.get("manual_review_required"),
            "confidence": report.get("confidence"),
            "warning_count": len(report.get("warnings", [])),
            "warnings": list(report.get("warnings", [])),
        },
        "backend_selection": {
            "backend_id": backend.get("backend_id"),
            "degraded": backend.get("degraded"),
            "reasons": list(backend.get("reasons", [])),
        },
        "sample_clip": sample_info,
        "sample_clip_stats": file_stats(sample_info.get("sample_path")),
        "cleanup_preview": summarize_preview(cleanup_preview),
        "upscale_preview": summarize_preview(upscale_preview),
        "degraded_run": summarize_run_manifest(degraded_manifest),
        "canonical_run": {
            **summarize_run_manifest(canonical_manifest),
            "error": canonical_error,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a generic real-world validation pass against a few large source files.")
    parser.add_argument("target", help="A source file or folder to sample.")
    parser.add_argument("--max-files", type=int, default=2, help="Maximum number of source files to validate.")
    parser.add_argument("--sample-seconds", type=float, default=12.0, help="Length of the extracted validation sample clip.")
    parser.add_argument("--sample-start", type=float, default=0.0, help="Start time for the extracted sample clip.")
    parser.add_argument("--preview-seconds", type=float, default=3.0, help="Length of the preview window rendered from the sample clip.")
    parser.add_argument("--encode-profile", help="Optional encode profile id to validate instead of the default output policy.")
    parser.add_argument(
        "--output-json",
        default=str(ROOT / "runtime" / "validation" / "real_world_validation.json"),
        help="Path where the validation report should be written.",
    )
    args = parser.parse_args(argv)

    target = Path(args.target).resolve()
    if not target.exists():
        raise SystemExit(f"Target does not exist: {target}")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        config_dir = create_temp_config(temp_root)
        service = AppService(str(config_dir))
        doctor_report = service.doctor_report()
        setup_actions = service.runtime_action_plan(doctor_report=doctor_report)
        sources = select_sources(service, target, max(1, args.max_files))
        if not sources:
            raise SystemExit(f"No supported video files found under {target}")

        results = [
            run_validation_for_source(
                service,
                source,
                temp_root,
                encode_profile_id=normalize_encode_profile_id(args.encode_profile),
                sample_seconds=max(1.0, float(args.sample_seconds)),
                sample_start_seconds=max(0.0, float(args.sample_start)),
                preview_seconds=max(0.5, float(args.preview_seconds)),
            )
            for source in sources
        ]

        output_path = Path(args.output_json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "target": str(target),
            "source_count": len(results),
            "runtime_context": summarize_runtime_context(doctor_report, setup_actions),
            "summary": summarize_validation_results(results),
            "results": results,
        }
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
