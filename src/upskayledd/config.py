from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from upskayledd.core.errors import ConfigError
from upskayledd.core.paths import repo_root, resolve_repo_path


@dataclass(slots=True, frozen=True)
class AppSettings:
    name: str
    default_container: str
    default_encode_profile_id: str
    default_output_root: str
    output_layout: str
    output_name_template: str
    output_collision_template: str
    state_db_path: str
    preview_cache_dir: str
    project_history_scope: str
    max_recent_targets: int
    supported_extensions: tuple[str, ...]
    probe_unknown_extensions: bool
    probe_extensionless_files: bool
    supported_output_containers: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class CompatibilitySettings:
    supported_previous_minor: int


@dataclass(slots=True, frozen=True)
class InspectorSettings:
    manual_review_threshold: float
    ntsc_fps: float
    ntsc_double_fps: float
    film_fps: float
    pal_fps: float
    sd_width_threshold: int
    sd_height_threshold: int


@dataclass(slots=True, frozen=True)
class PreviewSettings:
    default_mode: str
    default_duration_seconds: float
    default_fidelity_mode: str


@dataclass(slots=True, frozen=True)
class QueueSettings:
    restart_partial_encode: bool


@dataclass(slots=True, frozen=True)
class SupportSettings:
    bundle_output_dir: str
    include_full_paths: bool
    max_recent_jobs: int


@dataclass(slots=True, frozen=True)
class RuntimeActionRule:
    title: str
    category: str
    priority: int
    missing: str
    degraded: str
    only_when_recommended: bool = False


@dataclass(slots=True, frozen=True)
class RuntimeActionConfig:
    max_actions: int
    checks: dict[str, RuntimeActionRule]
    packs: dict[str, RuntimeActionRule]
    contexts: dict[str, RuntimeActionRule]


@dataclass(slots=True, frozen=True)
class PathSettings:
    model_dirs: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class ProfileDefinition:
    id: str
    label: str
    source_classes: tuple[str, ...]
    default_output_width: int
    default_output_height: int
    display_aspect_ratio: str
    default_container: str
    default_stages: tuple[str, ...]
    risky_stages: tuple[str, ...]
    stage_defaults: dict[str, dict[str, Any]]


@dataclass(slots=True, frozen=True)
class EncodeProfileDefinition:
    id: str
    label: str
    description: str
    container: str
    video_codec: str
    video_preset: str
    video_crf: int
    video_pixel_format: str
    audio_codec: str
    audio_bitrate_kbps: int | None
    subtitle_codec: str
    preserve_chapters: bool


@dataclass(slots=True, frozen=True)
class EncodeProfileConfig:
    default_profile_id: str
    profiles: tuple[EncodeProfileDefinition, ...]


@dataclass(slots=True, frozen=True)
class ModelFamilyDefinition:
    id: str
    label: str
    kind: str
    default: bool


@dataclass(slots=True, frozen=True)
class ModelRegistryConfig:
    custom_model_glob_patterns: tuple[str, ...]
    families: tuple[ModelFamilyDefinition, ...]


@dataclass(slots=True, frozen=True)
class ModelPackDefinition:
    id: str
    label: str
    url: str
    archive_format: str
    expected_paths: tuple[str, ...]
    recommended: bool = False
    size_hint_mb: int | None = None


@dataclass(slots=True, frozen=True)
class ModelPackConfig:
    packs: tuple[ModelPackDefinition, ...]


@dataclass(slots=True, frozen=True)
class FallbackFilterConfig:
    preview_default_upscale: str
    execution_default_upscale: str
    stage_filters: dict[str, dict[str, str]]


@dataclass(slots=True, frozen=True)
class StageModeDefinition:
    operation: str
    convert_to_rgbs: bool = False
    warning: str = ""
    model_family: str | None = None
    model_name: str | None = None
    scale: float | None = None
    resize_kernel: str | None = None
    strength: float | None = None
    output_format: str | None = None


@dataclass(slots=True, frozen=True)
class StagePresetConfig:
    stages: dict[str, dict[str, StageModeDefinition]]


@dataclass(slots=True, frozen=True)
class ConversionGuidanceConfig:
    oversized_ratio: float
    smaller_ratio: float
    much_smaller_ratio: float
    fps_change_tolerance: float
    compatibility_profile_ids: tuple[str, ...]
    messages: dict[str, str]


@dataclass(slots=True, frozen=True)
class DeliveryGuidanceConfig:
    archive_profile_ids: tuple[str, ...]
    smaller_profile_ids: tuple[str, ...]
    compatibility_profile_ids: tuple[str, ...]
    messages: dict[str, str]


@dataclass(slots=True, frozen=True)
class AppConfig:
    config_dir: Path
    app: AppSettings
    compatibility: CompatibilitySettings
    inspector: InspectorSettings
    preview: PreviewSettings
    queue: QueueSettings
    support: SupportSettings
    runtime_actions: RuntimeActionConfig
    paths: PathSettings
    profiles: tuple[ProfileDefinition, ...]
    encode: EncodeProfileConfig
    conversion_guidance: ConversionGuidanceConfig
    delivery_guidance: DeliveryGuidanceConfig
    model_registry: ModelRegistryConfig
    model_packs: ModelPackConfig
    fallback_filters: FallbackFilterConfig
    stage_presets: StagePresetConfig

    def profile_by_id(self, profile_id: str) -> ProfileDefinition:
        for profile in self.profiles:
            if profile.id == profile_id:
                return profile
        raise ConfigError(f"Unknown profile id: {profile_id}")

    def encode_profile_by_id(self, encode_profile_id: str) -> EncodeProfileDefinition:
        for profile in self.encode.profiles:
            if profile.id == encode_profile_id:
                return profile
        raise ConfigError(f"Unknown encode profile id: {encode_profile_id}")

    def stage_mode(self, stage_id: str, mode: str | None) -> StageModeDefinition | None:
        stage_modes = self.stage_presets.stages.get(stage_id, {})
        selected_mode = mode or "default"
        return stage_modes.get(selected_mode)

    def supported_output_containers(self) -> tuple[str, ...]:
        return self.app.supported_output_containers


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Missing config file: {path}")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _load_profiles(config_dir: Path) -> tuple[ProfileDefinition, ...]:
    payload = _read_toml(config_dir / "profiles.toml")
    profiles: list[ProfileDefinition] = []
    for item in payload.get("profiles", []):
        profiles.append(
            ProfileDefinition(
                id=item["id"],
                label=item["label"],
                source_classes=tuple(item.get("source_classes", [])),
                default_output_width=int(item["default_output_width"]),
                default_output_height=int(item["default_output_height"]),
                display_aspect_ratio=item.get("display_aspect_ratio", "source"),
                default_container=item.get("default_container", "mkv"),
                default_stages=tuple(item.get("default_stages", [])),
                risky_stages=tuple(item.get("risky_stages", [])),
                stage_defaults=item.get("stage_defaults", {}),
            )
        )
    if not profiles:
        raise ConfigError("No profiles were loaded from config/profiles.toml")
    return tuple(profiles)


def _load_encode_profiles(config_dir: Path, default_profile_id: str) -> EncodeProfileConfig:
    payload = _read_toml(config_dir / "encode_profiles.toml")
    defaults = payload.get("defaults", {})
    profiles = tuple(
        EncodeProfileDefinition(
            id=item["id"],
            label=item["label"],
            description=item.get("description", ""),
            container=str(item.get("container", "mkv")).strip().lower(),
            video_codec=item.get("video_codec", "libx265"),
            video_preset=item.get("video_preset", "medium"),
            video_crf=int(item.get("video_crf", 20)),
            video_pixel_format=item.get("video_pixel_format", "yuv420p10le"),
            audio_codec=item.get("audio_codec", "copy"),
            audio_bitrate_kbps=int(item["audio_bitrate_kbps"]) if item.get("audio_bitrate_kbps") is not None else None,
            subtitle_codec=item.get("subtitle_codec", "copy"),
            preserve_chapters=bool(item.get("preserve_chapters", True)),
        )
        for item in payload.get("profiles", [])
    )
    resolved_default = str(defaults.get("default_profile_id", default_profile_id)).strip()
    if not profiles:
        raise ConfigError("No encode profiles were loaded from config/encode_profiles.toml")
    if not any(profile.id == resolved_default for profile in profiles):
        raise ConfigError(f"Default encode profile '{resolved_default}' is not defined in config/encode_profiles.toml")
    return EncodeProfileConfig(default_profile_id=resolved_default, profiles=profiles)


def _load_model_registry(config_dir: Path) -> ModelRegistryConfig:
    payload = _read_toml(config_dir / "models.toml")
    registry = payload.get("registry", {})
    families_payload = payload.get("families", [])
    families = tuple(
        ModelFamilyDefinition(
            id=item["id"],
            label=item["label"],
            kind=item["kind"],
            default=bool(item.get("default", False)),
        )
        for item in families_payload
    )
    return ModelRegistryConfig(
        custom_model_glob_patterns=tuple(registry.get("custom_model_glob_patterns", [])),
        families=families,
    )


def _load_model_packs(config_dir: Path) -> ModelPackConfig:
    payload = _read_toml(config_dir / "model_packs.toml")
    packs = tuple(
        ModelPackDefinition(
            id=item["id"],
            label=item["label"],
            url=item["url"],
            archive_format=item.get("archive_format", "7z"),
            expected_paths=tuple(item.get("expected_paths", [])),
            recommended=bool(item.get("recommended", False)),
            size_hint_mb=int(item["size_hint_mb"]) if item.get("size_hint_mb") is not None else None,
        )
        for item in payload.get("packs", [])
    )
    return ModelPackConfig(packs=packs)


def _load_conversion_guidance(config_dir: Path) -> ConversionGuidanceConfig:
    payload = _read_toml(config_dir / "conversion_guidance.toml")
    thresholds = payload.get("thresholds", {})
    profiles = payload.get("profiles", {})
    messages = {
        str(key): str(value)
        for key, value in payload.get("messages", {}).items()
    }
    return ConversionGuidanceConfig(
        oversized_ratio=float(thresholds.get("oversized_ratio", 1.05)),
        smaller_ratio=float(thresholds.get("smaller_ratio", 0.95)),
        much_smaller_ratio=float(thresholds.get("much_smaller_ratio", 0.70)),
        fps_change_tolerance=float(thresholds.get("fps_change_tolerance", 0.35)),
        compatibility_profile_ids=tuple(str(item) for item in profiles.get("compatibility_ids", [])),
        messages=messages,
    )


def _load_delivery_guidance(config_dir: Path) -> DeliveryGuidanceConfig:
    payload = _read_toml(config_dir / "delivery_guidance.toml")
    profiles = payload.get("profiles", {})
    messages = {
        str(key): str(value)
        for key, value in payload.get("messages", {}).items()
    }
    return DeliveryGuidanceConfig(
        archive_profile_ids=tuple(str(item) for item in profiles.get("archive_ids", [])),
        smaller_profile_ids=tuple(str(item) for item in profiles.get("smaller_ids", [])),
        compatibility_profile_ids=tuple(str(item) for item in profiles.get("compatibility_ids", [])),
        messages=messages,
    )


def _load_stage_presets(config_dir: Path) -> StagePresetConfig:
    payload = _read_toml(config_dir / "stage_presets.toml")
    stages: dict[str, dict[str, StageModeDefinition]] = {}
    for stage_id, mode_payload in payload.get("stages", {}).items():
        stages[stage_id] = {}
        for mode_name, item in mode_payload.items():
            stages[stage_id][mode_name] = StageModeDefinition(
                operation=item["operation"],
                convert_to_rgbs=bool(item.get("convert_to_rgbs", False)),
                warning=item.get("warning", ""),
                model_family=item.get("model_family"),
                model_name=item.get("model_name"),
                scale=float(item["scale"]) if item.get("scale") is not None else None,
                resize_kernel=item.get("resize_kernel"),
                strength=float(item["strength"]) if item.get("strength") is not None else None,
                output_format=item.get("output_format"),
            )
    return StagePresetConfig(stages=stages)


def _load_runtime_actions(config_dir: Path) -> RuntimeActionConfig:
    payload = _read_toml(config_dir / "runtime_actions.toml")

    def build_rules(section: str) -> dict[str, RuntimeActionRule]:
        rules: dict[str, RuntimeActionRule] = {}
        for rule_id, item in payload.get(section, {}).items():
            rules[rule_id] = RuntimeActionRule(
                title=item["title"],
                category=item["category"],
                priority=int(item["priority"]),
                missing=item["missing"],
                degraded=item.get("degraded", item["missing"]),
                only_when_recommended=bool(item.get("only_when_recommended", False)),
            )
        return rules

    runtime_payload = payload.get("runtime", {})
    return RuntimeActionConfig(
        max_actions=int(runtime_payload.get("max_actions", 5)),
        checks=build_rules("checks"),
        packs=build_rules("packs"),
        contexts=build_rules("contexts"),
    )


def _normalize_model_dirs(raw_dirs: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw_dir in raw_dirs:
        candidate = str(raw_dir).strip()
        if not candidate:
            continue
        if candidate.startswith("%LOCALAPPDATA%") and os.name != "nt":
            continue
        if candidate.startswith("$HOME") and os.name == "nt":
            continue
        if candidate.startswith("~") and os.name == "nt":
            continue
        if candidate.startswith("$XDG_DATA_HOME") and os.name == "nt":
            continue
        if candidate not in normalized:
            normalized.append(candidate)
    return tuple(normalized)


def load_app_config(config_dir: str | Path | None = None) -> AppConfig:
    resolved_config_dir = (
        resolve_repo_path(config_dir)
        if config_dir is not None
        else repo_root() / "config"
    )
    defaults = _read_toml(resolved_config_dir / "defaults.toml")
    fallback_filters = _read_toml(resolved_config_dir / "fallback_filters.toml")
    app_defaults = defaults["app"]
    default_encode_profile_id = app_defaults.get("default_encode_profile_id", "hevc_balanced_archive")

    return AppConfig(
        config_dir=resolved_config_dir,
        app=AppSettings(
            name=app_defaults["name"],
            default_container=app_defaults["default_container"],
            default_encode_profile_id=default_encode_profile_id,
            default_output_root=app_defaults["default_output_root"],
            output_layout=app_defaults.get("output_layout", "preserve_relative"),
            output_name_template=app_defaults.get("output_name_template", "{stem}"),
            output_collision_template=app_defaults.get("output_collision_template", "__dup{index}"),
            state_db_path=app_defaults["state_db_path"],
            preview_cache_dir=app_defaults["preview_cache_dir"],
            project_history_scope=app_defaults["project_history_scope"],
            max_recent_targets=int(app_defaults.get("max_recent_targets", 6)),
            supported_extensions=tuple(sorted({str(item).lower() for item in app_defaults["supported_extensions"]})),
            probe_unknown_extensions=bool(app_defaults.get("probe_unknown_extensions", False)),
            probe_extensionless_files=bool(app_defaults.get("probe_extensionless_files", False)),
            supported_output_containers=tuple(
                str(item).strip().lower()
                for item in app_defaults.get(
                    "supported_output_containers",
                    [app_defaults["default_container"]],
                )
            ),
        ),
        compatibility=CompatibilitySettings(
            supported_previous_minor=int(defaults["compatibility"]["supported_previous_minor"])
        ),
        inspector=InspectorSettings(
            manual_review_threshold=float(defaults["inspector"]["manual_review_threshold"]),
            ntsc_fps=float(defaults["inspector"]["ntsc_fps"]),
            ntsc_double_fps=float(defaults["inspector"].get("ntsc_double_fps", 59.94)),
            film_fps=float(defaults["inspector"]["film_fps"]),
            pal_fps=float(defaults["inspector"]["pal_fps"]),
            sd_width_threshold=int(defaults["inspector"]["sd_width_threshold"]),
            sd_height_threshold=int(defaults["inspector"]["sd_height_threshold"]),
        ),
        preview=PreviewSettings(
            default_mode=defaults["preview"]["default_mode"],
            default_duration_seconds=float(defaults["preview"]["default_duration_seconds"]),
            default_fidelity_mode=defaults["preview"]["default_fidelity_mode"],
        ),
        queue=QueueSettings(
            restart_partial_encode=bool(defaults["queue"]["restart_partial_encode"])
        ),
        support=SupportSettings(
            bundle_output_dir=defaults["support"]["bundle_output_dir"],
            include_full_paths=bool(defaults["support"]["include_full_paths"]),
            max_recent_jobs=int(defaults["support"]["max_recent_jobs"]),
        ),
        runtime_actions=_load_runtime_actions(resolved_config_dir),
        paths=PathSettings(
            model_dirs=_normalize_model_dirs(defaults["paths"]["model_dirs"])
        ),
        profiles=_load_profiles(resolved_config_dir),
        encode=_load_encode_profiles(resolved_config_dir, default_encode_profile_id),
        conversion_guidance=_load_conversion_guidance(resolved_config_dir),
        delivery_guidance=_load_delivery_guidance(resolved_config_dir),
        model_registry=_load_model_registry(resolved_config_dir),
        model_packs=_load_model_packs(resolved_config_dir),
        fallback_filters=FallbackFilterConfig(
            preview_default_upscale=fallback_filters["preview"]["default_upscale"],
            execution_default_upscale=fallback_filters["execution"]["default_upscale"],
            stage_filters=fallback_filters.get("stage_filters", {}),
        ),
        stage_presets=_load_stage_presets(resolved_config_dir),
    )
