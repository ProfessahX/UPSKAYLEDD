from __future__ import annotations

import math
from pathlib import Path
from uuid import uuid4

from upskayledd.backend_manager import BackendManager
from upskayledd.config import AppConfig
from upskayledd.core.hashing import fingerprint_path, sha256_json
from upskayledd.core.paths import ensure_directory
from upskayledd.integrations.ffmpeg import FFmpegAdapter
from upskayledd.integrations.vapoursynth import VapourSynthAdapter
from upskayledd.inspector import Inspector
from upskayledd.manifest_writer import write_artifact
from upskayledd.models import (
    ComparisonMode,
    FidelityMode,
    PipelineStage,
    PreviewRequest,
    PreviewResult,
    ProjectManifest,
    utc_now,
)
from upskayledd.project_store import ProjectStore


class PreviewEngine:
    def __init__(
        self,
        config: AppConfig,
        store: ProjectStore | None = None,
        ffmpeg: FFmpegAdapter | None = None,
        vapoursynth: VapourSynthAdapter | None = None,
        inspector: Inspector | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.ffmpeg = ffmpeg or FFmpegAdapter()
        self.vapoursynth = vapoursynth or VapourSynthAdapter(config, ffmpeg=self.ffmpeg)
        self.inspector = inspector or Inspector(config)

    def create_request(
        self,
        source_path: str,
        stage_id: str,
        comparison_mode: ComparisonMode,
        stage_settings: dict[str, object] | None = None,
        sample_start_seconds: float = 0.0,
        sample_duration_seconds: float | None = None,
        fidelity_mode_request: FidelityMode | None = None,
        backend_id: str = "planning_only",
        model_ids: list[str] | None = None,
    ) -> PreviewRequest:
        resolved_duration = sample_duration_seconds or self.config.preview.default_duration_seconds
        fidelity = fidelity_mode_request or FidelityMode(self.config.preview.default_fidelity_mode)
        stage_settings = stage_settings or {}
        model_ids = model_ids or []
        source_fingerprint = fingerprint_path(source_path)
        cache_key_inputs = {
            "source_fingerprint": source_fingerprint,
            "stage_id": stage_id,
            "stage_settings": stage_settings,
            "comparison_mode": comparison_mode.value,
            "sample_start_seconds": sample_start_seconds,
            "sample_duration_seconds": resolved_duration,
            "backend_id": backend_id,
            "model_ids": model_ids,
            "fidelity_mode": fidelity.value,
        }
        return PreviewRequest(
            preview_id=str(uuid4()),
            source_path=str(Path(source_path).resolve()),
            stage_id=stage_id,
            comparison_mode=comparison_mode,
            sample_start_seconds=sample_start_seconds,
            sample_duration_seconds=resolved_duration,
            render_settings={"stage_settings": stage_settings},
            cache_key_inputs=cache_key_inputs,
            fidelity_mode_request=fidelity,
            created_at=utc_now(),
        )

    def prepare_preview(self, request: PreviewRequest) -> PreviewResult:
        cache_key = sha256_json(request.cache_key_inputs)
        cached = self.store.get_preview_cache(cache_key) if self.store else None
        stale_cache_warning: str | None = None
        if cached and Path(cached["metadata_path"]).exists():
            payload = self.store.read_preview_result(cached["metadata_path"]) if self.store else None
            if payload is not None:
                missing_artifacts = self._missing_preview_artifacts(payload)
                if not missing_artifacts:
                    payload.cache_hit = True
                    return payload
                stale_cache_warning = (
                    "Cached preview artifacts were incomplete and were rerendered: "
                    + ", ".join(missing_artifacts)
                )
        elif cached:
            stale_cache_warning = "Cached preview metadata was missing and was rerendered."

        preview_dir = ensure_directory(Path(self.config.app.preview_cache_dir) / cache_key)
        metadata_path = preview_dir / "preview_result.json"
        artifact_paths: list[str] = []
        comparison_artifacts: dict[str, str] = {}
        warnings = ["Preview metadata prepared."]
        if stale_cache_warning:
            warnings.insert(0, stale_cache_warning)
        fidelity_mode = FidelityMode.APPROXIMATE
        clip_path = preview_dir / "source_preview.mp4"
        if self.ffmpeg.is_available():
            try:
                source_clip = str(
                    self.ffmpeg.extract_preview_clip(
                        source_path=request.source_path,
                        output_path=clip_path,
                        start_seconds=request.sample_start_seconds,
                        duration_seconds=request.sample_duration_seconds,
                    ).resolve()
                )
                artifact_paths.append(source_clip)
                comparison_artifacts["source"] = source_clip
                warnings.append("Source preview clip extracted successfully.")
                exact_rendered = False
                if request.fidelity_mode_request == FidelityMode.EXACT and self.vapoursynth.is_available():
                    try:
                        exact_result = self._render_exact_preview(request, preview_dir / "processed_preview_exact.mp4")
                        processed_clip = exact_result["artifact_path"]
                        artifact_paths.append(processed_clip)
                        comparison_artifacts["processed"] = processed_clip
                        warnings.extend(exact_result["warnings"])
                        warnings.append("Processed preview clip rendered through the canonical VapourSynth path.")
                        fidelity_mode = FidelityMode.EXACT
                        exact_rendered = True
                    except Exception as exc:  # noqa: BLE001
                        warnings.append(f"Exact preview failed and fell back to approximate rendering: {exc}")

                if not exact_rendered:
                    stage_filter = self._approximate_stage_filter(
                        request.stage_id,
                        request.render_settings.get("stage_settings", {}),
                    )
                    if stage_filter:
                        processed_clip = str(
                            self.ffmpeg.extract_preview_clip(
                                source_path=request.source_path,
                                output_path=preview_dir / "processed_preview.mp4",
                                start_seconds=request.sample_start_seconds,
                                duration_seconds=request.sample_duration_seconds,
                                video_filter=stage_filter,
                            ).resolve()
                        )
                        artifact_paths.append(processed_clip)
                        comparison_artifacts["processed"] = processed_clip
                        warnings.append(f"Approximate processed preview clip extracted using ffmpeg filter chain: {stage_filter}")
                    else:
                        warnings.append("No approximate filter mapping is defined for this stage yet; only source preview was extracted.")
            except Exception as exc:  # noqa: BLE001
                warnings.append(str(exc))
        else:
            warnings.append("ffmpeg unavailable; preview clip extraction skipped.")
        if fidelity_mode == FidelityMode.APPROXIMATE:
            warnings.append("Processed comparison rendering used the approximate preview path.")
        result = PreviewResult(
            preview_id=request.preview_id,
            cache_key=cache_key,
            comparison_mode=request.comparison_mode,
            fidelity_mode=fidelity_mode,
            cache_hit=False,
            artifact_paths=artifact_paths,
            comparison_artifacts=comparison_artifacts,
            metadata_path=str(metadata_path.resolve()),
            warnings=warnings,
            created_at=utc_now(),
        )
        write_artifact(metadata_path, result.to_dict())
        if self.store:
            self.store.record_preview_cache(
                cache_key=cache_key,
                metadata_path=str(metadata_path.resolve()),
                fidelity_mode=result.fidelity_mode.value,
            )
        return result

    def _missing_preview_artifacts(self, result: PreviewResult) -> list[str]:
        missing: list[str] = []
        for path_text in result.artifact_paths:
            path = Path(path_text)
            if not path.exists():
                missing.append(path.name)
        for role, path_text in result.comparison_artifacts.items():
            path = Path(path_text)
            if not path.exists():
                missing.append(f"{role}:{path.name}")
        return missing

    def _approximate_stage_filter(self, stage_id: str, stage_settings: dict[str, object]) -> str | None:
        stage_filters = self.config.fallback_filters.stage_filters.get(stage_id, {})
        template = stage_filters.get("preview")
        if not template:
            return None
        width = stage_settings.get("target_width")
        height = stage_settings.get("target_height")
        if stage_id == "upscale" and not (width and height):
            return self.config.fallback_filters.preview_default_upscale
        return template.format(width=width, height=height)

    def _render_exact_preview(self, request: PreviewRequest, output_path: Path) -> dict[str, object]:
        report = self.inspector.inspect_path(request.source_path)
        profile = self.config.profile_by_id(report.recommended_profile_id)
        stage_settings = dict(request.render_settings.get("stage_settings", {}))
        stage_defaults = profile.stage_defaults.get(request.stage_id, {})
        mode = str(stage_settings.get("mode") or stage_defaults.get("mode") or "default")
        output_policy = {
            "container": profile.default_container,
            "width": int(stage_settings.get("target_width") or profile.default_output_width),
            "height": int(stage_settings.get("target_height") or profile.default_output_height),
            "display_aspect_ratio": profile.display_aspect_ratio,
            "output_root": self.config.app.default_output_root,
        }
        manifest = ProjectManifest(
            project_id=report.source_fingerprint[:12],
            created_at=utc_now(),
            source_files=[request.source_path],
            selected_profile_id=profile.id,
            output_policy=output_policy,
            resolved_pipeline_stages=[
                PipelineStage(
                    stage_id=request.stage_id,
                    label=request.stage_id.replace("_", " ").title(),
                    enabled=True,
                    settings={"mode": mode, **stage_settings},
                    reason="preview_request",
                )
            ],
            backend_preferences=[request.cache_key_inputs.get("backend_id", "planning_only")],
            model_preferences=list(request.cache_key_inputs.get("model_ids", [])),
            batch_settings={},
            per_file_overrides={},
            custom_model_paths=[],
            hook_references=[],
            warnings=[],
        )
        backend_selection = BackendManager(self.config).choose_backend()
        fps = self._resolve_fps(report)
        start_frame = int(request.sample_start_seconds * fps)
        duration_frames = max(1, int(request.sample_duration_seconds * fps))
        max_frame = self._resolve_last_frame(request.source_path, report, fps)
        end_frame = max(start_frame, start_frame + duration_frames - 1)
        end_frame = min(end_frame, max_frame)
        return self.vapoursynth.render_preview(
            manifest=manifest,
            stage_plan=manifest.resolved_pipeline_stages,
            source_path=request.source_path,
            output_path=output_path,
            backend_selection=backend_selection,
            start_frame=start_frame,
            end_frame=end_frame,
        )

    def _resolve_fps(self, report) -> float:
        for stream in report.streams:
            if stream.codec_type != "video":
                continue
            rate = stream.avg_frame_rate
            if not rate or rate in {"0/0", "N/A"}:
                continue
            if "/" in rate:
                numerator, denominator = rate.split("/", maxsplit=1)
                if float(denominator) == 0:
                    continue
                return float(numerator) / float(denominator)
            return float(rate)
        return 24.0

    def _resolve_last_frame(self, source_path: str, report, fps: float) -> int:
        payload = self.inspector.ffprobe.probe(source_path)
        for stream in payload.get("streams", []):
            if stream.get("codec_type") != "video":
                continue
            nb_frames = stream.get("nb_frames")
            if nb_frames not in {None, "", "N/A"}:
                return max(0, int(nb_frames) - 1)
        duration_seconds = report.duration_seconds or 0.0
        estimated_frames = max(1, math.ceil(duration_seconds * fps))
        return estimated_frames - 1
