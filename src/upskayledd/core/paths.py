from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def repo_root() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            return Path(bundle_root).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def writable_app_root(app_name: str = "UPSKAYLEDD") -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / app_name


def expand_config_path(raw_path: str | Path) -> Path:
    text = str(raw_path)
    text = re.sub(
        r"\$([A-Za-z_][A-Za-z0-9_]*)",
        lambda match: (
            str(Path.home()) if match.group(1) == "HOME" else os.environ.get(match.group(1), match.group(0))
        ),
        text,
    )
    expanded = os.path.expandvars(os.path.expanduser(text))
    return Path(expanded)


def resolve_repo_path(raw_path: str | Path) -> Path:
    path = expand_config_path(raw_path)
    if path.is_absolute():
        return path
    return repo_root() / path


def resolve_runtime_path(raw_path: str | Path, app_name: str = "UPSKAYLEDD") -> Path:
    path = expand_config_path(raw_path)
    if path.is_absolute():
        return path
    if getattr(sys, "frozen", False):
        return writable_app_root(app_name) / path
    return repo_root() / path


def ensure_directory(path: str | Path) -> Path:
    resolved = resolve_runtime_path(path)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def normalize_path_for_platform(path: str | Path) -> str:
    resolved = expand_config_path(path)
    normalized = str(resolved)
    if os.name == "nt":
        normalized = normalized.replace("/", "\\")
    return normalized
