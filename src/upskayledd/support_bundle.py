from __future__ import annotations

import json
import platform
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from upskayledd import __version__
from upskayledd.config import AppConfig
from upskayledd.core.paths import ensure_directory, resolve_runtime_path
from upskayledd.models import utc_now
from upskayledd.project_store import ProjectStore


@dataclass(slots=True, frozen=True)
class SupportBundleResult:
    bundle_path: str
    created_at: str
    include_full_paths: bool
    entries: list[str]
    selected_job_id: str = ""
    job_history_count: int = 0
    job_history_truncated: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "bundle_path": self.bundle_path,
            "created_at": self.created_at,
            "include_full_paths": self.include_full_paths,
            "entries": list(self.entries),
            "selected_job_id": self.selected_job_id,
            "job_history_count": self.job_history_count,
            "job_history_truncated": self.job_history_truncated,
        }


class SupportBundleExporter:
    def __init__(self, config: AppConfig, store: ProjectStore) -> None:
        self.config = config
        self.store = store

    def export(
        self,
        *,
        doctor_report: dict[str, object],
        model_packs: dict[str, object],
        setup_actions: list[dict[str, object]],
        dashboard_snapshot: dict[str, object],
        session_state: dict[str, object] | None = None,
        selected_job_id: str | None = None,
        selected_run_manifest: dict[str, object] | None = None,
        output_path: str | Path | None = None,
        include_full_paths: bool | None = None,
    ) -> SupportBundleResult:
        include_paths = (
            self.config.support.include_full_paths
            if include_full_paths is None
            else bool(include_full_paths)
        )
        bundle_path = self._resolve_output_path(output_path)
        dashboard_payload = self._limit_dashboard_snapshot(dashboard_snapshot)
        path_replacements = self._path_replacements(
            dashboard_snapshot=dashboard_payload,
            session_state=session_state,
            selected_run_manifest=selected_run_manifest,
            selected_job_id=selected_job_id,
        )

        config_summary = {
            "app_name": self.config.app.name,
            "engine_version": __version__,
            "config_dir": str(self.config.config_dir),
            "default_output_root": self.config.app.default_output_root,
            "preview_cache_dir": self.config.app.preview_cache_dir,
            "state_db_path": self.config.app.state_db_path,
            "support_bundle_dir": self.config.support.bundle_output_dir,
            "model_dirs": list(self.config.paths.model_dirs),
            "supported_extensions": list(self.config.app.supported_extensions),
            "profiles": [profile.id for profile in self.config.profiles],
        }
        environment_summary = {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        }

        entries: dict[str, dict[str, object]] = {
            "bundle_manifest.json": {
                "app_name": self.config.app.name,
                "engine_version": __version__,
                "created_at": utc_now(),
                "include_full_paths": include_paths,
                "selected_job_id": selected_job_id or "",
                "job_history_count": len(dashboard_payload.get("jobs", [])),
                "job_history_truncated": bool(dashboard_payload.get("job_history_truncated", False)),
            },
            "doctor_report.json": doctor_report,
            "model_packs.json": model_packs,
            "setup_actions.json": {"actions": setup_actions},
            "dashboard_snapshot.json": dashboard_payload,
            "config_summary.json": config_summary,
            "environment_summary.json": environment_summary,
        }
        if session_state is not None:
            entries["session_state.json"] = session_state
        if selected_run_manifest is not None:
            entries["selected_run_manifest.json"] = selected_run_manifest

        with ZipFile(bundle_path, "w", compression=ZIP_DEFLATED) as archive:
            for entry_name, payload in entries.items():
                content = payload if include_paths else self._sanitize_payload(payload, path_replacements)
                archive.writestr(entry_name, json.dumps(content, indent=2, sort_keys=True))

        return SupportBundleResult(
            bundle_path=str(bundle_path),
            created_at=utc_now(),
            include_full_paths=include_paths,
            entries=sorted(entries.keys()),
            selected_job_id=selected_job_id or "",
            job_history_count=len(dashboard_payload.get("jobs", [])),
            job_history_truncated=bool(dashboard_payload.get("job_history_truncated", False)),
        )

    def _resolve_output_path(self, output_path: str | Path | None) -> Path:
        if output_path is None:
            output_dir = ensure_directory(self.config.support.bundle_output_dir)
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            return output_dir / f"upskayledd_support_{timestamp}.zip"
        resolved = resolve_runtime_path(output_path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved

    def _limit_dashboard_snapshot(self, dashboard_snapshot: dict[str, object]) -> dict[str, object]:
        payload = dict(dashboard_snapshot)
        jobs = list(payload.get("jobs", []))
        payload["job_history_truncated"] = len(jobs) > self.config.support.max_recent_jobs
        payload["jobs"] = jobs[: self.config.support.max_recent_jobs]
        return payload

    def _path_replacements(
        self,
        *,
        dashboard_snapshot: dict[str, object],
        session_state: dict[str, object] | None,
        selected_run_manifest: dict[str, object] | None,
        selected_job_id: str | None,
    ) -> dict[str, str]:
        raw_paths = {
            str(self.config.config_dir),
            str(resolve_runtime_path(self.config.app.default_output_root)),
            str(resolve_runtime_path(self.config.app.preview_cache_dir)),
            str(resolve_runtime_path(self.config.app.state_db_path)),
            str(resolve_runtime_path(self.config.support.bundle_output_dir)),
            *[str(resolve_runtime_path(path)) for path in self.config.paths.model_dirs],
        }
        for job in dashboard_snapshot.get("jobs", []):
            if isinstance(job, dict):
                raw_paths.update(
                    value
                    for key, value in job.items()
                    if isinstance(value, str) and "path" in key
                )
        if session_state:
            raw_paths.update(
                value
                for key, value in session_state.items()
                if isinstance(value, str) and ("path" in key or key in {"last_target", "selected_source"})
            )
        if selected_run_manifest:
            raw_paths.update(
                value
                for value in selected_run_manifest.get("input_files", [])
                if isinstance(value, str)
            )
            raw_paths.update(
                value
                for value in selected_run_manifest.get("output_files", [])
                if isinstance(value, str)
            )
        if selected_job_id:
            record = self.store.get_job(selected_job_id)
            if record is not None:
                raw_paths.add(record.source_path)
                raw_paths.add(record.payload_path)
        return dict(
            sorted(
                ((path, self._display_path(path)) for path in raw_paths if path),
                key=lambda item: len(item[0]),
                reverse=True,
            )
        )

    def _sanitize_payload(self, payload, replacements: dict[str, str], key_name: str = ""):
        if isinstance(payload, dict):
            return {
                key: self._sanitize_payload(value, replacements, key_name=key)
                for key, value in payload.items()
            }
        if isinstance(payload, list):
            return [self._sanitize_payload(item, replacements, key_name=key_name) for item in payload]
        if isinstance(payload, str):
            redacted = payload
            for original, replacement in replacements.items():
                if original and original in redacted:
                    redacted = redacted.replace(original, replacement)
            if self._is_path_like_key(key_name):
                return self._display_path(redacted)
            return redacted
        return payload

    def _display_path(self, value: str) -> str:
        stripped = value.rstrip("\\/")
        if not stripped:
            return value
        parts = re.split(r"[\\/]+", stripped)
        leaf = parts[-1]
        return leaf or stripped

    def _is_path_like_key(self, key_name: str) -> bool:
        lowered = key_name.lower()
        return "path" in lowered or lowered.endswith("_dir") or lowered.endswith("_files")
