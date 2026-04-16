from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import Any

from upskayledd.config import AppConfig, StageModeDefinition
from upskayledd.core.errors import ExternalToolError
from upskayledd.core.hashing import fingerprint_path
from upskayledd.core.paths import ensure_directory, resolve_runtime_path
from upskayledd.integrations.ffmpeg import FFmpegAdapter
from upskayledd.models import BackendSelection, PipelineStage, ProjectManifest


MODEL_FILE_MAP = {
    ("dpir", "drunet_color"): Path("dpir") / "drunet_color.onnx",
    ("dpir", "drunet_deblocking_color"): Path("dpir") / "drunet_deblocking_color.onnx",
    ("scunet", "scunet_color_real_psnr"): Path("scunet") / "scunet_color_real_psnr.onnx",
    ("swinir", "realSR_BSRGAN_DFO_s64w8_SwinIR_M_x2_PSNR"): Path("swinir") / "003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x2_PSNR.onnx",
    ("swinir", "realSR_BSRGAN_DFO_s64w8_SwinIR_M_x4_PSNR"): Path("swinir") / "003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x4_PSNR.onnx",
}


class VapourSynthAdapter:
    def __init__(self, config: AppConfig, ffmpeg: FFmpegAdapter | None = None, vspipe_executable: str = "vspipe") -> None:
        self.config = config
        self.ffmpeg = ffmpeg or FFmpegAdapter()
        self.vspipe_executable = vspipe_executable

    def is_available(self) -> bool:
        if shutil.which(self.vspipe_executable) is None:
            return False
        if importlib.util.find_spec("vapoursynth") is None:
            return False
        try:
            import vapoursynth as vs

            return hasattr(vs.core, "ffms2")
        except Exception:  # noqa: BLE001
            return False

    def execute_job(
        self,
        manifest: ProjectManifest,
        stage_plan: list[PipelineStage],
        source_path: str | Path,
        output_path: str | Path,
        backend_selection: BackendSelection,
        encode_plan: dict[str, object],
    ) -> dict[str, object]:
        if not self.is_available():
            raise ExternalToolError("Canonical VapourSynth execution is not available.")

        source_fingerprint = fingerprint_path(source_path)
        script_dir = ensure_directory(Path(self.config.app.preview_cache_dir).parent / "scripts")
        index_dir = ensure_directory(Path(self.config.app.preview_cache_dir).parent / "indexes")
        script_path = script_dir / f"{source_fingerprint[:12]}_{Path(source_path).stem}.vpy"
        index_path = index_dir / f"{source_fingerprint}.ffindex"
        operations, warnings, fallbacks = self._plan_operations(manifest, stage_plan, backend_selection)
        script_payload = self._render_script(
            source_path=source_path,
            index_path=index_path,
            output_policy=manifest.output_policy,
            backend_selection=backend_selection,
            operations=operations,
            selected_profile_id=manifest.selected_profile_id,
        )
        script_path.write_text(script_payload, encoding="utf-8")

        execution = self.ffmpeg.run_vspipe_pipeline(
            script_path=script_path,
            source_path=source_path,
            output_path=output_path,
            vspipe_executable=self.vspipe_executable,
            video_args=self._build_video_args(encode_plan),
            encode_plan=encode_plan,
        )
        execution["script_path"] = str(script_path.resolve())
        execution["warnings"] = warnings
        execution["fallbacks"] = list(execution["fallbacks"]) + fallbacks
        execution["operations"] = [item["label"] for item in operations]
        return execution

    def render_preview(
        self,
        manifest: ProjectManifest,
        stage_plan: list[PipelineStage],
        source_path: str | Path,
        output_path: str | Path,
        backend_selection: BackendSelection,
        start_frame: int,
        end_frame: int,
    ) -> dict[str, object]:
        if not self.is_available():
            raise ExternalToolError("Canonical VapourSynth execution is not available.")

        source_fingerprint = fingerprint_path(source_path)
        output_path = Path(output_path)
        script_path = output_path.with_suffix(".vpy")
        index_dir = ensure_directory(Path(self.config.app.preview_cache_dir).parent / "indexes")
        index_path = index_dir / f"{source_fingerprint}.ffindex"
        operations, warnings, fallbacks = self._plan_operations(manifest, stage_plan, backend_selection)
        script_payload = self._render_script(
            source_path=source_path,
            index_path=index_path,
            output_policy=manifest.output_policy,
            backend_selection=backend_selection,
            operations=operations,
            selected_profile_id=manifest.selected_profile_id,
        )
        script_path.write_text(script_payload, encoding="utf-8")
        rendered_path = self.ffmpeg.render_vspipe_preview(
            script_path=script_path,
            output_path=output_path,
            vspipe_executable=self.vspipe_executable,
            start_frame=start_frame,
            end_frame=end_frame,
        )
        return {
            "artifact_path": str(rendered_path.resolve()),
            "script_path": str(script_path.resolve()),
            "operations": [item["label"] for item in operations],
            "warnings": warnings,
            "fallbacks": fallbacks,
        }

    def _plan_operations(
        self,
        manifest: ProjectManifest,
        stage_plan: list[PipelineStage],
        backend_selection: BackendSelection,
    ) -> tuple[list[dict[str, Any]], list[str], list[str]]:
        output_width = int(manifest.output_policy.get("width") or 0)
        output_height = int(manifest.output_policy.get("height") or 0)
        operations: list[dict[str, Any]] = []
        warnings: list[str] = []
        fallbacks: list[str] = []

        for stage in stage_plan:
            if not stage.enabled:
                continue
            mode = str(stage.settings.get("mode", "")).strip() or None
            definition = self.config.stage_mode(stage.stage_id, mode)
            if definition is None:
                warnings.append(f"Stage '{stage.stage_id}' has no configured preset for mode '{mode or 'default'}'; it will be skipped.")
                fallbacks.append(f"{stage.stage_id}_preset_missing")
                continue

            planned = self._build_operation(stage, definition, output_width, output_height, backend_selection)
            if planned["warning"]:
                warnings.append(planned["warning"])
            if planned["fallback"]:
                fallbacks.append(planned["fallback"])
            if planned["operation"] != "noop":
                operations.append(planned)

        return operations, warnings, fallbacks

    def _build_operation(
        self,
        stage: PipelineStage,
        definition: StageModeDefinition,
        output_width: int,
        output_height: int,
        backend_selection: BackendSelection,
    ) -> dict[str, Any]:
        operation = definition.operation
        warning = definition.warning
        fallback = ""

        if operation == "swinir" and backend_selection.backend_id == "vulkan_ml":
            warning = (
                f"{warning} " if warning else ""
            ) + "SwinIR live-action upscale is not stable on the current NCNN/Vulkan backend; falling back to a conservative resize."
            return {
                "label": f"{stage.stage_id}:resize_backend_fallback",
                "operation": "resize",
                "warning": warning.strip(),
                "fallback": f"{stage.stage_id}_swinir_backend_fallback",
                "resize_kernel": definition.resize_kernel or "spline36",
                "width": output_width,
                "height": output_height,
            }

        if operation in {"dpir", "scunet", "swinir"}:
            model_family = definition.model_family or operation
            model_name = definition.model_name
            model_path = self._resolve_model_path(model_family, model_name)
            if model_path is None or not model_path.exists():
                fallback = f"{stage.stage_id}_{operation}_model_missing"
                if stage.stage_id == "upscale":
                    warning = (
                        f"{warning} " if warning else ""
                    ) + f"Model '{model_name}' is not installed for stage '{stage.stage_id}'; falling back to a conservative resize."
                    return {
                        "label": f"{stage.stage_id}:resize_fallback",
                        "operation": "resize",
                        "warning": warning.strip(),
                        "fallback": fallback,
                        "resize_kernel": definition.resize_kernel or "spline36",
                        "width": output_width,
                        "height": output_height,
                    }
                warning = (
                    f"{warning} " if warning else ""
                ) + f"Model '{model_name}' is not installed for stage '{stage.stage_id}'; falling back to a conservative median filter."
                return {
                    "label": f"{stage.stage_id}:median_fallback",
                    "operation": "median",
                    "warning": warning.strip(),
                    "fallback": fallback,
                }
            return {
                "label": f"{stage.stage_id}:{operation}",
                "operation": operation,
                "warning": warning,
                "fallback": "",
                "convert_to_rgbs": definition.convert_to_rgbs,
                "strength": definition.strength,
                "model_name": model_name,
            }

        if operation == "resize":
            return {
                "label": f"{stage.stage_id}:resize",
                "operation": "resize",
                "warning": warning,
                "fallback": "",
                "resize_kernel": definition.resize_kernel or "spline36",
                "width": output_width,
                "height": output_height,
            }

        if operation == "encode_passthrough":
            return {
                "label": f"{stage.stage_id}:encode_passthrough",
                "operation": "noop",
                "warning": "",
                "fallback": "",
            }

        if operation == "noop":
            return {
                "label": f"{stage.stage_id}:noop",
                "operation": "noop",
                "warning": warning,
                "fallback": f"{stage.stage_id}_noop" if warning else "",
            }

        return {
            "label": f"{stage.stage_id}:noop",
            "operation": "noop",
            "warning": f"Unsupported stage operation '{operation}' for '{stage.stage_id}'; skipping it.",
            "fallback": f"{stage.stage_id}_unsupported_operation",
        }

    def _render_script(
        self,
        source_path: str | Path,
        index_path: Path,
        output_policy: dict[str, Any],
        backend_selection: BackendSelection,
        operations: list[dict[str, Any]],
        selected_profile_id: str,
    ) -> str:
        source_matrix = self._source_matrix(selected_profile_id)
        output_matrix = self._output_matrix(int(output_policy.get("height") or 0), source_matrix)
        requires_ml = any(item["operation"] in {"dpir", "scunet", "swinir"} for item in operations)
        converted_to_rgbs = False

        lines = [
            "import vapoursynth as vs",
            "core = vs.core",
        ]
        if requires_ml:
            lines.append("import vsmlrt")
        lines.extend(
            [
                f"clip = core.ffms2.Source(source={str(Path(source_path).resolve())!r}, cache=True, cachefile={str(index_path.resolve())!r})",
            ]
        )

        for item in operations:
            if item["operation"] in {"dpir", "scunet", "swinir"} and not converted_to_rgbs:
                lines.append(f"clip = core.resize.Bicubic(clip, format=vs.RGBS, matrix_in_s={source_matrix!r})")
                converted_to_rgbs = True

            if item["operation"] == "dpir":
                strength = item.get("strength", 5.0)
                lines.append(
                    "clip = vsmlrt.DPIR("
                    f"clip, strength={strength}, model=vsmlrt.DPIRModel.{item['model_name']}, "
                    f"backend={self._backend_expression(backend_selection)})"
                )
            elif item["operation"] == "scunet":
                lines.append(
                    "clip = vsmlrt.SCUNet("
                    f"clip, model=vsmlrt.SCUNetModel.{item['model_name']}, "
                    f"backend={self._backend_expression(backend_selection)})"
                )
            elif item["operation"] == "swinir":
                lines.append(
                    "clip = vsmlrt.SwinIR("
                    f"clip, model=vsmlrt.SwinIRModel.{item['model_name']}, "
                    f"backend={self._backend_expression(backend_selection)})"
                )
            elif item["operation"] == "median":
                lines.append("clip = core.std.Median(clip)")
            elif item["operation"] == "resize":
                resize_call = self._resize_call(
                    kernel=str(item.get("resize_kernel", "spline36")),
                    width=int(item["width"]),
                    height=int(item["height"]),
                )
                lines.append(f"clip = {resize_call}")

        if converted_to_rgbs:
            lines.append(f"clip = core.resize.Bicubic(clip, format=vs.YUV420P10, matrix_s={output_matrix!r})")
        else:
            lines.append("clip = core.resize.Bicubic(clip, format=vs.YUV420P10)")
        lines.append("clip.set_output()")
        return "\n".join(lines) + "\n"

    def _resolve_model_path(self, model_family: str, model_name: str | None) -> Path | None:
        if model_name is None:
            return None
        relative = MODEL_FILE_MAP.get((model_family, model_name))
        if relative is None:
            return None
        for root in self._model_roots():
            candidate = root / relative
            if candidate.exists():
                return candidate
        return None

    def _plugin_root(self) -> Path | None:
        spec = importlib.util.find_spec("vapoursynth")
        if spec is None or spec.origin is None:
            return None
        return Path(spec.origin).resolve().parent / "plugins"

    def _model_roots(self) -> list[Path]:
        roots = [resolve_runtime_path(path) for path in self.config.paths.model_dirs]
        plugin_root = self._plugin_root()
        if plugin_root is not None:
            roots.append(plugin_root / "models")
        unique: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root.resolve()) if root.exists() else str(root)
            if key in seen:
                continue
            seen.add(key)
            unique.append(root)
        return unique

    def _build_video_args(self, encode_plan: dict[str, object]) -> list[str]:
        codec = str(encode_plan.get("video_codec", "libx265"))
        preset = str(encode_plan.get("video_preset", "medium"))
        crf = str(encode_plan.get("video_crf", 16))
        pixel_format = str(encode_plan.get("video_pixel_format", "yuv420p10le"))
        return ["-c:v", codec, "-preset", preset, "-crf", crf, "-pix_fmt", pixel_format]

    def _backend_expression(self, backend_selection: BackendSelection) -> str:
        if backend_selection.backend_id == "tensorrt_nvidia":
            return "vsmlrt.Backend.TRT(fp16=True, device_id=0)"
        if backend_selection.backend_id == "vulkan_ml":
            return "vsmlrt.Backend.NCNN_VK(fp16=True, device_id=0, num_streams=1)"
        return "vsmlrt.Backend.OV_CPU(fp16=False, num_streams=1)"

    def _resize_call(self, kernel: str, width: int, height: int) -> str:
        kernel_name = kernel.lower()
        if kernel_name == "lanczos":
            return f"core.resize.Lanczos(clip, width={width}, height={height})"
        if kernel_name == "bicubic":
            return f"core.resize.Bicubic(clip, width={width}, height={height})"
        return f"core.resize.Spline36(clip, width={width}, height={height})"

    def _source_matrix(self, selected_profile_id: str) -> str:
        lowered = selected_profile_id.lower()
        if "pal" in lowered:
            return "470bg"
        if "ntsc" in lowered:
            return "170m"
        return "709"

    def _output_matrix(self, output_height: int, source_matrix: str) -> str:
        if output_height >= 720:
            return "709"
        return source_matrix
