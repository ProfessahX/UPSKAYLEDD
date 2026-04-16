from __future__ import annotations

from typing import Any

from upskayledd.config import AppConfig, EncodeProfileDefinition, ProfileDefinition
from upskayledd.models import ProjectManifest


class EncodeMuxPlanner:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def build_output_policy(
        self,
        profile: ProfileDefinition,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encode_profile = self.config.encode_profile_by_id(self.config.encode.default_profile_id)
        output_policy = {
            "container": encode_profile.container or profile.default_container or self.config.app.default_container,
            "width": profile.default_output_width,
            "height": profile.default_output_height,
            "display_aspect_ratio": profile.display_aspect_ratio,
            "output_root": self.config.app.default_output_root,
            **self._encode_profile_payload(encode_profile),
        }
        return self.apply_output_overrides(output_policy, overrides)

    def apply_output_overrides(
        self,
        base_output_policy: dict[str, Any],
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        output_policy = dict(base_output_policy)
        raw_overrides = dict(overrides or {})
        encode_profile_id = str(raw_overrides.pop("encode_profile_id", "") or "").strip()
        if encode_profile_id:
            output_policy.update(self._encode_profile_payload(self.config.encode_profile_by_id(encode_profile_id)))

        for key, value in raw_overrides.items():
            if value in (None, ""):
                continue
            output_policy[key] = value

        output_policy["container"] = str(output_policy.get("container", self.config.app.default_container)).strip().lower()
        output_policy["width"] = self._coerce_int(output_policy.get("width"), default=0)
        output_policy["height"] = self._coerce_int(output_policy.get("height"), default=0)
        output_policy["video_crf"] = self._coerce_int(output_policy.get("video_crf"), default=20)
        audio_bitrate = output_policy.get("audio_bitrate_kbps")
        if audio_bitrate in ("", None):
            output_policy.pop("audio_bitrate_kbps", None)
        else:
            output_policy["audio_bitrate_kbps"] = self._coerce_int(audio_bitrate, default=192)
        output_policy["preserve_chapters"] = bool(output_policy.get("preserve_chapters", True))
        output_policy.setdefault("encode_profile_id", self.config.encode.default_profile_id)
        output_policy.setdefault("output_root", self.config.app.default_output_root)
        output_policy.setdefault("display_aspect_ratio", "source")
        return output_policy

    def build_plan(self, manifest: ProjectManifest) -> dict[str, object]:
        profile = self.config.profile_by_id(manifest.selected_profile_id)
        resolved_policy = self.apply_output_overrides(
            self.build_output_policy(profile),
            manifest.output_policy,
        )
        return {
            "container": resolved_policy["container"],
            "encode_profile_id": resolved_policy["encode_profile_id"],
            "video_policy": resolved_policy["encode_profile_id"],
            "video_codec": resolved_policy["video_codec"],
            "video_preset": resolved_policy["video_preset"],
            "video_crf": resolved_policy["video_crf"],
            "video_pixel_format": resolved_policy["video_pixel_format"],
            "audio_codec": resolved_policy["audio_codec"],
            "audio_bitrate_kbps": resolved_policy.get("audio_bitrate_kbps"),
            "subtitle_codec": resolved_policy["subtitle_codec"],
            "preserve_chapters": resolved_policy["preserve_chapters"],
        }

    def _encode_profile_payload(self, encode_profile: EncodeProfileDefinition) -> dict[str, Any]:
        payload = {
            "encode_profile_id": encode_profile.id,
            "container": encode_profile.container,
            "video_codec": encode_profile.video_codec,
            "video_preset": encode_profile.video_preset,
            "video_crf": encode_profile.video_crf,
            "video_pixel_format": encode_profile.video_pixel_format,
            "audio_codec": encode_profile.audio_codec,
            "subtitle_codec": encode_profile.subtitle_codec,
            "preserve_chapters": encode_profile.preserve_chapters,
        }
        if encode_profile.audio_bitrate_kbps is not None:
            payload["audio_bitrate_kbps"] = encode_profile.audio_bitrate_kbps
        return payload

    def _coerce_int(self, raw: Any, *, default: int) -> int:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default
