from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ToolStatus:
    name: str
    available: bool
    detail: str


def _which(name: str) -> ToolStatus:
    path = shutil.which(name)
    return ToolStatus(name=name, available=path is not None, detail=path or "not found")


def _module(name: str) -> ToolStatus:
    spec = importlib.util.find_spec(name)
    return ToolStatus(name=name, available=spec is not None, detail="installed" if spec else "not installed")


def _probe_nvidia() -> ToolStatus:
    path = shutil.which("nvidia-smi")
    if not path:
        return ToolStatus(name="nvidia", available=False, detail="nvidia-smi not found")
    completed = subprocess.run([path, "-L"], capture_output=True, text=True, check=False)
    detail = completed.stdout.strip() or completed.stderr.strip() or path
    return ToolStatus(name="nvidia", available=completed.returncode == 0, detail=detail)


def _probe_vulkan() -> ToolStatus:
    return ToolStatus(
        name="vulkan",
        available=bool(os.environ.get("VULKAN_SDK") or shutil.which("vulkaninfo")),
        detail=os.environ.get("VULKAN_SDK") or shutil.which("vulkaninfo") or "not detected",
    )


def _probe_vs_plugin(plugin_name: str) -> ToolStatus:
    if importlib.util.find_spec("vapoursynth") is None:
        return ToolStatus(name=plugin_name, available=False, detail="vapoursynth not installed")
    try:
        import vapoursynth as vs

        core = vs.core
        available = hasattr(core, plugin_name)
        return ToolStatus(
            name=plugin_name,
            available=available,
            detail="loaded" if available else "not loaded",
        )
    except Exception as exc:  # noqa: BLE001
        return ToolStatus(name=plugin_name, available=False, detail=str(exc))


def detect_environment() -> dict[str, ToolStatus]:
    return {
        "python": ToolStatus(name="python", available=True, detail=sys.version.split()[0]),
        "ffmpeg": _which("ffmpeg"),
        "ffprobe": _which("ffprobe"),
        "vspipe": _which("vspipe"),
        "vapoursynth": _module("vapoursynth"),
        "vsmlrt": _module("vsmlrt"),
        "ffms2": _probe_vs_plugin("ffms2"),
        "vsmlrt_ncnn": _probe_vs_plugin("ncnn"),
        "vsmlrt_trt": _probe_vs_plugin("trt"),
        "vsmlrt_trt_rtx": _probe_vs_plugin("trt_rtx"),
        "nvidia": _probe_nvidia(),
        "vulkan": _probe_vulkan(),
    }


def classify_path_rules(path: str | Path) -> list[str]:
    raw = str(Path(path))
    notes: list[str] = []
    if os.name == "nt":
        if raw.startswith("\\\\"):
            notes.append("windows_unc_path")
        if len(raw) >= 240:
            notes.append("windows_long_path_risk")
        if ":" in raw[:3]:
            notes.append("windows_drive_letter")
    else:
        notes.append("linux_case_sensitive_paths")
    return notes
