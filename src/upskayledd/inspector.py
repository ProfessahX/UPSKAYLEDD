from __future__ import annotations

from pathlib import Path
from typing import Any

from upskayledd.config import AppConfig
from upskayledd.core.hashing import fingerprint_path
from upskayledd.integrations.ffprobe import FFprobeAdapter
from upskayledd.models import InspectionReport, StreamInfo


def _safe_float(value: str | float | int | None) -> float | None:
    if value in (None, "", "N/A"):
        return None
    return float(value)


def _fps_to_float(rate: str | None) -> float | None:
    if not rate or rate in {"0/0", "N/A"}:
        return None
    if "/" in rate:
        numerator, denominator = rate.split("/", maxsplit=1)
        if float(denominator) == 0:
            return None
        return float(numerator) / float(denominator)
    return float(rate)


def _near(value: float | None, target: float, tolerance: float = 0.15) -> bool:
    return value is not None and abs(value - target) <= tolerance


class Inspector:
    def __init__(self, config: AppConfig, ffprobe: FFprobeAdapter | None = None) -> None:
        self.config = config
        self.ffprobe = ffprobe or FFprobeAdapter()

    def discover_media_files(self, target: str | Path) -> list[Path]:
        resolved = Path(target)
        if resolved.is_file():
            return [resolved] if self._is_discoverable_media_file(resolved) else []
        supported = {suffix.lower() for suffix in self.config.app.supported_extensions}
        files = [
            path
            for path in resolved.rglob("*")
            if path.is_file() and (
                path.suffix.lower() in supported or self._should_probe_candidate(path)
            ) and self._is_discoverable_media_file(path, supported=supported)
        ]
        return sorted(files)

    def inspect_target(self, target: str | Path) -> list[InspectionReport]:
        return [self.inspect_path(path) for path in self.discover_media_files(target)]

    def inspect_path(self, path: str | Path) -> InspectionReport:
        resolved = Path(path)
        warnings: list[str] = []
        payload: dict[str, Any] = {}
        if self.ffprobe.is_available():
            payload = self.ffprobe.probe(resolved)
        else:
            warnings.append("ffprobe not available; using filesystem-only inspection.")

        streams = [self._stream_from_payload(item) for item in payload.get("streams", [])]
        format_payload = payload.get("format", {})
        chapter_count = len(payload.get("chapters", []))
        video_stream = next((stream for stream in streams if stream.codec_type == "video"), None)
        detected_source_class, confidence, artifact_hints = self._classify(video_stream)
        manual_review_required = confidence < self.config.inspector.manual_review_threshold
        recommended_profile_id = self._suggest_profile_id(detected_source_class, manual_review_required)
        summary = self._build_summary(
            resolved,
            video_stream,
            detected_source_class,
            artifact_hints,
            chapter_count,
            recommended_profile_id,
            manual_review_required,
        )

        return InspectionReport(
            source_path=str(resolved.resolve()),
            container_name=format_payload.get("format_name", resolved.suffix.lstrip(".")),
            duration_seconds=_safe_float(format_payload.get("duration")),
            size_bytes=int(format_payload["size"]) if format_payload.get("size") else None,
            streams=streams,
            chapter_count=chapter_count,
            source_fingerprint=fingerprint_path(resolved),
            detected_source_class=detected_source_class,
            confidence=confidence,
            artifact_hints=artifact_hints,
            recommended_profile_id=recommended_profile_id,
            manual_review_required=manual_review_required,
            warnings=warnings,
            summary=summary,
        )

    def _stream_from_payload(self, payload: dict[str, Any]) -> StreamInfo:
        tags = {str(key): str(value) for key, value in payload.get("tags", {}).items()}
        language = tags.get("language")
        return StreamInfo(
            index=int(payload.get("index", 0)),
            codec_type=payload.get("codec_type", "unknown"),
            codec_name=payload.get("codec_name", "unknown"),
            language=language,
            channels=payload.get("channels"),
            width=payload.get("width"),
            height=payload.get("height"),
            sample_aspect_ratio=payload.get("sample_aspect_ratio"),
            display_aspect_ratio=payload.get("display_aspect_ratio"),
            avg_frame_rate=payload.get("avg_frame_rate") or payload.get("r_frame_rate"),
            field_order=payload.get("field_order"),
            tags=tags,
        )

    def _classify(self, video_stream: StreamInfo | None) -> tuple[str, float, list[str]]:
        if video_stream is None:
            return "manual_review", 0.0, ["no_video_stream_detected"]

        artifact_hints: list[str] = []
        fps = _fps_to_float(video_stream.avg_frame_rate)
        field_order = (video_stream.field_order or "unknown").lower()
        width = video_stream.width or 0
        height = video_stream.height or 0

        if field_order not in {"progressive", "unknown"}:
            artifact_hints.append("interlaced_source_detected")
        if video_stream.codec_name == "mpeg2video":
            artifact_hints.append("mpeg2_compression_detected")
        if video_stream.display_aspect_ratio == "4:3":
            artifact_hints.append("preserve_4_3_geometry")

        is_sd = (
            width <= self.config.inspector.sd_width_threshold
            and height <= self.config.inspector.sd_height_threshold
        )

        if is_sd and (_near(fps, self.config.inspector.ntsc_fps) or _near(fps, self.config.inspector.film_fps)):
            if field_order == "progressive" and _near(fps, self.config.inspector.ntsc_fps):
                artifact_hints.append("telecine_or_mixed_cadence_suspected")
            return "sd_live_action_ntsc", 0.78, artifact_hints
        if is_sd and _near(fps, self.config.inspector.ntsc_double_fps, tolerance=0.35):
            artifact_hints.append("double_rate_ntsc_cadence_suspected")
            if field_order == "progressive":
                artifact_hints.append("telecine_or_repeated_fields_suspected")
            return "sd_live_action_ntsc", 0.74, artifact_hints
        if is_sd and _near(fps, self.config.inspector.pal_fps):
            return "sd_live_action_pal", 0.82, artifact_hints
        if is_sd:
            artifact_hints.append("unknown_sd_source_traits")
            return "sd_live_action_unknown_sd", 0.45, artifact_hints
        if width >= 1280 and field_order in {"progressive", "unknown"}:
            return "progressive_hd_cleanup", 0.74, artifact_hints
        return "manual_review", 0.3, artifact_hints

    def _suggest_profile_id(self, source_class: str, manual_review_required: bool) -> str:
        if manual_review_required or source_class == "manual_review":
            return "safe_review_required"
        for profile in self.config.profiles:
            if source_class in profile.source_classes:
                return profile.id
        return "safe_review_required"

    def _build_summary(
        self,
        path: Path,
        video_stream: StreamInfo | None,
        detected_source_class: str,
        artifact_hints: list[str],
        chapter_count: int,
        recommended_profile_id: str,
        manual_review_required: bool,
    ) -> list[str]:
        summary = [f"Source: {path.name}"]
        if video_stream:
            dimensions = f"{video_stream.width or '?'}x{video_stream.height or '?'}"
            dar = video_stream.display_aspect_ratio or "unknown DAR"
            summary.append(f"Video: {dimensions} ({dar})")
            if video_stream.avg_frame_rate:
                summary.append(f"Frame rate: {video_stream.avg_frame_rate}")
        summary.append(f"Detected source class: {detected_source_class}")
        if artifact_hints:
            summary.append("Hints: " + ", ".join(artifact_hints))
        summary.append(f"Recommended profile: {recommended_profile_id}")
        if chapter_count:
            summary.append(f"Chapters present: {chapter_count}")
        if manual_review_required:
            summary.append("Manual review recommended before risky stages.")
        return summary

    def _should_probe_candidate(self, path: Path) -> bool:
        if path.suffix:
            return self.config.app.probe_unknown_extensions and path.suffix.lower() not in {
                suffix.lower() for suffix in self.config.app.supported_extensions
            }
        return self.config.app.probe_extensionless_files

    def _is_discoverable_media_file(
        self,
        path: Path,
        *,
        supported: set[str] | None = None,
    ) -> bool:
        known_suffixes = supported or {suffix.lower() for suffix in self.config.app.supported_extensions}
        if path.suffix.lower() in known_suffixes:
            return True
        if not self._should_probe_candidate(path):
            return False
        if not self.ffprobe.is_available():
            return False
        try:
            payload = self.ffprobe.probe(path)
        except Exception:  # noqa: BLE001
            return False
        return any(
            str(stream.get("codec_type", "")).lower() == "video"
            for stream in payload.get("streams", [])
        )
