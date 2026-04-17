from __future__ import annotations

import os
import re
import shutil
import sys
import uuid
from pathlib import Path

WINDOWS_ENV_PATTERN = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")
WINDOWS_DRIVE_PATH_PATTERN = re.compile(r"^([A-Za-z]):[\\/]*(.*)$")


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


def _running_inside_wsl() -> bool:
    if os.name == "nt":
        return False
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        proc_version = Path("/proc/version").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "microsoft" in proc_version.lower()


def _translate_windows_path_for_wsl(text: str) -> str:
    if not _running_inside_wsl():
        return text
    match = WINDOWS_DRIVE_PATH_PATTERN.match(text)
    if not match:
        return text
    drive, tail = match.groups()
    normalized_tail = tail.replace("\\", "/").lstrip("/")
    if not normalized_tail:
        return f"/mnt/{drive.lower()}"
    return f"/mnt/{drive.lower()}/{normalized_tail}"


def expand_config_path(raw_path: str | Path) -> Path:
    text = str(raw_path)
    text = re.sub(
        r"\$([A-Za-z_][A-Za-z0-9_]*)",
        lambda match: (
            str(Path.home()) if match.group(1) == "HOME" else os.environ.get(match.group(1), match.group(0))
        ),
        text,
    )
    text = WINDOWS_ENV_PATTERN.sub(
        lambda match: os.environ.get(match.group(1), match.group(0)),
        text,
    )
    expanded = os.path.expandvars(os.path.expanduser(text))
    expanded = _translate_windows_path_for_wsl(expanded)
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


class RuntimeTemporaryDirectory:
    """Workspace/app-rooted temporary directory for runtime-safe scratch writes."""

    def __init__(
        self,
        root: str | Path = "runtime/scratch",
        *,
        prefix: str = "tmp",
        suffix: str = "",
        app_name: str = "UPSKAYLEDD",
        ignore_cleanup_errors: bool = False,
    ) -> None:
        base = resolve_runtime_path(root, app_name=app_name)
        base.mkdir(parents=True, exist_ok=True)
        folder_name = f"{prefix}{uuid.uuid4().hex}{suffix}"
        self.path = base / folder_name
        self.path.mkdir(parents=True, exist_ok=False)
        self.name = str(self.path)
        self.ignore_cleanup_errors = ignore_cleanup_errors
        self._cleaned = False

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        if self._cleaned:
            return
        try:
            shutil.rmtree(self.path)
        except FileNotFoundError:
            self._cleaned = True
            return
        except OSError:
            if self.ignore_cleanup_errors:
                self._cleaned = True
                return
            raise
        self._cleaned = True


def normalize_path_for_platform(path: str | Path) -> str:
    resolved = expand_config_path(path)
    normalized = str(resolved)
    if os.name == "nt":
        normalized = normalized.replace("/", "\\")
    return normalized
