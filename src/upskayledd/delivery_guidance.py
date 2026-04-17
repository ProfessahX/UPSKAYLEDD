from __future__ import annotations

from typing import Any

from upskayledd.config import AppConfig, EncodeProfileDefinition
from upskayledd.core.errors import ConfigError
from upskayledd.models import InspectionReport


TEXT_FRIENDLY_SUBTITLE_CODECS = {"ass", "mov_text", "ssa", "subrip", "text", "webvtt"}


class DeliveryGuidanceBuilder:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def build(
        self,
        reports: list[InspectionReport],
        output_policy: dict[str, Any],
    ) -> dict[str, Any]:
        selected_profile_id, selected_profile = self._resolve_selected_profile(output_policy)
        facts = self._source_facts(reports)

        selected_entry = self._profile_entry(
            selected_profile,
            output_policy=output_policy,
            facts=facts,
            selected=True,
        )
        alternatives = [
            self._profile_entry(
                profile,
                output_policy=output_policy,
                facts=facts,
                selected=False,
            )
            for profile in self.config.encode.profiles
            if profile.id != selected_profile_id
        ]
        return {
            "selected_profile_id": selected_profile_id,
            "selected_profile_label": selected_profile.label,
            "selected_messages": selected_entry["messages"],
            "selected_facts": selected_entry["facts"],
            "selected_status": selected_entry["status"],
            "selected_is_selected": True,
            "alternative_profiles": alternatives,
            "source_facts": facts,
        }

    def _profile_entry(
        self,
        profile: EncodeProfileDefinition,
        *,
        output_policy: dict[str, Any],
        facts: dict[str, Any],
        selected: bool,
    ) -> dict[str, Any]:
        messages: list[str] = []
        status = "alternative"

        if profile.id in self.config.delivery_guidance.archive_profile_ids:
            messages.append(self._message("archive"))
            status = "archive"
        if profile.id in self.config.delivery_guidance.smaller_profile_ids:
            messages.append(self._message("smaller"))
            status = "smaller_file"
        if profile.id in self.config.delivery_guidance.compatibility_profile_ids:
            messages.append(self._message("compatibility"))
            status = "compatibility"

        if facts["has_image_subtitles"]:
            if profile.container == "mp4" or profile.subtitle_codec != "copy":
                messages.append(self._message("subtitle_risk"))
                status = "watch"
            else:
                messages.append(self._message("subtitle_preserve"))

        max_channels = int(facts.get("max_audio_channels", 0) or 0)
        if max_channels > 2:
            if profile.audio_codec == "copy":
                messages.append(self._message("audio_preserve", channels=max_channels))
            else:
                messages.append(
                    self._message(
                        "audio_transcode",
                        channels=max_channels,
                        audio_codec=profile.audio_codec,
                    )
                )

        if facts["uniform_geometry"] and output_policy.get("width") and output_policy.get("height"):
            width = int(output_policy.get("width") or 0)
            height = int(output_policy.get("height") or 0)
            source_width = int(facts.get("source_width", 0) or 0)
            source_height = int(facts.get("source_height", 0) or 0)
            source_pixels = source_width * source_height
            target_pixels = width * height
            if source_pixels and target_pixels > source_pixels:
                scale = target_pixels / source_pixels
                messages.append(
                    self._message(
                        "upscale_target",
                        width=width,
                        height=height,
                        scale=f"{scale:.2f}",
                    )
                )

        if facts["chapter_count"] > 0:
            messages.append(self._message("chapters_preserve" if profile.preserve_chapters else "chapters_drop"))

        if facts["batch_outliers"]:
            messages.append(self._message("batch_outliers"))

        fact_tags = self._build_fact_tags(profile, facts)
        deduped_messages = [message for message in dict.fromkeys(messages) if message]
        if selected and status == "alternative":
            status = "selected"
        return {
            "id": profile.id,
            "label": profile.label,
            "status": status,
            "is_selected": selected,
            "container": profile.container,
            "video_codec": profile.video_codec,
            "audio_codec": profile.audio_codec,
            "subtitle_codec": profile.subtitle_codec,
            "facts": fact_tags,
            "messages": deduped_messages,
        }

    def describe_profile(self, profile_id: str) -> dict[str, Any]:
        profile = self.config.encode_profile_by_id(profile_id)
        return {
            "id": profile.id,
            "label": profile.label,
            "facts": self._build_fact_tags(profile, None),
        }

    def _resolve_selected_profile(
        self,
        output_policy: dict[str, Any],
    ) -> tuple[str, EncodeProfileDefinition]:
        selected_profile_id = str(output_policy.get("encode_profile_id") or "").strip()
        if not selected_profile_id:
            selected_profile_id = self.config.encode.default_profile_id
        try:
            return selected_profile_id, self.config.encode_profile_by_id(selected_profile_id)
        except ConfigError:
            fallback_id = self.config.encode.default_profile_id
            return fallback_id, self.config.encode_profile_by_id(fallback_id)

    def _source_facts(self, reports: list[InspectionReport]) -> dict[str, Any]:
        subtitle_codecs = sorted(
            {
                stream.codec_name.lower()
                for report in reports
                for stream in report.streams
                if stream.codec_type == "subtitle" and stream.codec_name
            }
        )
        max_audio_channels = max(
            (
                int(stream.channels or 0)
                for report in reports
                for stream in report.streams
                if stream.codec_type == "audio"
            ),
            default=0,
        )
        chapter_count = max((int(report.chapter_count or 0) for report in reports), default=0)
        geometries = {
            (int(stream.width or 0), int(stream.height or 0))
            for report in reports
            for stream in report.streams
            if stream.codec_type == "video" and stream.width and stream.height
        }
        uniform_geometry = len(geometries) == 1
        source_width = 0
        source_height = 0
        if uniform_geometry and geometries:
            source_width, source_height = next(iter(geometries))
        profile_ids = {report.recommended_profile_id for report in reports}
        return {
            "subtitle_codecs": subtitle_codecs,
            "has_image_subtitles": any(codec not in TEXT_FRIENDLY_SUBTITLE_CODECS for codec in subtitle_codecs),
            "max_audio_channels": max_audio_channels,
            "chapter_count": chapter_count,
            "uniform_geometry": uniform_geometry,
            "source_width": source_width,
            "source_height": source_height,
            "batch_outliers": len(profile_ids) > 1 or any(report.manual_review_required for report in reports),
        }

    def _message(self, key: str, **kwargs: object) -> str:
        template = self.config.delivery_guidance.messages.get(key, "").strip()
        if not template:
            return ""
        try:
            return template.format(**kwargs)
        except Exception:  # noqa: BLE001
            return template

    def _build_fact_tags(
        self,
        profile: EncodeProfileDefinition,
        facts: dict[str, Any] | None,
    ) -> list[dict[str, str]]:
        tag_rows: list[tuple[str, str]] = []

        if profile.id in self.config.delivery_guidance.archive_profile_ids:
            tag_rows.append(("info", self._message("fact_archive")))
            tag_rows.append(("success", self._message("fact_size_smaller")))
        if profile.id in self.config.delivery_guidance.smaller_profile_ids:
            tag_rows.append(("success", self._message("fact_smaller")))
        if profile.id in self.config.delivery_guidance.compatibility_profile_ids:
            tag_rows.append(("warning", self._message("fact_compatibility")))
            tag_rows.append(("warning", self._message("fact_size_maybe_larger")))

        if profile.audio_codec == "copy":
            tag_rows.append(("success", self._message("fact_audio_copy")))
        else:
            tag_rows.append(
                (
                    "warning" if profile.id in self.config.delivery_guidance.compatibility_profile_ids else "info",
                    self._message("fact_audio_transcode", audio_codec=profile.audio_codec),
                )
            )

        has_image_subtitles = bool((facts or {}).get("has_image_subtitles"))
        if profile.subtitle_codec == "copy":
            tag_rows.append(("success", self._message("fact_subtitle_copy")))
        elif has_image_subtitles:
            tag_rows.append(("warning", self._message("fact_subtitle_risk")))
        else:
            tag_rows.append(("info", self._message("fact_subtitle_text", subtitle_codec=profile.subtitle_codec)))

        tag_rows.append(
            (
                "success" if profile.preserve_chapters else "warning",
                self._message("fact_chapters_preserve" if profile.preserve_chapters else "fact_chapters_drop"),
            )
        )

        facts_payload: list[dict[str, str]] = []
        seen_labels: set[str] = set()
        for tone, label in tag_rows:
            normalized_label = str(label).strip()
            if not normalized_label or normalized_label in seen_labels:
                continue
            facts_payload.append({"tone": tone, "label": normalized_label})
            seen_labels.add(normalized_label)
        return facts_payload
