from __future__ import annotations

from pathlib import Path

from upskayledd.config import AppConfig
from upskayledd.core.paths import resolve_runtime_path


class ModelRegistry:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def default_family_ids(self, kind: str | None = None) -> list[str]:
        family_ids = []
        for family in self.config.model_registry.families:
            if kind and family.kind != kind:
                continue
            if family.default:
                family_ids.append(family.id)
        return family_ids

    def configured_model_dirs(self) -> list[Path]:
        return [resolve_runtime_path(path) for path in self.config.paths.model_dirs]

    def discover_custom_models(self, extra_dirs: list[str] | None = None) -> list[Path]:
        directories = self.configured_model_dirs()
        if extra_dirs:
            directories.extend(resolve_runtime_path(path) for path in extra_dirs)
        discovered: list[Path] = []
        for directory in directories:
            if not directory.exists():
                continue
            for pattern in self.config.model_registry.custom_model_glob_patterns:
                discovered.extend(sorted(directory.rglob(pattern)))
        unique: list[Path] = []
        seen: set[str] = set()
        for path in discovered:
            key = str(path.resolve())
            if key not in seen:
                seen.add(key)
                unique.append(path.resolve())
        return unique
