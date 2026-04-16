from __future__ import annotations

import importlib.util
import shutil
import subprocess
import urllib.request
from pathlib import Path

from upskayledd.config import AppConfig, ModelPackDefinition
from upskayledd.core.errors import ExternalToolError
from upskayledd.core.paths import ensure_directory, resolve_runtime_path


class ModelPackInstaller:
    def __init__(self, config: AppConfig, download_root: str | Path | None = None) -> None:
        self.config = config
        self.download_root = ensure_directory(download_root or "runtime/tmp/model-packs")

    def list_packs(self) -> list[dict[str, object]]:
        return [
            {
                "id": pack.id,
                "label": pack.label,
                "recommended": pack.recommended,
                "size_hint_mb": pack.size_hint_mb,
                "installed": self.is_installed(pack),
            }
            for pack in self.config.model_packs.packs
        ]

    def install(self, pack_id: str, force: bool = False) -> dict[str, object]:
        pack = self._pack_by_id(pack_id)
        install_root = self._install_root()

        if self.is_installed(pack) and not force:
            return {
                "pack_id": pack.id,
                "installed": True,
                "skipped": True,
                "message": f"{pack.label} is already installed.",
            }

        archive_path = self.download_root / Path(pack.url).name
        self._download(pack.url, archive_path)
        self._extract_archive(archive_path, install_root, pack.archive_format)
        missing = self._missing_expected_paths(pack)
        if missing:
            raise ExternalToolError(
                f"Model pack '{pack.id}' was extracted but expected files are still missing: {', '.join(missing)}"
            )
        return {
            "pack_id": pack.id,
            "installed": True,
            "skipped": False,
            "message": f"Installed {pack.label}.",
        }

    def install_recommended(self) -> list[dict[str, object]]:
        return [self.install(pack.id) for pack in self.config.model_packs.packs if pack.recommended]

    def is_installed(self, pack: ModelPackDefinition) -> bool:
        return not self._missing_expected_paths(pack)

    def _missing_expected_paths(self, pack: ModelPackDefinition) -> list[str]:
        roots = self._model_roots()
        if not roots:
            return list(pack.expected_paths)
        missing = []
        for relative in pack.expected_paths:
            expected_path = self._relative_model_path(relative)
            if not any((root / expected_path).exists() for root in roots):
                missing.append(relative)
        return missing

    def _pack_by_id(self, pack_id: str) -> ModelPackDefinition:
        for pack in self.config.model_packs.packs:
            if pack.id == pack_id:
                return pack
        raise ExternalToolError(f"Unknown model pack id: {pack_id}")

    def _plugin_root(self) -> Path | None:
        spec = importlib.util.find_spec("vapoursynth")
        if spec is None or spec.origin is None:
            return None
        return Path(spec.origin).resolve().parent / "plugins"

    def _install_root(self) -> Path:
        configured_dirs = [resolve_runtime_path(path) for path in self.config.paths.model_dirs]
        if configured_dirs:
            return ensure_directory(configured_dirs[0])
        plugin_root = self._plugin_root()
        if plugin_root is None:
            raise ExternalToolError("Unable to locate a writable model directory or VapourSynth plugin directory.")
        return ensure_directory(plugin_root / "models")

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

    def _relative_model_path(self, raw_relative: str) -> Path:
        relative = Path(raw_relative)
        if relative.parts and relative.parts[0] == "models":
            return Path(*relative.parts[1:])
        return relative

    def _download(self, url: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url) as response, destination.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)

    def _extract_archive(self, archive_path: Path, destination: Path, archive_format: str) -> None:
        if archive_format == "7z":
            bsdtar = shutil.which("bsdtar")
            if bsdtar:
                completed = subprocess.run(  # noqa: S603
                    [bsdtar, "-xf", str(archive_path), "-C", str(destination)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if completed.returncode == 0:
                    return
                error_text = completed.stderr.strip() or completed.stdout.strip()
            else:
                error_text = "bsdtar not available"

            py7zr_spec = importlib.util.find_spec("py7zr")
            if py7zr_spec is not None:
                import py7zr

                with py7zr.SevenZipFile(archive_path, mode="r") as archive:
                    archive.extractall(path=destination)
                return
            raise ExternalToolError(f"Unable to extract {archive_path.name}: {error_text}")

        raise ExternalToolError(f"Unsupported archive format: {archive_format}")
