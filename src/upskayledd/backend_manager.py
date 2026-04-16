from __future__ import annotations

import os
from uuid import uuid4
from pathlib import Path

from upskayledd.bootstrap import ModelPackInstaller
from upskayledd.config import AppConfig
from upskayledd.core.paths import resolve_runtime_path
from upskayledd.integrations.env_probe import ToolStatus, classify_path_rules, detect_environment
from upskayledd.models import BackendSelection, DoctorCheck, DoctorReport, utc_now


class BackendManager:
    def __init__(self, config: AppConfig, environment: dict[str, ToolStatus] | None = None) -> None:
        self.config = config
        self.environment = environment or detect_environment()

    def doctor(self) -> DoctorReport:
        checks = [
            DoctorCheck(
                name=status.name,
                status="healthy" if status.available else "missing",
                detail=status.detail,
            )
            for status in self.environment.values()
        ]
        checks.extend(self._path_checks())
        warnings = []
        if not self.environment["vapoursynth"].available or not self.environment["vsmlrt"].available:
            warnings.append("Canonical restoration stack is incomplete; planning can continue, execution will be degraded.")
        if not self.environment.get("ffms2", ToolStatus("ffms2", False, "missing")).available:
            warnings.append("VapourSynth source plugin is missing; canonical execution will fall back until FFMS2 is available.")
        if not self.environment.get("vspipe", ToolStatus("vspipe", False, "missing")).available:
            warnings.append("vspipe is missing; canonical execution cannot render frames into ffmpeg.")
        return DoctorReport(created_at=utc_now(), checks=checks, warnings=warnings)

    def choose_backend(self) -> BackendSelection:
        ffmpeg_ok = self.environment["ffmpeg"].available and self.environment["ffprobe"].available
        vapoursynth_ok = self.environment["vapoursynth"].available
        mlrt_ok = self.environment["vsmlrt"].available
        source_ok = self.environment.get("ffms2", ToolStatus("ffms2", False, "missing")).available
        pipe_ok = self.environment.get("vspipe", ToolStatus("vspipe", False, "missing")).available
        trt_ok = self.environment.get("vsmlrt_trt", ToolStatus("vsmlrt_trt", False, "missing")).available
        trt_rtx_ok = self.environment.get("vsmlrt_trt_rtx", ToolStatus("vsmlrt_trt_rtx", False, "missing")).available
        ncnn_ok = self.environment.get("vsmlrt_ncnn", ToolStatus("vsmlrt_ncnn", False, "missing")).available
        nvidia_ok = self.environment["nvidia"].available
        vulkan_ok = self.environment["vulkan"].available

        if ffmpeg_ok and vapoursynth_ok and mlrt_ok and source_ok and pipe_ok and nvidia_ok and (trt_ok or trt_rtx_ok):
            return BackendSelection(
                backend_id="tensorrt_nvidia",
                runtime="vs-mlrt + TensorRT/CUDA",
                reasons=["NVIDIA path detected", "TensorRT backend plugin loaded"],
                degraded=False,
            )
        if ffmpeg_ok and vapoursynth_ok and mlrt_ok and source_ok and pipe_ok and vulkan_ok and ncnn_ok:
            return BackendSelection(
                backend_id="vulkan_ml",
                runtime="vs-mlrt + Vulkan",
                reasons=["Vulkan-capable path detected", "NCNN backend plugin loaded"],
                degraded=False,
            )
        if ffmpeg_ok and vapoursynth_ok:
            return BackendSelection(
                backend_id="cpu_compat",
                runtime="VapourSynth + FFmpeg CPU compatibility path",
                reasons=["Canonical stack partially available", "ML runtime missing or unavailable"],
                degraded=True,
            )
        if ffmpeg_ok:
            return BackendSelection(
                backend_id="ffmpeg_degraded",
                runtime="FFmpeg degraded execution path",
                reasons=["FFmpeg is available but VapourSynth/vs-mlrt are not fully available"],
                degraded=True,
            )
        return BackendSelection(
            backend_id="planning_only",
            runtime="Inspection and planning only",
            reasons=["Execution dependencies are not fully available"],
            degraded=True,
        )

    def validate_runtime_path(self, path: str | Path) -> list[str]:
        return classify_path_rules(path)

    def _path_checks(self) -> list[DoctorCheck]:
        checks = [
            self._check_writable_directory("preview_cache_dir", self.config.app.preview_cache_dir),
            self._check_writable_directory("output_root", self.config.app.default_output_root),
        ]
        installer = ModelPackInstaller(self.config)
        for pack in self.config.model_packs.packs:
            checks.append(
                DoctorCheck(
                    name=f"model_pack:{pack.id}",
                    status="healthy" if installer.is_installed(pack) else "degraded",
                    detail="installed" if installer.is_installed(pack) else "not installed",
                )
            )
        for raw_path in self.config.paths.model_dirs:
            resolved = resolve_runtime_path(raw_path)
            if resolved.exists():
                checks.append(
                    DoctorCheck(
                        name=f"model_dir:{resolved}",
                        status="healthy",
                        detail="configured model directory exists",
                    )
                )
            else:
                checks.append(
                    DoctorCheck(
                        name=f"model_dir:{resolved}",
                        status="degraded",
                        detail="configured model directory does not exist yet",
                    )
                )
        return checks

    def _check_writable_directory(self, name: str, raw_path: str | Path) -> DoctorCheck:
        resolved = resolve_runtime_path(raw_path)
        try:
            resolved.mkdir(parents=True, exist_ok=True)
            probe_file = resolved / f".upskayledd_write_test_{os.getpid()}_{uuid4().hex}"
            probe_file.write_text("ok", encoding="utf-8")
            probe_file.unlink(missing_ok=True)
            detail = f"writable ({resolved})"
            status = "healthy"
        except OSError as exc:
            detail = f"not writable ({resolved}): {exc}"
            status = "missing"
        path_rules = ",".join(classify_path_rules(resolved))
        if path_rules:
            detail = f"{detail}; path_rules={path_rules}"
        return DoctorCheck(name=name, status=status, detail=detail)
