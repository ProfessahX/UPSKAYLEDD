from __future__ import annotations
import shutil
import subprocess
from pathlib import Path

from upskayledd.core.errors import ExternalToolError


class FFmpegAdapter:
    def __init__(self, executable: str = "ffmpeg") -> None:
        self.executable = executable

    def is_available(self) -> bool:
        return shutil.which(self.executable) is not None

    def extract_preview_clip(
        self,
        source_path: str | Path,
        output_path: str | Path,
        start_seconds: float,
        duration_seconds: float,
        video_filter: str | None = None,
    ) -> Path:
        if not self.is_available():
            raise ExternalToolError("ffmpeg is not available on PATH.")

        resolved_output = Path(output_path)
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.executable,
            "-y",
            "-ss",
            str(start_seconds),
            "-i",
            str(source_path),
            "-t",
            str(duration_seconds),
            "-map",
            "0:v:0",
            "-an",
            "-sn",
        ]
        if video_filter:
            command.extend(["-vf", video_filter])
        command.extend(
            [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(resolved_output),
            ]
        )
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise ExternalToolError(
                f"ffmpeg preview extraction failed: {completed.stderr.strip() or completed.stdout.strip()}"
            )
        return resolved_output

    def run_processing_pipeline(
        self,
        source_path: str | Path,
        output_path: str | Path,
        video_filters: list[str],
        encode_plan: dict[str, object] | None = None,
    ) -> dict[str, object]:
        resolved_output = Path(output_path)
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        filter_chain = ",".join(video_filters) if video_filters else None
        last_error = ""
        encode_plan = encode_plan or {}
        video_args = self._video_args_from_plan(encode_plan)

        for attempt in self._build_stream_attempts(video_source_index=0, encode_plan=encode_plan):
            command = [
                self.executable,
                "-y",
                "-i",
                str(source_path),
                *attempt["maps"],
                *self._chapter_args(encode_plan, source_index=0),
            ]
            if filter_chain:
                command.extend(["-vf", filter_chain])
            command.extend(
                [
                    *video_args,
                    *attempt["codecs"],
                    str(resolved_output),
                ]
            )
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
            )
            if completed.returncode == 0:
                return {
                    "output_path": str(resolved_output.resolve()),
                    "attempt": attempt["name"],
                    "stream_outcomes": attempt["stream_outcomes"],
                    "fallbacks": attempt["fallbacks"],
                    "filter_chain": filter_chain or "",
                }
            last_error = completed.stderr.strip() or completed.stdout.strip()

        raise ExternalToolError(f"ffmpeg processing failed after retries: {last_error}")

    def run_vspipe_pipeline(
        self,
        script_path: str | Path,
        source_path: str | Path,
        output_path: str | Path,
        vspipe_executable: str = "vspipe",
        video_args: list[str] | None = None,
        encode_plan: dict[str, object] | None = None,
    ) -> dict[str, object]:
        if not self.is_available():
            raise ExternalToolError("ffmpeg is not available on PATH.")
        if shutil.which(vspipe_executable) is None:
            raise ExternalToolError("vspipe is not available on PATH.")

        resolved_output = Path(output_path)
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        encode_plan = encode_plan or {}
        video_args = video_args or self._video_args_from_plan(encode_plan)
        last_error = ""

        for attempt in self._build_stream_attempts(video_source_index=1, encode_plan=encode_plan):
            vspipe_command = [vspipe_executable, str(script_path), "-", "-c", "y4m"]
            ffmpeg_command = [
                self.executable,
                "-y",
                "-i",
                "-",
                "-i",
                str(source_path),
                "-map_metadata",
                "1",
                *attempt["maps"],
                *self._chapter_args(encode_plan, source_index=1),
                *video_args,
                *attempt["codecs"],
                str(resolved_output),
            ]
            vspipe_process = subprocess.Popen(  # noqa: S603
                vspipe_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
            )
            try:
                assert vspipe_process.stdout is not None
                ffmpeg_process = subprocess.Popen(  # noqa: S603
                    ffmpeg_command,
                    stdin=vspipe_process.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                )
                try:
                    vspipe_process.stdout.close()
                    ffmpeg_stdout, ffmpeg_stderr = ffmpeg_process.communicate()
                finally:
                    if ffmpeg_process.stdout is not None:
                        ffmpeg_process.stdout.close()
                    if ffmpeg_process.stderr is not None:
                        ffmpeg_process.stderr.close()
                vspipe_stderr = (
                    vspipe_process.stderr.read().decode("utf-8", errors="replace")
                    if vspipe_process.stderr is not None
                    else ""
                )
                vspipe_return = vspipe_process.wait()
            finally:
                if vspipe_process.stderr is not None:
                    vspipe_process.stderr.close()
            if ffmpeg_process.returncode == 0 and vspipe_return == 0:
                return {
                    "output_path": str(resolved_output.resolve()),
                    "attempt": attempt["name"],
                    "stream_outcomes": attempt["stream_outcomes"],
                    "fallbacks": attempt["fallbacks"],
                }
            last_error = (ffmpeg_stderr or ffmpeg_stdout or vspipe_stderr).strip()

        raise ExternalToolError(f"ffmpeg/vspipe processing failed after retries: {last_error}")

    def render_vspipe_preview(
        self,
        script_path: str | Path,
        output_path: str | Path,
        vspipe_executable: str = "vspipe",
        start_frame: int | None = None,
        end_frame: int | None = None,
    ) -> Path:
        if not self.is_available():
            raise ExternalToolError("ffmpeg is not available on PATH.")
        if shutil.which(vspipe_executable) is None:
            raise ExternalToolError("vspipe is not available on PATH.")

        resolved_output = Path(output_path)
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        vspipe_command = [vspipe_executable]
        if start_frame is not None:
            vspipe_command.extend(["--start", str(start_frame)])
        if end_frame is not None:
            vspipe_command.extend(["--end", str(end_frame)])
        vspipe_command.extend([str(script_path), "-", "-c", "y4m"])
        ffmpeg_command = [
            self.executable,
            "-y",
            "-i",
            "-",
            "-an",
            "-sn",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(resolved_output),
        ]

        vspipe_process = subprocess.Popen(  # noqa: S603
            vspipe_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )
        try:
            assert vspipe_process.stdout is not None
            ffmpeg_process = subprocess.Popen(  # noqa: S603
                ffmpeg_command,
                stdin=vspipe_process.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            try:
                vspipe_process.stdout.close()
                ffmpeg_stdout, ffmpeg_stderr = ffmpeg_process.communicate()
            finally:
                if ffmpeg_process.stdout is not None:
                    ffmpeg_process.stdout.close()
                if ffmpeg_process.stderr is not None:
                    ffmpeg_process.stderr.close()
            vspipe_stderr = (
                vspipe_process.stderr.read().decode("utf-8", errors="replace")
                if vspipe_process.stderr is not None
                else ""
            )
            vspipe_return = vspipe_process.wait()
        finally:
            if vspipe_process.stderr is not None:
                vspipe_process.stderr.close()

        if ffmpeg_process.returncode != 0 or vspipe_return != 0:
            error_text = (ffmpeg_stderr or ffmpeg_stdout or vspipe_stderr).strip()
            raise ExternalToolError(f"ffmpeg/vspipe preview render failed: {error_text}")
        return resolved_output

    def _build_stream_attempts(self, video_source_index: int, encode_plan: dict[str, object]) -> list[dict[str, object]]:
        source = str(video_source_index)
        audio_codecs = self._audio_codec_args(encode_plan)
        subtitle_codecs = self._subtitle_codec_args(encode_plan)
        preserve_subtitles = any(item == "-c:s" for item in subtitle_codecs)
        chapter_action = "preserve" if bool(encode_plan.get("preserve_chapters", True)) else "drop"
        return [
            {
                "name": "preserve_all",
                "maps": ["-map", "0:v:0", "-map", f"{source}:a?"] + (["-map", f"{source}:s?"] if preserve_subtitles else []),
                "codecs": [*audio_codecs, *subtitle_codecs],
                "stream_outcomes": [
                    {"stream_type": "audio", "action": self._audio_action_label(encode_plan), "reason": self._audio_reason(encode_plan)},
                    {"stream_type": "subtitle", "action": self._subtitle_action_label(encode_plan), "reason": self._subtitle_reason(encode_plan)},
                    {"stream_type": "chapter", "action": chapter_action, "reason": self._chapter_reason(encode_plan)},
                ],
                "fallbacks": [],
            },
            {
                "name": "drop_subtitles",
                "maps": ["-map", "0:v:0", "-map", f"{source}:a?"],
                "codecs": audio_codecs,
                "stream_outcomes": [
                    {"stream_type": "audio", "action": self._audio_action_label(encode_plan), "reason": self._audio_reason(encode_plan)},
                    {"stream_type": "subtitle", "action": "drop", "reason": "ffmpeg_subtitle_copy_failed"},
                    {"stream_type": "chapter", "action": chapter_action, "reason": self._chapter_reason(encode_plan)},
                ],
                "fallbacks": ["subtitle_encode_failed_retry_without_subtitles"],
            },
            {
                "name": "video_only",
                "maps": ["-map", "0:v:0"],
                "codecs": [],
                "stream_outcomes": [
                    {"stream_type": "audio", "action": "drop", "reason": "ffmpeg_fallback_video_only"},
                    {"stream_type": "subtitle", "action": "drop", "reason": "ffmpeg_fallback_video_only"},
                    {"stream_type": "chapter", "action": "drop", "reason": "ffmpeg_fallback_video_only"},
                ],
                "fallbacks": ["audio_or_subtitle_copy_failed_retry_video_only"],
            },
        ]

    def _video_args_from_plan(self, encode_plan: dict[str, object]) -> list[str]:
        codec = str(encode_plan.get("video_codec", "libx264"))
        preset = str(encode_plan.get("video_preset", "medium"))
        crf = str(encode_plan.get("video_crf", 18))
        pixel_format = str(encode_plan.get("video_pixel_format", "yuv420p"))
        return ["-c:v", codec, "-preset", preset, "-crf", crf, "-pix_fmt", pixel_format]

    def _audio_codec_args(self, encode_plan: dict[str, object]) -> list[str]:
        audio_codec = str(encode_plan.get("audio_codec", "copy")).strip().lower()
        if audio_codec == "copy":
            return ["-c:a", "copy"]
        args = ["-c:a", audio_codec]
        bitrate = encode_plan.get("audio_bitrate_kbps")
        if bitrate not in (None, ""):
            args.extend(["-b:a", f"{int(bitrate)}k"])
        return args

    def _subtitle_codec_args(self, encode_plan: dict[str, object]) -> list[str]:
        subtitle_codec = str(encode_plan.get("subtitle_codec", "copy")).strip().lower()
        if subtitle_codec in {"", "none", "drop"}:
            return []
        return ["-c:s", subtitle_codec]

    def _chapter_args(self, encode_plan: dict[str, object], source_index: int) -> list[str]:
        return ["-map_chapters", str(source_index if bool(encode_plan.get("preserve_chapters", True)) else -1)]

    def _audio_action_label(self, encode_plan: dict[str, object]) -> str:
        return "preserve" if str(encode_plan.get("audio_codec", "copy")).strip().lower() == "copy" else "transcode"

    def _audio_reason(self, encode_plan: dict[str, object]) -> str:
        audio_codec = str(encode_plan.get("audio_codec", "copy")).strip().lower()
        return "ffmpeg_copy" if audio_codec == "copy" else f"ffmpeg_transcode_{audio_codec}"

    def _subtitle_action_label(self, encode_plan: dict[str, object]) -> str:
        subtitle_codec = str(encode_plan.get("subtitle_codec", "copy")).strip().lower()
        if subtitle_codec in {"", "none", "drop"}:
            return "drop"
        return "preserve" if subtitle_codec == "copy" else "transcode"

    def _subtitle_reason(self, encode_plan: dict[str, object]) -> str:
        subtitle_codec = str(encode_plan.get("subtitle_codec", "copy")).strip().lower()
        if subtitle_codec in {"", "none", "drop"}:
            return "disabled_by_output_policy"
        return "ffmpeg_copy" if subtitle_codec == "copy" else f"ffmpeg_transcode_{subtitle_codec}"

    def _chapter_reason(self, encode_plan: dict[str, object]) -> str:
        return "ffmpeg_copy" if bool(encode_plan.get("preserve_chapters", True)) else "disabled_by_output_policy"
