from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from upskayledd.models import ProjectManifest


@dataclass(slots=True)
class DesktopSessionState:
    current_page: str
    simple_mode: bool
    queue_collapsed: bool
    selected_stage: str
    comparison_mode: str
    fidelity_mode: str
    preview_start_seconds: float
    preview_duration_seconds: float
    selected_source: str
    selected_job_id: str
    last_target: str
    stage_expansion_memory: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_page": self.current_page,
            "simple_mode": self.simple_mode,
            "queue_collapsed": self.queue_collapsed,
            "selected_stage": self.selected_stage,
            "comparison_mode": self.comparison_mode,
            "fidelity_mode": self.fidelity_mode,
            "preview_start_seconds": self.preview_start_seconds,
            "preview_duration_seconds": self.preview_duration_seconds,
            "selected_source": self.selected_source,
            "selected_job_id": self.selected_job_id,
            "last_target": self.last_target,
            "stage_expansion_memory": self.stage_expansion_memory,
        }

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
        *,
        default_page: str,
        default_simple_mode: bool,
        default_queue_collapsed: bool,
        default_stage: str,
        default_comparison_mode: str,
        default_fidelity_mode: str,
        default_preview_start_seconds: float,
        default_preview_duration_seconds: float,
    ) -> "DesktopSessionState":
        return cls(
            current_page=str(payload.get("current_page", default_page)),
            simple_mode=bool(payload.get("simple_mode", default_simple_mode)),
            queue_collapsed=bool(payload.get("queue_collapsed", default_queue_collapsed)),
            selected_stage=str(payload.get("selected_stage", default_stage)),
            comparison_mode=str(payload.get("comparison_mode", default_comparison_mode)),
            fidelity_mode=str(payload.get("fidelity_mode", default_fidelity_mode)),
            preview_start_seconds=float(payload.get("preview_start_seconds", default_preview_start_seconds)),
            preview_duration_seconds=float(payload.get("preview_duration_seconds", default_preview_duration_seconds)),
            selected_source=str(payload.get("selected_source", "")),
            selected_job_id=str(payload.get("selected_job_id", "")),
            last_target=str(payload.get("last_target", "")),
            stage_expansion_memory=dict(payload.get("stage_expansion_memory", {})),
        )


@dataclass(slots=True)
class CurrentProject:
    inspection_reports: list[dict[str, Any]]
    backend_selection: dict[str, Any]
    manifest: ProjectManifest
    batch_summary: dict[str, Any] = field(default_factory=dict)
    delivery_guidance: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "CurrentProject":
        return cls(
            inspection_reports=list(payload["inspection_reports"]),
            backend_selection=dict(payload["backend_selection"]),
            manifest=ProjectManifest.from_dict(payload["project_manifest"]),
            batch_summary=dict(payload.get("batch_summary", {})),
            delivery_guidance=dict(payload.get("delivery_guidance", {})),
        )

    @property
    def source_files(self) -> list[str]:
        return list(self.manifest.source_files)

    @property
    def stage_ids(self) -> list[str]:
        return [stage.stage_id for stage in self.manifest.resolved_pipeline_stages]

    def stage_by_id(self, stage_id: str):
        for stage in self.manifest.resolved_pipeline_stages:
            if stage.stage_id == stage_id:
                return stage
        return self.manifest.resolved_pipeline_stages[0] if self.manifest.resolved_pipeline_stages else None
