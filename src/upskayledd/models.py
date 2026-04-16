from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from upskayledd import __version__
from upskayledd.core.errors import CompatibilityError


class ComparisonMode(StrEnum):
    SLIDER_WIPE = "slider_wipe"
    SIDE_BY_SIDE = "side_by_side"
    AB_TOGGLE = "ab_toggle"


class FidelityMode(StrEnum):
    EXACT = "exact"
    APPROXIMATE = "approximate"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"
    PAUSED = "paused"
    PLANNED = "planned"


SCHEMA_VERSIONS = {
    "inspection_report": "0.1",
    "project_manifest": "0.1",
    "preview_request": "0.1",
    "preview_result": "0.1",
    "run_manifest": "0.1",
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _minor_version(version: str) -> tuple[int, int]:
    major_text, minor_text = version.split(".", maxsplit=1)
    return int(major_text), int(minor_text)


def is_supported_schema(schema_name: str, schema_version: str) -> bool:
    current = SCHEMA_VERSIONS[schema_name]
    current_major, current_minor = _minor_version(current)
    incoming_major, incoming_minor = _minor_version(schema_version)
    if current_major != incoming_major:
        return False
    return incoming_minor in {current_minor, max(current_minor - 1, 0)}


def ensure_compatible_schema(schema_name: str, schema_version: str) -> None:
    if not is_supported_schema(schema_name, schema_version):
        raise CompatibilityError(
            f"Incompatible {schema_name} schema version {schema_version}; "
            f"current supported version is {SCHEMA_VERSIONS[schema_name]}"
        )


def _serialize(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: _serialize(val) for key, val in asdict(value).items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(val) for key, val in value.items()}
    return value


@dataclass(slots=True)
class StreamInfo:
    index: int
    codec_type: str
    codec_name: str
    language: str | None = None
    channels: int | None = None
    width: int | None = None
    height: int | None = None
    sample_aspect_ratio: str | None = None
    display_aspect_ratio: str | None = None
    avg_frame_rate: str | None = None
    field_order: str | None = None
    tags: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StreamInfo":
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(slots=True)
class PipelineStage:
    stage_id: str
    label: str
    enabled: bool
    settings: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PipelineStage":
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(slots=True)
class StreamOutcome:
    stream_type: str
    source_index: int
    action: str
    reason: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StreamOutcome":
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(slots=True)
class BackendSelection:
    backend_id: str
    runtime: str
    reasons: list[str] = field(default_factory=list)
    degraded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(slots=True)
class InspectionReport:
    source_path: str
    container_name: str
    duration_seconds: float | None
    size_bytes: int | None
    streams: list[StreamInfo]
    chapter_count: int
    source_fingerprint: str
    detected_source_class: str
    confidence: float
    artifact_hints: list[str]
    recommended_profile_id: str
    manual_review_required: bool
    warnings: list[str]
    summary: list[str]
    schema_name: str = "inspection_report"
    schema_version: str = SCHEMA_VERSIONS["inspection_report"]
    engine_version: str = __version__

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "InspectionReport":
        ensure_compatible_schema(payload["schema_name"], payload["schema_version"])
        data = dict(payload)
        data["streams"] = [StreamInfo.from_dict(item) for item in payload.get("streams", [])]
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(slots=True)
class ProjectManifest:
    project_id: str
    created_at: str
    source_files: list[str]
    selected_profile_id: str
    output_policy: dict[str, Any]
    resolved_pipeline_stages: list[PipelineStage]
    backend_preferences: list[str]
    model_preferences: list[str]
    batch_settings: dict[str, Any]
    per_file_overrides: dict[str, dict[str, Any]]
    custom_model_paths: list[str]
    hook_references: list[str]
    warnings: list[str]
    schema_name: str = "project_manifest"
    schema_version: str = SCHEMA_VERSIONS["project_manifest"]
    engine_version: str = __version__

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProjectManifest":
        ensure_compatible_schema(payload["schema_name"], payload["schema_version"])
        data = dict(payload)
        data["resolved_pipeline_stages"] = [
            PipelineStage.from_dict(item)
            for item in payload.get("resolved_pipeline_stages", [])
        ]
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(slots=True)
class PreviewRequest:
    preview_id: str
    source_path: str
    stage_id: str
    comparison_mode: ComparisonMode
    sample_start_seconds: float
    sample_duration_seconds: float
    render_settings: dict[str, Any]
    cache_key_inputs: dict[str, Any]
    fidelity_mode_request: FidelityMode
    created_at: str
    schema_name: str = "preview_request"
    schema_version: str = SCHEMA_VERSIONS["preview_request"]
    engine_version: str = __version__

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PreviewRequest":
        ensure_compatible_schema(payload["schema_name"], payload["schema_version"])
        data = dict(payload)
        data["comparison_mode"] = ComparisonMode(payload["comparison_mode"])
        data["fidelity_mode_request"] = FidelityMode(payload["fidelity_mode_request"])
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(slots=True)
class PreviewResult:
    preview_id: str
    cache_key: str
    comparison_mode: ComparisonMode
    fidelity_mode: FidelityMode
    cache_hit: bool
    artifact_paths: list[str]
    comparison_artifacts: dict[str, str]
    metadata_path: str
    warnings: list[str]
    created_at: str
    schema_name: str = "preview_result"
    schema_version: str = SCHEMA_VERSIONS["preview_result"]
    engine_version: str = __version__

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PreviewResult":
        ensure_compatible_schema(payload["schema_name"], payload["schema_version"])
        data = dict(payload)
        data["comparison_mode"] = ComparisonMode(payload["comparison_mode"])
        data["fidelity_mode"] = FidelityMode(payload["fidelity_mode"])
        data.setdefault("comparison_artifacts", {})
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(slots=True)
class RunManifest:
    run_id: str
    project_id: str
    input_files: list[str]
    final_pipeline: list[PipelineStage]
    actual_backend: dict[str, Any]
    models_used: list[str]
    output_files: list[str]
    encode_settings: dict[str, Any]
    stream_outcomes: list[StreamOutcome]
    warnings: list[str]
    fallbacks: list[str]
    errors: list[str]
    created_at: str
    schema_name: str = "run_manifest"
    schema_version: str = SCHEMA_VERSIONS["run_manifest"]
    engine_version: str = __version__

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunManifest":
        ensure_compatible_schema(payload["schema_name"], payload["schema_version"])
        data = dict(payload)
        data["final_pipeline"] = [
            PipelineStage.from_dict(item)
            for item in payload.get("final_pipeline", [])
        ]
        data["stream_outcomes"] = [
            StreamOutcome.from_dict(item)
            for item in payload.get("stream_outcomes", [])
        ]
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(slots=True)
class JobRecord:
    job_id: str
    project_id: str
    source_path: str
    status: JobStatus
    progress: float
    payload_path: str
    error_message: str | None = None
    updated_at: str = field(default_factory=utc_now)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "JobRecord":
        return cls(
            job_id=row["job_id"],
            project_id=row["project_id"],
            source_path=row["source_path"],
            status=JobStatus(row["status"]),
            progress=row["progress"],
            payload_path=row["payload_path"],
            error_message=row["error_message"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(slots=True)
class DoctorCheck:
    name: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(slots=True)
class DoctorReport:
    created_at: str
    checks: list[DoctorCheck]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)
