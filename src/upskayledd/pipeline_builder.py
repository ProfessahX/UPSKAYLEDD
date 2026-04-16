from __future__ import annotations

from typing import Any

from upskayledd.config import AppConfig, ProfileDefinition
from upskayledd.encode_mux import EncodeMuxPlanner
from upskayledd.model_registry import ModelRegistry
from upskayledd.models import InspectionReport, PipelineStage, ProjectManifest, utc_now


TEXT_FRIENDLY_MP4_SUBTITLE_CODECS = {"ass", "mov_text", "ssa", "subrip", "text", "webvtt"}


class PipelineBuilder:
    def __init__(self, config: AppConfig, model_registry: ModelRegistry) -> None:
        self.config = config
        self.model_registry = model_registry
        self.encode_planner = EncodeMuxPlanner(config)

    def build_manifest(
        self,
        reports: list[InspectionReport],
        profile: ProfileDefinition,
        per_file_overrides: dict[str, dict[str, str]] | None = None,
        warnings: list[str] | None = None,
        custom_model_paths: list[str] | None = None,
        hook_references: list[str] | None = None,
        output_policy_overrides: dict[str, Any] | None = None,
    ) -> ProjectManifest:
        per_file_overrides = per_file_overrides or {}
        warnings = warnings or []
        custom_model_paths = custom_model_paths or []
        hook_references = hook_references or []

        suppress_risky = any(report.manual_review_required for report in reports)
        stages = self._build_stages(profile, suppress_risky=suppress_risky)
        model_preferences = self.model_registry.default_family_ids()
        output_policy = self.encode_planner.build_output_policy(profile, output_policy_overrides)
        warnings.extend(self._build_output_policy_warnings(reports, output_policy))

        return ProjectManifest(
            project_id=reports[0].source_fingerprint[:12] if reports else "empty_project",
            created_at=utc_now(),
            source_files=[report.source_path for report in reports],
            selected_profile_id=profile.id,
            output_policy=output_policy,
            resolved_pipeline_stages=stages,
            backend_preferences=["tensorrt_nvidia", "vulkan_ml", "cpu_compat"],
            model_preferences=model_preferences,
            batch_settings={
                "project_history_scope": self.config.app.project_history_scope,
                "restart_partial_encode": self.config.queue.restart_partial_encode,
            },
            per_file_overrides=per_file_overrides,
            custom_model_paths=custom_model_paths,
            hook_references=hook_references,
            warnings=sorted(set(warnings)),
        )

    def _build_output_policy_warnings(
        self,
        reports: list[InspectionReport],
        output_policy: dict[str, Any],
    ) -> list[str]:
        warnings: list[str] = []
        container = str(output_policy.get("container", "")).strip().lower()
        if container != "mp4":
            return warnings
        subtitle_codecs = sorted(
            {
                stream.codec_name.lower()
                for report in reports
                for stream in report.streams
                if stream.codec_type == "subtitle" and stream.codec_name
            }
        )
        risky_codecs = [codec for codec in subtitle_codecs if codec not in TEXT_FRIENDLY_MP4_SUBTITLE_CODECS]
        if risky_codecs:
            template = self.config.conversion_guidance.messages.get(
                "mp4_subtitle_risk",
                "MP4 delivery may drop subtitle codecs that do not map cleanly to text-based MP4 subtitles ({codecs}); keep MKV if subtitle retention matters.",
            )
            warnings.append(template.format(codecs=", ".join(risky_codecs)))
        return warnings

    def _build_stages(self, profile: ProfileDefinition, suppress_risky: bool) -> list[PipelineStage]:
        stages: list[PipelineStage] = []
        for stage_id in profile.default_stages:
            stage_defaults = profile.stage_defaults.get(stage_id, {})
            enabled = not (suppress_risky and stage_id in profile.risky_stages)
            reason = "suppressed_for_manual_review" if not enabled else "profile_default"
            stages.append(
                PipelineStage(
                    stage_id=stage_id,
                    label=stage_id.replace("_", " ").title(),
                    enabled=enabled,
                    settings=dict(stage_defaults),
                    reason=reason,
                )
            )
        return stages
