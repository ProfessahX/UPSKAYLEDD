from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from upskayledd.app_service import AppService
from upskayledd.core.paths import RuntimeTemporaryDirectory, resolve_runtime_path
from upskayledd.integrations.ffprobe import FFprobeAdapter
from upskayledd.media_metrics import summarize_media_probe
from upskayledd.models import ComparisonMode, FidelityMode, InspectionReport, ProjectManifest


def _replace_default_path(content: str, key: str, replacement: Path) -> str:
    return content.replace(key, replacement.as_posix())


def normalize_encode_profile_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _safe_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _count_map(values: list[str]) -> dict[str, int]:
    counter = Counter(value for value in values if str(value).strip())
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def _fps_bucket_label(value: object) -> str:
    fps = _safe_float(value)
    if fps is None:
        return ""
    return f"{fps:.2f} fps"


def _format_size(value: object) -> str:
    size_bytes = _safe_int(value)
    if size_bytes is None:
        return "unknown size"
    if size_bytes >= 1_000_000_000:
        return f"{size_bytes / 1_000_000_000:.2f} GB"
    if size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.2f} MB"
    if size_bytes >= 1_000:
        return f"{size_bytes / 1_000:.1f} KB"
    return f"{size_bytes} bytes"


def _format_bitrate(value: object) -> str:
    bitrate = _safe_int(value)
    if bitrate is None:
        return "unknown bitrate"
    if bitrate >= 1_000_000:
        return f"{bitrate / 1_000_000:.2f} Mbps"
    return f"{bitrate / 1_000:.0f} kbps"


def _format_duration(value: object) -> str:
    duration = _safe_float(value)
    if duration is None:
        return "unknown duration"
    minutes, seconds = divmod(duration, 60.0)
    if minutes >= 1.0:
        return f"{int(minutes)}m {seconds:04.1f}s"
    return f"{seconds:.2f}s"


def _format_video_metrics(video: dict[str, Any]) -> str:
    codec = str(video.get("codec_name") or "unknown codec")
    width = _safe_int(video.get("width"))
    height = _safe_int(video.get("height"))
    resolution = f"{width}x{height}" if width and height else "unknown resolution"
    dar = str(video.get("display_aspect_ratio") or "").strip()
    fps = _safe_float(video.get("avg_frame_rate_fps"))
    fps_label = f"{fps:.2f} fps" if fps is not None else "unknown fps"
    field_order = str(video.get("field_order") or "unknown").replace("_", " ")
    pixel_format = str(video.get("pixel_format") or "").strip()
    details = [codec, resolution + (f" ({dar})" if dar else ""), fps_label, field_order, _format_bitrate(video.get("bit_rate_bps"))]
    if pixel_format:
        details.append(pixel_format)
    return " · ".join(details)


def _format_audio_metrics(audio: dict[str, Any]) -> str:
    codecs = ", ".join(audio.get("codec_names", [])) or "unknown audio"
    stream_count = _safe_int(audio.get("stream_count")) or 0
    max_channels = _safe_int(audio.get("max_channels")) or 0
    details = [f"{stream_count} stream(s)", codecs]
    if max_channels:
        details.append(f"up to {max_channels} ch")
    languages = ", ".join(audio.get("languages", []))
    if languages:
        details.append(languages)
    return " · ".join(details)


def _format_subtitle_metrics(subtitle: dict[str, Any]) -> str:
    codecs = ", ".join(subtitle.get("codec_names", [])) or "no subtitle codec data"
    stream_count = _safe_int(subtitle.get("stream_count")) or 0
    details = [f"{stream_count} stream(s)", codecs]
    languages = ", ".join(subtitle.get("languages", []))
    if languages:
        details.append(languages)
    return " · ".join(details)


def _format_comparison_highlights(comparison: dict[str, Any]) -> list[str]:
    if not comparison:
        return []
    lines: list[str] = []
    size_ratio = _safe_float(comparison.get("size_ratio"))
    bitrate_ratio = _safe_float(comparison.get("overall_bitrate_ratio"))
    resolution_scale = _safe_float(comparison.get("resolution_scale"))
    if size_ratio is not None:
        lines.append(f"Size ratio: {size_ratio:.2f}x")
    if bitrate_ratio is not None:
        lines.append(f"Overall bitrate ratio: {bitrate_ratio:.2f}x")
    if resolution_scale is not None:
        lines.append(f"Resolution scale: {resolution_scale:.2f}x")
    if comparison.get("container_changed"):
        lines.append("Container changed during delivery.")
    if comparison.get("video_codec_changed"):
        lines.append("Video codec changed during delivery.")
    if comparison.get("audio_codec_changed"):
        lines.append("Audio codec changed during delivery.")
    if comparison.get("subtitle_codec_changed"):
        lines.append("Subtitle codec changed during delivery.")
    subtitle_stream_delta = _safe_int(comparison.get("subtitle_stream_delta"))
    if subtitle_stream_delta not in (None, 0):
        lines.append(f"Subtitle stream delta: {subtitle_stream_delta:+d}")
    chapter_delta = _safe_int(comparison.get("chapter_delta"))
    if chapter_delta not in (None, 0):
        lines.append(f"Chapter delta: {chapter_delta:+d}")
    return lines


def _metric_rollup_bucket(
    metrics: dict[str, Any],
    *,
    containers: list[str],
    codecs: list[str],
    resolutions: list[str],
) -> None:
    container_name = str(metrics.get("container_name") or "").strip().lower()
    if container_name:
        containers.append(container_name)
    video = dict(metrics.get("video", {}))
    codec_name = str(video.get("codec_name") or "").strip().lower()
    if codec_name:
        codecs.append(codec_name)
    width = _safe_int(video.get("width"))
    height = _safe_int(video.get("height"))
    if width and height:
        resolutions.append(f"{width}x{height}")


def _probe_metrics(ffprobe_adapter: Any | None, path: str | Path) -> dict[str, Any]:
    if ffprobe_adapter is None or not bool(ffprobe_adapter.is_available()):
        return {}
    try:
        return summarize_media_probe(ffprobe_adapter.probe(path))
    except Exception:  # noqa: BLE001
        return {}


def _parse_fps_ratio(value: str) -> float | None:
    raw = str(value).strip()
    if not raw:
        return None
    if "/" in raw:
        numerator, denominator = raw.split("/", maxsplit=1)
        numerator_value = _safe_float(numerator)
        denominator_value = _safe_float(denominator)
        if numerator_value is None or denominator_value in (None, 0.0):
            return None
        return numerator_value / denominator_value
    return _safe_float(raw)


def _extract_vspipe_fps(output: str) -> float | None:
    for line in output.splitlines():
        if not line.startswith("FPS:"):
            continue
        ratio = line.partition(":")[2].strip().split(" ", maxsplit=1)[0]
        return _parse_fps_ratio(ratio)
    return None


def probe_vspipe_fps(path: str | Path) -> float | None:
    vspipe = shutil.which("vspipe")
    if not vspipe:
        return None
    resolved = Path(path).resolve()
    try:
        probe_root = resolve_runtime_path("runtime/validation/probe-cache")
        probe_root.mkdir(parents=True, exist_ok=True)
        stat = resolved.stat()
        cache_token = f"{stat.st_size}-{stat.st_mtime_ns}"
    except OSError:
        return None
    index_path = probe_root / f"{resolved.stem}-{cache_token}.ffindex"
    script_path = probe_root / f"{resolved.stem}-{cache_token}.vpy"
    try:
        script_path.write_text(
            (
                "import vapoursynth as vs\n"
                "core = vs.core\n"
                f"clip = core.ffms2.Source(source={str(resolved)!r}, cache=True, cachefile={str(index_path)!r})\n"
                "clip.set_output()\n"
            ),
            encoding="utf-8",
        )
    except OSError:
        return None
    completed = subprocess.run(
        [vspipe, "--info", str(script_path), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    fps = _extract_vspipe_fps(completed.stdout) or _extract_vspipe_fps(completed.stderr)
    if fps is not None:
        return fps
    if completed.returncode != 0:
        return None
    return None


def sample_copy_fallback_reasons(
    source_metrics: dict[str, Any] | None,
    sample_metrics: dict[str, Any] | None,
    *,
    fps_tolerance: float = 0.5,
    sample_pipeline_fps: float | None = None,
) -> list[str]:
    source_payload = dict(source_metrics or {})
    sample_payload = dict(sample_metrics or {})
    if not source_payload or not sample_payload:
        return []
    reasons: list[str] = []
    source_video = dict(source_payload.get("video", {}))
    sample_video = dict(sample_payload.get("video", {}))
    source_fps = _safe_float(source_video.get("avg_frame_rate_fps"))
    sample_fps = _safe_float(sample_video.get("avg_frame_rate_fps"))
    if source_fps is not None and sample_fps is not None and abs(source_fps - sample_fps) > fps_tolerance:
        reasons.append("copied sample drifted away from the source cadence")
    if source_fps is not None and sample_pipeline_fps is not None and abs(source_fps - sample_pipeline_fps) > fps_tolerance:
        reasons.append("copied sample drifts under ffms2/vspipe compared with the source cadence")
    source_audio = _safe_int(dict(source_payload.get("audio", {})).get("stream_count")) or 0
    sample_audio = _safe_int(dict(sample_payload.get("audio", {})).get("stream_count")) or 0
    if sample_audio < source_audio:
        reasons.append("copied sample lost audio streams")
    source_subtitles = _safe_int(dict(source_payload.get("subtitle", {})).get("stream_count")) or 0
    sample_subtitles = _safe_int(dict(sample_payload.get("subtitle", {})).get("stream_count")) or 0
    if sample_subtitles < source_subtitles:
        reasons.append("copied sample lost subtitle streams")
    return reasons


def build_metric_overview(media_metrics: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(media_metrics or {})
    input_metrics = dict(payload.get("input", {}))
    output_metrics = dict(payload.get("output", {}))
    comparison = dict(payload.get("comparison", {}))
    return {
        "input": {
            "container": str(input_metrics.get("container_name") or "unknown").upper(),
            "duration": _format_duration(input_metrics.get("duration_seconds")),
            "size": _format_size(input_metrics.get("size_bytes")),
            "overall_bitrate": _format_bitrate(input_metrics.get("overall_bitrate_bps")),
            "video": _format_video_metrics(dict(input_metrics.get("video", {}))),
            "audio": _format_audio_metrics(dict(input_metrics.get("audio", {}))),
            "subtitle": _format_subtitle_metrics(dict(input_metrics.get("subtitle", {}))),
            "chapter_count": _safe_int(input_metrics.get("chapter_count")) or 0,
        },
        "output": {
            "container": str(output_metrics.get("container_name") or "unknown").upper(),
            "duration": _format_duration(output_metrics.get("duration_seconds")),
            "size": _format_size(output_metrics.get("size_bytes")),
            "overall_bitrate": _format_bitrate(output_metrics.get("overall_bitrate_bps")),
            "video": _format_video_metrics(dict(output_metrics.get("video", {}))),
            "audio": _format_audio_metrics(dict(output_metrics.get("audio", {}))),
            "subtitle": _format_subtitle_metrics(dict(output_metrics.get("subtitle", {}))),
            "chapter_count": _safe_int(output_metrics.get("chapter_count")) or 0,
        },
        "comparison_highlights": _format_comparison_highlights(comparison),
        "guidance": [str(item).strip() for item in comparison.get("guidance", []) if str(item).strip()],
    }


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


def select_sources(
    service: AppService,
    target: Path,
    limit: int,
    *,
    output_policy_overrides: dict[str, Any] | None = None,
) -> tuple[list[Path], dict[str, Any]]:
    discovered = [path.resolve() for path in service.inspector.discover_media_files(target)]
    if not discovered:
        return [], {
            "strategy": "no_discoverable_sources",
            "considered_source_count": 0,
            "chosen_sources": [],
        }
    if target.is_file():
        return discovered[:1], {
            "strategy": "direct_file_target",
            "considered_source_count": len(discovered),
            "chosen_sources": [
                {
                    "source_path": str(path),
                    "source_name": path.name,
                    "reasons": ["direct target"],
                }
                for path in discovered[:1]
            ],
        }

    recommendation = service.recommend_target(str(target), output_policy_overrides=output_policy_overrides or {})
    inspection_reports = [InspectionReport.from_dict(item) for item in recommendation.get("inspection_reports", [])]
    if not inspection_reports:
        fallback = discovered[: max(1, limit)]
        return fallback, {
            "strategy": "discovery_fallback_no_inspection_reports",
            "considered_source_count": len(discovered),
            "chosen_sources": [
                {
                    "source_path": str(path),
                    "source_name": path.name,
                    "reasons": ["discovery fallback"],
                }
                for path in fallback
            ],
        }
    batch_summary = dict(recommendation.get("batch_summary", {}))
    dominant_profile = str(batch_summary.get("dominant_profile") or "").strip()
    outlier_paths = {str(path) for path in batch_summary.get("outlier_sources", [])}

    candidates = [
        {
            "source_path": report.source_path,
            "source_name": Path(report.source_path).name,
            "manual_review_required": report.manual_review_required,
            "warning_count": len(report.warnings),
            "profile_outlier": report.source_path in outlier_paths or (
                dominant_profile and report.recommended_profile_id != dominant_profile
            ),
            "confidence": report.confidence,
            "recommended_profile_id": report.recommended_profile_id,
            "detected_source_class": report.detected_source_class,
            "duration_seconds": report.duration_seconds,
            "size_bytes": report.size_bytes,
        }
        for report in inspection_reports
    ]

    selected: dict[str, dict[str, Any]] = {}
    selected_order: list[str] = []

    def add_candidate(candidate: dict[str, Any], reason: str) -> None:
        source_path = str(candidate["source_path"])
        if source_path in selected:
            reasons = list(selected[source_path]["reasons"])
            if reason not in reasons:
                reasons.append(reason)
                selected[source_path]["reasons"] = reasons
            return
        if len(selected_order) >= max(1, limit):
            return
        selected[source_path] = {**candidate, "reasons": [reason]}
        selected_order.append(source_path)

    manual_review = sorted(
        [item for item in candidates if item["manual_review_required"]],
        key=lambda item: (-item["warning_count"], item["confidence"], -(item["size_bytes"] or 0), item["source_name"].lower()),
    )
    profile_outliers = sorted(
        [item for item in candidates if item["profile_outlier"]],
        key=lambda item: (-item["warning_count"], item["confidence"], -(item["size_bytes"] or 0), item["source_name"].lower()),
    )
    dominant_representatives = sorted(
        [item for item in candidates if not dominant_profile or item["recommended_profile_id"] == dominant_profile],
        key=lambda item: (item["manual_review_required"], item["warning_count"], -item["confidence"], -(item["size_bytes"] or 0), item["source_name"].lower()),
    )
    largest_sources = sorted(candidates, key=lambda item: (-(item["size_bytes"] or 0), item["source_name"].lower()))
    longest_sources = sorted(candidates, key=lambda item: (-(item["duration_seconds"] or 0.0), item["source_name"].lower()))
    alphabetical = sorted(candidates, key=lambda item: item["source_name"].lower())

    for candidate in manual_review:
        add_candidate(candidate, "manual review candidate")
    for candidate in profile_outliers:
        add_candidate(candidate, "profile outlier")
    for candidate in dominant_representatives:
        add_candidate(candidate, "dominant profile representative")
    for candidate in largest_sources:
        add_candidate(candidate, "largest source")
    for candidate in longest_sources:
        add_candidate(candidate, "longest runtime")
    for candidate in alphabetical:
        add_candidate(candidate, "alphabetical fill")

    chosen_sources = [selected[source_path] for source_path in selected_order]
    return [Path(item["source_path"]).resolve() for item in chosen_sources], {
        "strategy": "representative_batch_sampling",
        "considered_source_count": len(candidates),
        "dominant_profile": dominant_profile,
        "manual_review_count": sum(1 for item in candidates if item["manual_review_required"]),
        "outlier_count": sum(1 for item in candidates if item["profile_outlier"]),
        "chosen_sources": chosen_sources,
    }


def extract_sample(source: Path, sample_path: Path, *, sample_seconds: float, start_seconds: float) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for real-world validation.")

    ffprobe = FFprobeAdapter()
    source_metrics = _probe_metrics(ffprobe, source)
    copy_fallback_reasons: list[str] = []
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
        sample_metrics = _probe_metrics(ffprobe, sample_path)
        copy_fallback_reasons = sample_copy_fallback_reasons(
            source_metrics,
            sample_metrics,
            sample_pipeline_fps=probe_vspipe_fps(sample_path),
        )
        if not copy_fallback_reasons:
            return {"mode": "stream_copy", "sample_path": str(sample_path)}
        sample_path.unlink(missing_ok=True)

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
        "0",
        "-map_chapters",
        "0",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-c:s",
        "copy",
        str(sample_path),
    ]
    transcode_run = subprocess.run(transcode_command, capture_output=True, text=True, check=False)
    if transcode_run.returncode == 0 and sample_path.exists() and sample_path.stat().st_size > 0:
        payload = {"mode": "transcode_fallback", "sample_path": str(sample_path)}
        if copy_run.returncode == 0:
            payload["fallback_reasons"] = copy_fallback_reasons
        return payload

    minimal_transcode_command = [
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
    minimal_transcode_run = subprocess.run(minimal_transcode_command, capture_output=True, text=True, check=False)
    if minimal_transcode_run.returncode != 0 or not sample_path.exists() or sample_path.stat().st_size <= 0:
        stderr = minimal_transcode_run.stderr.strip() or transcode_run.stderr.strip() or copy_run.stderr.strip()
        raise RuntimeError(f"Could not extract sample from {source.name}: {stderr}")
    payload = {"mode": "transcode_fallback_minimal", "sample_path": str(sample_path)}
    if copy_run.returncode == 0:
        payload["fallback_reasons"] = copy_fallback_reasons
    return payload


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
    media_metrics = dict(encode_settings.get("media_metrics", {}))
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
        "media_metrics": media_metrics,
        "metric_overview": build_metric_overview(media_metrics),
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
    items = list(results or [])
    sample_extraction_modes: list[str] = []

    def summarize_mode(result_items: list[dict[str, Any]], key: str) -> dict[str, Any]:
        size_ratios: list[float] = []
        cadence_change_count = 0
        decode_cadence_mismatch_count = 0
        subtitle_change_count = 0
        stream_loss_count = 0
        oversized_delivery_count = 0
        completed_runs = 0
        errored_runs = 0
        output_containers: list[str] = []
        output_video_codecs: list[str] = []
        output_resolutions: list[str] = []
        output_frame_rates: list[str] = []
        probe_frame_rates: list[str] = []
        decode_frame_rates: list[str] = []
        for item in result_items:
            run = dict(item.get(key) or {})
            if str(run.get("error", "")).strip():
                errored_runs += 1
            elif run.get("execution_mode"):
                completed_runs += 1
            size_summary = dict(run.get("size_summary") or {})
            size_ratio = _safe_float(size_summary.get("size_ratio"))
            if size_ratio is not None:
                size_ratios.append(size_ratio)
            if size_summary.get("oversized_delivery"):
                oversized_delivery_count += 1
            media_metrics = dict(run.get("media_metrics") or {})
            comparison = dict(media_metrics.get("comparison", {}) or {})
            input_video = dict(dict(media_metrics.get("input", {}) or {}).get("video", {}) or {})
            output_video = dict(dict(media_metrics.get("output", {}) or {}).get("video", {}) or {})
            _metric_rollup_bucket(
                dict(media_metrics.get("output", {}) or {}),
                containers=output_containers,
                codecs=output_video_codecs,
                resolutions=output_resolutions,
            )
            input_fps = _safe_float(input_video.get("avg_frame_rate_fps"))
            output_fps = _safe_float(output_video.get("avg_frame_rate_fps"))
            output_fps_label = _fps_bucket_label(output_fps)
            if output_fps_label:
                output_frame_rates.append(output_fps_label)
            sample_clip_cadence = dict(item.get("sample_clip_cadence", {}) or {})
            sample_probe_fps = _safe_float(sample_clip_cadence.get("probe_frame_rate_fps"))
            sample_decode_fps = _safe_float(sample_clip_cadence.get("decode_frame_rate_fps"))
            probe_fps_label = _fps_bucket_label(sample_probe_fps)
            if probe_fps_label:
                probe_frame_rates.append(probe_fps_label)
            decode_fps_label = _fps_bucket_label(sample_decode_fps)
            if decode_fps_label:
                decode_frame_rates.append(decode_fps_label)
            if (
                key == "canonical_run"
                and sample_probe_fps is not None
                and sample_decode_fps is not None
                and abs(sample_probe_fps - sample_decode_fps) >= 0.5
            ):
                decode_cadence_mismatch_count += 1
            if input_fps is not None and output_fps is not None and abs(input_fps - output_fps) >= 0.5:
                cadence_change_count += 1
            subtitle_delta = _safe_int(comparison.get("subtitle_stream_delta")) or 0
            chapter_delta = _safe_int(comparison.get("chapter_delta")) or 0
            if comparison.get("subtitle_codec_changed") or subtitle_delta != 0:
                subtitle_change_count += 1
            if subtitle_delta < 0 or chapter_delta < 0:
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
            "decode_cadence_mismatch_count": decode_cadence_mismatch_count,
            "oversized_delivery_count": oversized_delivery_count,
            "cadence_change_count": cadence_change_count,
            "subtitle_change_count": subtitle_change_count,
            "stream_loss_count": stream_loss_count,
            "size_ratio": size_summary_payload,
            "output_containers": _count_map(output_containers),
            "output_video_codecs": _count_map(output_video_codecs),
            "output_resolutions": _count_map(output_resolutions),
            "output_frame_rates": _count_map(output_frame_rates),
            "probe_frame_rates": _count_map(probe_frame_rates),
            "decode_frame_rates": _count_map(decode_frame_rates),
        }

    canonical = summarize_mode(items, "canonical_run")
    degraded = summarize_mode(items, "degraded_run")
    detected_source_classes = sorted(
        {
            str(dict(item.get("inspection", {})).get("detected_source_class", "")).strip()
            for item in items
            if str(dict(item.get("inspection", {})).get("detected_source_class", "")).strip()
        }
    )
    recommended_profiles = sorted(
        {
            str(dict(item.get("inspection", {})).get("recommended_profile_id", "")).strip()
            for item in items
            if str(dict(item.get("inspection", {})).get("recommended_profile_id", "")).strip()
        }
    )
    encode_profiles = sorted(
        {
            str(dict(item.get("output_policy", {})).get("encode_profile_id", "")).strip()
            for item in items
            if str(dict(item.get("output_policy", {})).get("encode_profile_id", "")).strip()
        }
    )
    source_containers: list[str] = []
    source_video_codecs: list[str] = []
    source_resolutions: list[str] = []
    guidance_messages: list[str] = []
    for item in items:
        sample_mode = str(dict(item.get("sample_clip", {}) or {}).get("mode", "")).strip()
        if sample_mode:
            sample_extraction_modes.append(sample_mode)
        canonical_metrics = dict(dict(item.get("canonical_run", {})).get("media_metrics", {}) or {})
        degraded_metrics = dict(dict(item.get("degraded_run", {})).get("media_metrics", {}) or {})
        source_metrics = dict(canonical_metrics.get("input", {}) or degraded_metrics.get("input", {}) or {})
        _metric_rollup_bucket(
            source_metrics,
            containers=source_containers,
            codecs=source_video_codecs,
            resolutions=source_resolutions,
        )
        guidance_messages.extend(
            [
                str(message).strip()
                for message in dict(canonical_metrics.get("comparison", {}) or {}).get("guidance", [])
                if str(message).strip()
            ]
        )
        guidance_messages.extend(
            [
                str(message).strip()
                for message in dict(degraded_metrics.get("comparison", {}) or {}).get("guidance", [])
                if str(message).strip()
            ]
        )
    watch_items: list[str] = []
    source_count = len(items)
    if canonical["cadence_change_count"]:
        watch_items.append(
            f"Canonical runs changed frame rate on {canonical['cadence_change_count']}/{source_count} sampled source(s)."
        )
    if canonical["decode_cadence_mismatch_count"]:
        watch_items.append(
            f"Sample metadata and ffms2 decode cadence disagreed on {canonical['decode_cadence_mismatch_count']}/{source_count} sampled source(s), so cadence warnings need decode-aware interpretation."
        )
    non_stream_copy_count = sum(1 for mode in sample_extraction_modes if mode and mode != "stream_copy")
    if canonical["cadence_change_count"] and non_stream_copy_count:
        watch_items.append(
            f"{non_stream_copy_count}/{source_count} sampled source(s) required non-stream-copy extraction before validation, so cadence warnings should be confirmed on fuller source clips when motion trust matters."
        )
    if len(canonical["output_frame_rates"]) > 1:
        if canonical["output_frame_rates"] == canonical["decode_frame_rates"]:
            watch_items.append(
                "Canonical sampled outputs landed in mixed frame-rate groups that match the sampled decode cadence buckets; verify whether the batch itself mixes cadence patterns before a long run."
            )
        else:
            watch_items.append(
                "Canonical sampled outputs landed in mixed frame-rate groups; verify whether batch cadence expectations actually match the sampled decode cadence before a long run."
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
        "media_rollup": {
            "source_containers": _count_map(source_containers),
            "source_video_codecs": _count_map(source_video_codecs),
            "source_resolutions": _count_map(source_resolutions),
            "guidance_messages": _count_map(guidance_messages),
        },
        "sample_extraction_modes": _count_map(sample_extraction_modes),
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
    sample_probe_metrics = _probe_metrics(service.ffprobe, sample_path)
    sample_decode_fps = probe_vspipe_fps(sample_path)

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
        "sample_clip_cadence": {
            "probe_frame_rate_fps": _safe_float(dict(sample_probe_metrics.get("video", {})).get("avg_frame_rate_fps")),
            "decode_frame_rate_fps": sample_decode_fps,
        },
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

    with RuntimeTemporaryDirectory("runtime/validation/scratch", prefix="real-world-validation-") as temp_dir:
        temp_root = Path(temp_dir)
        config_dir = create_temp_config(temp_root)
        service = AppService(str(config_dir))
        doctor_report = service.doctor_report()
        setup_actions = service.runtime_action_plan(doctor_report=doctor_report)
        normalized_profile_id = normalize_encode_profile_id(args.encode_profile)
        output_policy_overrides = {"encode_profile_id": normalized_profile_id} if normalized_profile_id else {}
        sources, selection_summary = select_sources(
            service,
            target,
            max(1, args.max_files),
            output_policy_overrides=output_policy_overrides,
        )
        if not sources:
            raise SystemExit(f"No supported video files found under {target}")

        results = [
            run_validation_for_source(
                service,
                source,
                temp_root,
                encode_profile_id=normalized_profile_id,
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
            "selection": selection_summary,
            "runtime_context": summarize_runtime_context(doctor_report, setup_actions),
            "summary": summarize_validation_results(results),
            "results": results,
        }
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
