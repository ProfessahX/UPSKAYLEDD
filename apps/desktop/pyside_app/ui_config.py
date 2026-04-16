from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from upskayledd.core.paths import resolve_repo_path
except ImportError:  # pragma: no cover - defensive fallback for isolated UI editing
    def resolve_repo_path(raw_path: str | Path) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        return Path(__file__).resolve().parents[3] / path


@dataclass(slots=True, frozen=True)
class WindowConfig:
    title: str
    width: int
    height: int
    minimum_width: int
    minimum_height: int


@dataclass(slots=True, frozen=True)
class BehaviorConfig:
    session_state_key: str
    default_page: str
    default_simple_mode: bool
    default_queue_collapsed: bool
    dashboard_refresh_seconds: int
    auto_play_preview: bool


@dataclass(slots=True, frozen=True)
class AssetConfig:
    app_icon: str
    repo_header: str
    hero_graphic: str


@dataclass(slots=True, frozen=True)
class LayoutConfig:
    stage_rail_width: int
    detail_panel_width: int
    preview_panel_width: int
    queue_bar_expanded_height: int
    brand_panel_width: int
    brand_graphic_height: int


@dataclass(slots=True, frozen=True)
class PreviewUiConfig:
    default_stage: str
    default_comparison_mode: str
    default_fidelity_mode: str
    default_sample_start_seconds: float
    default_sample_duration_seconds: float
    comparison_modes: tuple[str, ...]
    fidelity_modes: tuple[str, ...]
    upscale_preview_width: int
    upscale_preview_height: int


@dataclass(slots=True, frozen=True)
class ThemeConfig:
    font_family: str
    display_font_family: str
    accent_color: str
    accent_soft: str
    background_start: str
    background_end: str
    surface_color: str
    surface_alt: str
    panel_color: str
    panel_raised: str
    ink_color: str
    muted_color: str
    line_color: str
    preview_background: str
    success_color: str
    warning_color: str
    danger_color: str
    info_color: str


@dataclass(slots=True, frozen=True)
class GlobalCopyConfig:
    wordmark: str
    tagline: str
    ready_label: str
    working_label: str
    doctor_button: str
    model_button: str
    install_button: str
    support_button: str
    doctor_dialog_title: str
    model_dialog_title: str
    support_dialog_title: str
    error_dialog_title: str


@dataclass(slots=True, frozen=True)
class RuntimeStatusCopyConfig:
    headline: str
    doctor_summary: str
    model_summary: str
    action: str


@dataclass(slots=True, frozen=True)
class RuntimeCopyConfig:
    title: str
    platform_empty: str
    focus_title: str
    focus_empty: str
    packs_title: str
    packs_empty: str
    actions_title: str
    actions_empty: str
    locations_title: str
    locations_empty: str
    open_location_button: str
    location_labels: dict[str, str]
    checking: RuntimeStatusCopyConfig
    ready: RuntimeStatusCopyConfig
    watch: RuntimeStatusCopyConfig
    attention: RuntimeStatusCopyConfig


@dataclass(slots=True, frozen=True)
class IngestCopyConfig:
    drop_title: str
    drop_body: str
    target_placeholder: str
    browse_button: str
    analyze_button: str
    recent_title: str
    recent_empty: str
    recent_open_button: str
    recent_prune_button: str


@dataclass(slots=True, frozen=True)
class SummaryCopyConfig:
    title: str
    intro: str
    placeholder: str
    delivery_guidance_label: str
    alternative_profiles_label: str
    batch_review_title: str
    batch_review_idle: str
    batch_review_aligned: str
    batch_review_attention: str
    open_workspace_button: str
    analyze_another_button: str
    review_selected_button: str
    review_flagged_button: str


@dataclass(slots=True, frozen=True)
class WorkspaceCopyConfig:
    source_label: str
    simple_mode_label: str
    source_context_placeholder: str
    source_context_aligned: str
    source_context_outlier: str
    source_context_manual_review: str


@dataclass(slots=True, frozen=True)
class QueueCopyConfig:
    idle: str
    collapse_button: str
    expand_button: str
    processing_template: str
    waiting_template: str
    attention_template: str
    summary_counts_template: str


@dataclass(slots=True, frozen=True)
class DashboardCopyConfig:
    title: str
    refresh_button: str
    queue_idle: str
    overview_title: str
    overview_empty: str
    overall_progress_label: str
    focus_title: str
    focus_empty: str
    focus_running: str
    focus_failed: str
    focus_paused: str
    focus_queued: str
    focus_planned: str
    focus_completed: str
    active_label: str
    completed_label: str
    issues_label: str
    last_completed_empty: str
    last_completed_template: str
    selection_empty: str
    highlights_title: str
    highlights_empty: str
    metrics_title: str
    metrics_empty: str
    metrics_guidance_title: str
    metrics_guidance_empty: str
    metrics_metric_label: str
    metrics_before_label: str
    metrics_after_label: str
    run_summary_title: str
    run_summary_empty: str
    manifest_empty: str
    result_review_title: str
    compare_label: str
    manifest_button: str
    open_output_button: str
    mark_queued_button: str
    run_selected_button: str
    retry_degraded_button: str


@dataclass(slots=True, frozen=True)
class DesktopCopyConfig:
    global_text: GlobalCopyConfig
    runtime: RuntimeCopyConfig
    ingest: IngestCopyConfig
    summary: SummaryCopyConfig
    workspace: WorkspaceCopyConfig
    queue: QueueCopyConfig
    dashboard: DashboardCopyConfig
    tooltips: dict[str, str]

    def tooltip(self, key: str, default: str = "") -> str:
        return self.tooltips.get(key, default)


@dataclass(slots=True, frozen=True)
class StageControlConfig:
    key: str
    label: str
    source: str
    widget: str
    tier: str
    help: str = ""
    options: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None


@dataclass(slots=True, frozen=True)
class StageUiConfig:
    rail_label: str
    description: str
    summary_template: str
    simple_section_title: str
    advanced_section_title: str
    controls: tuple[StageControlConfig, ...]


@dataclass(slots=True, frozen=True)
class DesktopUiConfig:
    window: WindowConfig
    behavior: BehaviorConfig
    assets: AssetConfig
    layout: LayoutConfig
    preview: PreviewUiConfig
    theme: ThemeConfig
    copy: DesktopCopyConfig
    stages: dict[str, StageUiConfig]

    def stage(self, stage_id: str) -> StageUiConfig | None:
        return self.stages.get(stage_id)


def _parse_stage_ui(path: Path) -> dict[str, StageUiConfig]:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    stages: dict[str, StageUiConfig] = {}
    for stage_id, stage_payload in payload.get("stages", {}).items():
        raw_controls = stage_payload.get("controls", [])
        controls = tuple(
            StageControlConfig(
                key=item["key"],
                label=item["label"],
                source=item.get("source", "stage"),
                widget=item.get("widget", "text"),
                tier=item.get("tier", "simple"),
                help=item.get("help", ""),
                options=tuple(item.get("options", [])),
                minimum=float(item["minimum"]) if item.get("minimum") is not None else None,
                maximum=float(item["maximum"]) if item.get("maximum") is not None else None,
                step=float(item["step"]) if item.get("step") is not None else None,
            )
            for item in raw_controls
        )
        stages[stage_id] = StageUiConfig(
            rail_label=stage_payload["rail_label"],
            description=stage_payload["description"],
            summary_template=stage_payload["summary_template"],
            simple_section_title=stage_payload["simple_section_title"],
            advanced_section_title=stage_payload["advanced_section_title"],
            controls=controls,
        )
    return stages


def _parse_copy_config(path: Path) -> DesktopCopyConfig:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    runtime_payload = payload["runtime"]

    def runtime_status(section: str) -> RuntimeStatusCopyConfig:
        status_payload = runtime_payload[section]
        doctor_summary = status_payload.get("doctor_summary", runtime_payload["checking"]["doctor_summary"])
        model_summary = status_payload.get("model_summary", runtime_payload["checking"]["model_summary"])
        return RuntimeStatusCopyConfig(
            headline=status_payload["headline"],
            doctor_summary=doctor_summary,
            model_summary=model_summary,
            action=status_payload["action"],
        )

    return DesktopCopyConfig(
        global_text=GlobalCopyConfig(**payload["global"]),
        runtime=RuntimeCopyConfig(
            title=runtime_payload["title"],
            platform_empty=runtime_payload["platform_empty"],
            focus_title=runtime_payload["focus_title"],
            focus_empty=runtime_payload["focus_empty"],
            packs_title=runtime_payload["packs_title"],
            packs_empty=runtime_payload["packs_empty"],
            actions_title=runtime_payload["actions_title"],
            actions_empty=runtime_payload["actions_empty"],
            locations_title=runtime_payload["locations_title"],
            locations_empty=runtime_payload["locations_empty"],
            open_location_button=runtime_payload["open_location_button"],
            location_labels=dict(runtime_payload.get("location_labels", {})),
            checking=runtime_status("checking"),
            ready=runtime_status("ready"),
            watch=runtime_status("watch"),
            attention=runtime_status("attention"),
        ),
        ingest=IngestCopyConfig(**payload["ingest"]),
        summary=SummaryCopyConfig(**payload["summary"]),
        workspace=WorkspaceCopyConfig(**payload["workspace"]),
        queue=QueueCopyConfig(**payload["queue"]),
        dashboard=DashboardCopyConfig(**payload["dashboard"]),
        tooltips=dict(payload.get("tooltips", {})),
    )


def load_ui_config(path: str | Path | None = None) -> DesktopUiConfig:
    config_path = resolve_repo_path(path or "config/desktop_ui.toml")
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    stage_path = config_path.parent / "desktop_stage_ui.toml"
    copy_path = config_path.parent / "desktop_copy.toml"
    return DesktopUiConfig(
        window=WindowConfig(**payload["window"]),
        behavior=BehaviorConfig(**payload["behavior"]),
        assets=AssetConfig(**payload["assets"]),
        layout=LayoutConfig(**payload["layout"]),
        preview=PreviewUiConfig(
            default_stage=payload["preview"]["default_stage"],
            default_comparison_mode=payload["preview"]["default_comparison_mode"],
            default_fidelity_mode=payload["preview"]["default_fidelity_mode"],
            default_sample_start_seconds=float(payload["preview"]["default_sample_start_seconds"]),
            default_sample_duration_seconds=float(payload["preview"]["default_sample_duration_seconds"]),
            comparison_modes=tuple(payload["preview"]["comparison_modes"]),
            fidelity_modes=tuple(payload["preview"]["fidelity_modes"]),
            upscale_preview_width=int(payload["preview"]["upscale_preview_width"]),
            upscale_preview_height=int(payload["preview"]["upscale_preview_height"]),
        ),
        theme=ThemeConfig(**payload["theme"]),
        copy=_parse_copy_config(copy_path),
        stages=_parse_stage_ui(stage_path),
    )
