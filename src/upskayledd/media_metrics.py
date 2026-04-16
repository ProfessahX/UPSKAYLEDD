from __future__ import annotations

from typing import Any

from upskayledd.config import ConversionGuidanceConfig


def _safe_int(value: str | int | float | None) -> int | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _safe_float(value: str | int | float | None) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fps_to_float(rate: str | None) -> float | None:
    if not rate or rate in {"0/0", "N/A"}:
        return None
    if "/" in rate:
        numerator, denominator = rate.split("/", maxsplit=1)
        numerator_value = _safe_float(numerator)
        denominator_value = _safe_float(denominator)
        if numerator_value is None or denominator_value in (None, 0.0):
            return None
        return numerator_value / denominator_value
    return _safe_float(rate)


def _primary_container_name(value: str | None) -> str:
    if not value:
        return "unknown"
    return value.split(",", maxsplit=1)[0].strip().lower() or "unknown"


def _unique_strings(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        if not value:
            continue
        normalized = str(value).strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return items


def _message(
    config: ConversionGuidanceConfig,
    key: str,
    **kwargs: object,
) -> str | None:
    template = config.messages.get(key, "").strip()
    if not template:
        return None
    try:
        return template.format(**kwargs)
    except Exception:  # noqa: BLE001
        return template


def summarize_media_probe(payload: dict[str, Any]) -> dict[str, Any]:
    format_payload = dict(payload.get("format", {}))
    streams = list(payload.get("streams", []))
    chapters = list(payload.get("chapters", []))

    video_streams = [stream for stream in streams if str(stream.get("codec_type", "")).lower() == "video"]
    audio_streams = [stream for stream in streams if str(stream.get("codec_type", "")).lower() == "audio"]
    subtitle_streams = [stream for stream in streams if str(stream.get("codec_type", "")).lower() == "subtitle"]
    other_streams = [
        stream
        for stream in streams
        if str(stream.get("codec_type", "")).lower() not in {"video", "audio", "subtitle"}
    ]

    primary_video = dict(video_streams[0]) if video_streams else {}

    return {
        "container_name": _primary_container_name(format_payload.get("format_name")),
        "duration_seconds": _safe_float(format_payload.get("duration")),
        "size_bytes": _safe_int(format_payload.get("size")),
        "overall_bitrate_bps": _safe_int(format_payload.get("bit_rate")),
        "chapter_count": len(chapters),
        "stream_counts": {
            "video": len(video_streams),
            "audio": len(audio_streams),
            "subtitle": len(subtitle_streams),
            "other": len(other_streams),
        },
        "video": {
            "codec_name": primary_video.get("codec_name"),
            "width": primary_video.get("width"),
            "height": primary_video.get("height"),
            "display_aspect_ratio": primary_video.get("display_aspect_ratio"),
            "sample_aspect_ratio": primary_video.get("sample_aspect_ratio"),
            "avg_frame_rate": primary_video.get("avg_frame_rate") or primary_video.get("r_frame_rate"),
            "avg_frame_rate_fps": _fps_to_float(primary_video.get("avg_frame_rate") or primary_video.get("r_frame_rate")),
            "field_order": primary_video.get("field_order"),
            "pixel_format": primary_video.get("pix_fmt"),
            "bit_rate_bps": _safe_int(primary_video.get("bit_rate")),
        },
        "audio": {
            "stream_count": len(audio_streams),
            "codec_names": _unique_strings([stream.get("codec_name") for stream in audio_streams]),
            "languages": _unique_strings([dict(stream.get("tags", {})).get("language") for stream in audio_streams]),
            "max_channels": max((_safe_int(stream.get("channels")) or 0) for stream in audio_streams) if audio_streams else 0,
        },
        "subtitle": {
            "stream_count": len(subtitle_streams),
            "codec_names": _unique_strings([stream.get("codec_name") for stream in subtitle_streams]),
            "languages": _unique_strings([dict(stream.get("tags", {})).get("language") for stream in subtitle_streams]),
        },
    }


def compare_media_metrics(
    input_metrics: dict[str, Any],
    output_metrics: dict[str, Any],
    *,
    encode_profile_id: str | None,
    preserve_chapters: bool,
    config: ConversionGuidanceConfig,
) -> dict[str, Any]:
    input_size = _safe_int(input_metrics.get("size_bytes"))
    output_size = _safe_int(output_metrics.get("size_bytes"))
    input_bitrate = _safe_int(input_metrics.get("overall_bitrate_bps"))
    output_bitrate = _safe_int(output_metrics.get("overall_bitrate_bps"))
    input_video = dict(input_metrics.get("video", {}))
    output_video = dict(output_metrics.get("video", {}))
    input_audio = dict(input_metrics.get("audio", {}))
    output_audio = dict(output_metrics.get("audio", {}))
    input_subtitles = dict(input_metrics.get("subtitle", {}))
    output_subtitles = dict(output_metrics.get("subtitle", {}))

    input_width = _safe_int(input_video.get("width"))
    input_height = _safe_int(input_video.get("height"))
    output_width = _safe_int(output_video.get("width"))
    output_height = _safe_int(output_video.get("height"))
    input_pixels = (input_width or 0) * (input_height or 0)
    output_pixels = (output_width or 0) * (output_height or 0)

    size_ratio = round(output_size / input_size, 4) if input_size and output_size else None
    overall_bitrate_ratio = round(output_bitrate / input_bitrate, 4) if input_bitrate and output_bitrate else None
    resolution_scale = round(output_pixels / input_pixels, 4) if input_pixels and output_pixels else None
    fps_in = _safe_float(input_video.get("avg_frame_rate_fps"))
    fps_out = _safe_float(output_video.get("avg_frame_rate_fps"))
    audio_input_codecs = list(input_audio.get("codec_names", []))
    audio_output_codecs = list(output_audio.get("codec_names", []))
    subtitle_input_codecs = list(input_subtitles.get("codec_names", []))
    subtitle_output_codecs = list(output_subtitles.get("codec_names", []))

    guidance: list[str] = []
    if encode_profile_id in config.compatibility_profile_ids:
        message = _message(config, "compatibility")
        if message:
            guidance.append(message)
    if size_ratio is not None:
        if size_ratio > config.oversized_ratio:
            message = _message(config, "oversized")
            if message:
                guidance.append(message)
        elif size_ratio <= config.much_smaller_ratio:
            message = _message(config, "much_smaller")
            if message:
                guidance.append(message)
        elif size_ratio <= config.smaller_ratio:
            message = _message(config, "smaller")
            if message:
                guidance.append(message)
    if resolution_scale is not None and resolution_scale > 1.01 and size_ratio is not None and size_ratio < 1.0:
        message = _message(config, "resolution_up_smaller")
        if message:
            guidance.append(message)
    if audio_input_codecs and audio_output_codecs and set(audio_input_codecs) != set(audio_output_codecs):
        message = _message(
            config,
            "audio_transcode",
            from_codecs=", ".join(audio_input_codecs),
            to_codecs=", ".join(audio_output_codecs),
        )
        if message:
            guidance.append(message)
    if subtitle_input_codecs and subtitle_output_codecs and set(subtitle_input_codecs) != set(subtitle_output_codecs):
        message = _message(
            config,
            "subtitle_transcode",
            from_codecs=", ".join(subtitle_input_codecs),
            to_codecs=", ".join(subtitle_output_codecs),
        )
        if message:
            guidance.append(message)
    if int(output_subtitles.get("stream_count", 0) or 0) < int(input_subtitles.get("stream_count", 0) or 0):
        message = _message(config, "subtitle_dropped")
        if message:
            guidance.append(message)
    if preserve_chapters and int(output_metrics.get("chapter_count", 0) or 0) < int(input_metrics.get("chapter_count", 0) or 0):
        message = _message(config, "chapters_dropped")
        if message:
            guidance.append(message)
    if fps_in is not None and fps_out is not None and abs(fps_in - fps_out) > config.fps_change_tolerance:
        message = _message(
            config,
            "fps_changed",
            from_fps=f"{fps_in:.2f} fps",
            to_fps=f"{fps_out:.2f} fps",
        )
        if message:
            guidance.append(message)

    deduped_guidance = list(dict.fromkeys(guidance))
    return {
        "size_ratio": size_ratio,
        "overall_bitrate_ratio": overall_bitrate_ratio,
        "resolution_scale": resolution_scale,
        "container_changed": input_metrics.get("container_name") != output_metrics.get("container_name"),
        "video_codec_changed": input_video.get("codec_name") != output_video.get("codec_name"),
        "audio_codec_changed": set(audio_input_codecs) != set(audio_output_codecs),
        "subtitle_codec_changed": set(subtitle_input_codecs) != set(subtitle_output_codecs),
        "audio_stream_delta": int(output_audio.get("stream_count", 0) or 0) - int(input_audio.get("stream_count", 0) or 0),
        "subtitle_stream_delta": int(output_subtitles.get("stream_count", 0) or 0) - int(input_subtitles.get("stream_count", 0) or 0),
        "chapter_delta": int(output_metrics.get("chapter_count", 0) or 0) - int(input_metrics.get("chapter_count", 0) or 0),
        "guidance": deduped_guidance,
    }
