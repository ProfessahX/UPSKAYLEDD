from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from upskayledd.backend_manager import BackendManager
from upskayledd.bootstrap import ModelPackInstaller
from upskayledd.config import AppConfig, load_app_config
from upskayledd.core.paths import resolve_runtime_path
from upskayledd.delivery_guidance import DeliveryGuidanceBuilder
from upskayledd.encode_mux import EncodeMuxPlanner
from upskayledd.inspector import Inspector
from upskayledd.integrations.ffprobe import FFprobeAdapter
from upskayledd.manifest_writer import read_artifact
from upskayledd.media_metrics import compare_media_metrics, summarize_media_probe
from upskayledd.model_registry import ModelRegistry
from upskayledd.models import ComparisonMode, FidelityMode, InspectionReport, JobRecord, PreviewResult, ProjectManifest
from upskayledd.platform_validation_matrix import build_platform_validation_payload
from upskayledd.pipeline_builder import PipelineBuilder
from upskayledd.preview_engine import PreviewEngine
from upskayledd.profile_resolver import ProfileResolver
from upskayledd.project_store import ProjectStore
from upskayledd.queue_runner import QueueRunner
from upskayledd.runtime_guidance import RuntimeGuidanceBuilder
from upskayledd.support_bundle import SupportBundleExporter


class AppService:
    """Shared app-facing entrypoints for CLI and future desktop shells."""

    RECENT_TARGETS_STATE_KEY = "recent_targets"

    def __init__(self, config_dir: str | None = None) -> None:
        self.config: AppConfig = load_app_config(config_dir)
        self.store = ProjectStore(self.config.app.state_db_path)
        self.inspector = Inspector(self.config)
        self.profile_resolver = ProfileResolver(self.config)
        self.model_registry = ModelRegistry(self.config)
        self.pipeline_builder = PipelineBuilder(self.config, self.model_registry)
        self.backend_manager = BackendManager(self.config)
        self.preview_engine = PreviewEngine(self.config, self.store)
        self.queue_runner = QueueRunner(self.store, self.config)
        self.ffprobe = FFprobeAdapter()
        self.model_pack_installer = ModelPackInstaller(self.config)
        self.encode_mux_planner = EncodeMuxPlanner(self.config)
        self.delivery_guidance_builder = DeliveryGuidanceBuilder(self.config)
        self.runtime_guidance = RuntimeGuidanceBuilder(self.config)
        self.support_bundle_exporter = SupportBundleExporter(self.config, self.store)

    def doctor_report(self) -> dict[str, Any]:
        payload = self.backend_manager.doctor().to_dict()
        payload["path_rules"] = self.backend_manager.validate_runtime_path(self.config.app.preview_cache_dir)
        payload["platform_summary"] = self._platform_summary(dict(payload.get("platform_context", {})))
        return payload

    def list_model_packs(self) -> dict[str, Any]:
        return {"packs": self.model_pack_installer.list_packs()}

    def list_encode_profiles(self) -> dict[str, Any]:
        return {
            "default_profile_id": self.config.encode.default_profile_id,
            "profiles": [
                {
                    "id": profile.id,
                    "label": profile.label,
                    "description": profile.description,
                    "container": profile.container,
                    "video_codec": profile.video_codec,
                    "video_preset": profile.video_preset,
                    "video_crf": profile.video_crf,
                    "video_pixel_format": profile.video_pixel_format,
                    "audio_codec": profile.audio_codec,
                    "audio_bitrate_kbps": profile.audio_bitrate_kbps,
                    "subtitle_codec": profile.subtitle_codec,
                    "preserve_chapters": profile.preserve_chapters,
                    "facts": self.delivery_guidance_builder.describe_profile(profile.id)["facts"],
                }
                for profile in self.config.encode.profiles
            ],
        }

    def runtime_locations(self) -> dict[str, Any]:
        locations = [
            self._location_payload("output_root", self.config.app.default_output_root),
            self._location_payload("preview_cache_dir", self.config.app.preview_cache_dir),
            self._location_payload("support_bundle_dir", self.config.support.bundle_output_dir),
            self._location_payload("app_state_dir", Path(self.config.app.state_db_path).parent),
        ]
        primary_model_dir = next(iter(self.config.paths.model_dirs), None)
        if primary_model_dir:
            locations.append(self._location_payload("primary_model_dir", primary_model_dir))
        return {"locations": locations}

    def platform_validation_matrix(
        self,
        repo_root: str | Path | None = None,
        *,
        include_execution_smoke: bool = False,
    ) -> dict[str, Any]:
        return build_platform_validation_payload(
            repo_root,
            include_execution_smoke=include_execution_smoke,
        )

    def compare_media_files(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        encode_profile_id: str | None = None,
        preserve_chapters: bool = True,
    ) -> dict[str, Any]:
        normalized_encode_profile_id = self._normalize_encode_profile_id(encode_profile_id)
        input_probe = self.ffprobe.probe(input_path)
        output_probe = self.ffprobe.probe(output_path)
        input_metrics = summarize_media_probe(input_probe)
        output_metrics = summarize_media_probe(output_probe)
        comparison = compare_media_metrics(
            input_metrics,
            output_metrics,
            encode_profile_id=normalized_encode_profile_id,
            preserve_chapters=preserve_chapters,
            config=self.config.conversion_guidance,
        )
        return {
            "input_path": str(Path(input_path).resolve()),
            "output_path": str(Path(output_path).resolve()),
            "encode_profile_id": normalized_encode_profile_id,
            "preserve_chapters": preserve_chapters,
            "input_metrics": input_metrics,
            "output_metrics": output_metrics,
            "comparison": comparison,
        }

    def runtime_action_plan(
        self,
        doctor_report: dict[str, Any] | None = None,
        model_pack_payload: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        report = self.doctor_report() if doctor_report is None else doctor_report
        packs = self.list_model_packs() if model_pack_payload is None else model_pack_payload
        return [
            action.to_dict()
            for action in self.runtime_guidance.build(
                doctor_report=report,
                model_pack_payload=packs,
            )
        ]

    def install_model_pack(self, pack_id: str, force: bool = False) -> dict[str, Any]:
        if pack_id == "recommended":
            results = self.model_pack_installer.install_recommended()
        else:
            results = [self.model_pack_installer.install(pack_id, force=force)]
        return {"results": results}

    def inspect_target(self, target: str | Path) -> list[dict[str, Any]]:
        reports = self.inspector.inspect_target(target)
        return [report.to_dict() for report in reports]

    def recommend_target(
        self,
        target: str | Path,
        custom_model_paths: list[str] | None = None,
        hook_references: list[str] | None = None,
        output_policy_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reports = self.inspector.inspect_target(target)
        profile, overrides, warnings = self.profile_resolver.choose_manifest_profile(reports)
        backend = self.backend_manager.choose_backend()
        manifest = self.pipeline_builder.build_manifest(
            reports=reports,
            profile=profile,
            per_file_overrides=overrides,
            warnings=warnings + ([] if not backend.degraded else [f"Preferred backend is degraded: {backend.backend_id}"]),
            custom_model_paths=custom_model_paths or [],
            hook_references=hook_references or [],
            output_policy_overrides=output_policy_overrides or {},
        )
        return {
            "inspection_reports": [report.to_dict() for report in reports],
            "backend_selection": backend.to_dict(),
            "project_manifest": manifest.to_dict(),
            "delivery_guidance": self.build_delivery_guidance(
                reports=[report.to_dict() for report in reports],
                output_policy=manifest.output_policy,
            ),
            "batch_summary": self._build_batch_summary(reports, manifest, backend.to_dict()),
        }

    def build_delivery_guidance(
        self,
        *,
        reports: list[dict[str, Any]],
        output_policy: dict[str, Any],
    ) -> dict[str, Any]:
        inspection_reports = [InspectionReport.from_dict(report) for report in reports]
        return self.delivery_guidance_builder.build(inspection_reports, output_policy)

    def prepare_preview(
        self,
        source_path: str,
        stage_id: str,
        comparison_mode: ComparisonMode,
        stage_settings: dict[str, object] | None = None,
        sample_start_seconds: float = 0.0,
        sample_duration_seconds: float | None = None,
        fidelity_mode: FidelityMode = FidelityMode.APPROXIMATE,
        backend_id: str = "planning_only",
        model_ids: list[str] | None = None,
    ) -> PreviewResult:
        request = self.preview_engine.create_request(
            source_path=source_path,
            stage_id=stage_id,
            comparison_mode=comparison_mode,
            stage_settings=stage_settings,
            sample_start_seconds=sample_start_seconds,
            sample_duration_seconds=sample_duration_seconds,
            fidelity_mode_request=fidelity_mode,
            backend_id=backend_id,
            model_ids=model_ids,
        )
        return self.preview_engine.prepare_preview(request)

    def run_project(
        self,
        manifest: ProjectManifest,
        output_dir: str | Path | None = None,
        execute: bool = False,
        execute_degraded: bool = False,
    ) -> tuple[dict[str, Any], list[JobRecord]]:
        backend_selection = self.backend_manager.choose_backend()
        encode_plan = self.encode_mux_planner.build_plan(manifest)
        resolved_output_dir = output_dir or self.config.app.default_output_root
        if execute:
            jobs = self.queue_runner.execute_manifest(
                manifest,
                resolved_output_dir,
                backend_selection=backend_selection,
                encode_plan=encode_plan,
            )
        elif execute_degraded:
            jobs = self.queue_runner.execute_degraded_manifest(
                manifest,
                resolved_output_dir,
                backend_selection=backend_selection,
                encode_plan=encode_plan,
            )
        else:
            jobs = self.queue_runner.enqueue_manifest(
                manifest,
                resolved_output_dir,
                backend_selection=backend_selection,
                encode_plan=encode_plan,
            )
        return backend_selection.to_dict(), jobs

    def resume_job(
        self,
        job_id: str,
        execute: bool = False,
        execute_degraded: bool = False,
    ) -> JobRecord | None:
        if execute or execute_degraded:
            return self.queue_runner.execute_saved_job(
                job_id=job_id,
                backend_selection=self.backend_manager.choose_backend(),
                force_degraded=execute_degraded,
            )
        return self.queue_runner.resume(job_id)

    def load_session_state(self, key: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = self.store.get_app_state(key)
        if payload is None:
            return dict(default or {})
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return dict(default or {})

    def save_session_state(self, key: str, payload: dict[str, Any]) -> None:
        self.store.set_app_state(key, json.dumps(payload, sort_keys=True))

    def list_recent_targets(self) -> list[dict[str, Any]]:
        payload = self.load_session_state(self._recent_targets_state_key(), default={"targets": []})
        rows = list(payload.get("targets", []))
        recent_targets: list[dict[str, Any]] = []
        for row in rows[: self.config.app.max_recent_targets]:
            target_path = str(row.get("path", "")).strip()
            if not target_path:
                continue
            resolved = Path(target_path).resolve()
            recent_targets.append(
                {
                    "path": str(resolved),
                    "label": resolved.name or str(resolved),
                    "kind": "folder" if resolved.is_dir() else "file",
                    "exists": resolved.exists(),
                    "recommended_profile_id": str(row.get("recommended_profile_id", "")),
                    "source_count": row.get("source_count"),
                    "manual_review_count": row.get("manual_review_count"),
                }
            )
        return recent_targets

    def remember_recent_target(
        self,
        target: str | Path,
        *,
        recommended_profile_id: str = "",
        source_count: int | None = None,
        manual_review_count: int | None = None,
    ) -> list[dict[str, Any]]:
        resolved = Path(target).resolve()
        if not resolved.exists():
            return self.list_recent_targets()
        existing = self.list_recent_targets()
        deduped = [
            item
            for item in existing
            if Path(str(item.get("path", ""))).resolve() != resolved
        ]
        recent_targets = [
            {
                "path": str(resolved),
                "label": resolved.name or str(resolved),
                "kind": "folder" if resolved.is_dir() else "file",
                "exists": True,
                "recommended_profile_id": recommended_profile_id,
                "source_count": source_count,
                "manual_review_count": manual_review_count,
            },
            *deduped,
        ][: self.config.app.max_recent_targets]
        self.save_session_state(self._recent_targets_state_key(), {"targets": recent_targets})
        return recent_targets

    def prune_recent_targets(self) -> list[dict[str, Any]]:
        recent_targets = [item for item in self.list_recent_targets() if item.get("exists")]
        self.save_session_state(self._recent_targets_state_key(), {"targets": recent_targets})
        return recent_targets

    def dashboard_snapshot(self) -> dict[str, Any]:
        jobs = [job.to_dict() for job in self.store.list_jobs()]
        counts = {
            "queued": 0,
            "running": 0,
            "failed": 0,
            "completed": 0,
            "paused": 0,
            "planned": 0,
        }
        for job in jobs:
            counts[job["status"]] = counts.get(job["status"], 0) + 1
        overall_progress = (
            sum(max(0.0, min(1.0, float(job.get("progress", 0.0)))) for job in jobs) / len(jobs)
            if jobs
            else 0.0
        )
        active_job_count = counts.get("queued", 0) + counts.get("running", 0) + counts.get("paused", 0) + counts.get("planned", 0)
        focus_job = self._dashboard_focus_job(jobs)
        latest_completed_job = next((job for job in jobs if job.get("status") == "completed"), None)
        return {
            "counts": counts,
            "overview": {
                "total_jobs": len(jobs),
                "overall_progress": round(overall_progress, 4),
                "active_job_count": active_job_count,
                "issue_job_count": counts.get("failed", 0),
                "completed_job_count": counts.get("completed", 0),
                "focus_job": focus_job,
                "latest_completed_job": self._dashboard_job_brief(latest_completed_job),
            },
            "jobs": jobs,
        }

    def run_manifest_for_job(self, job_id: str) -> dict[str, Any] | None:
        record = self.store.get_job(job_id)
        if record is None:
            return None
        payload_path = Path(record.payload_path)
        if not payload_path.exists():
            return None
        return read_artifact(payload_path)

    def job_output_location(self, job_id: str) -> dict[str, Any] | None:
        record = self.store.get_job(job_id)
        if record is None:
            return None
        run_manifest = self.run_manifest_for_job(job_id)
        output_files = list((run_manifest or {}).get("output_files", []))
        output_dir = (
            Path(output_files[0]).resolve().parent
            if output_files
            else Path(record.payload_path).resolve().parent
        )
        return {
            "job_id": job_id,
            "path": str(output_dir),
            "exists": output_dir.exists(),
        }

    def export_support_bundle(
        self,
        *,
        output_path: str | Path | None = None,
        include_full_paths: bool | None = None,
        session_state_key: str | None = None,
        selected_job_id: str | None = None,
    ) -> dict[str, Any]:
        session_state = self.load_session_state(session_state_key) if session_state_key else None
        selected_run_manifest = self.run_manifest_for_job(selected_job_id) if selected_job_id else None
        result = self.support_bundle_exporter.export(
            doctor_report=self.doctor_report(),
            model_packs=self.list_model_packs(),
            setup_actions=self.runtime_action_plan(),
            platform_validation_matrix=self.platform_validation_matrix(),
            dashboard_snapshot=self.dashboard_snapshot(),
            session_state=session_state,
            selected_job_id=selected_job_id,
            selected_run_manifest=selected_run_manifest,
            output_path=output_path,
            include_full_paths=include_full_paths,
        )
        return result.to_dict()

    def _build_batch_summary(
        self,
        reports,
        manifest: ProjectManifest,
        backend_selection: dict[str, Any],
    ) -> dict[str, Any]:
        profile_counts = Counter(report.recommended_profile_id for report in reports)
        source_class_counts = Counter(report.detected_source_class for report in reports)
        dominant_profile = profile_counts.most_common(1)[0][0] if profile_counts else manifest.selected_profile_id
        source_rows = []
        flagged_sources = []
        outlier_sources = []
        for report in reports:
            video_stream = next((stream for stream in report.streams if stream.codec_type == "video"), None)
            geometry = "unknown"
            if video_stream is not None:
                geometry = f"{video_stream.width or '?'}x{video_stream.height or '?'}"
            profile_outlier = report.recommended_profile_id != dominant_profile
            flag_labels = []
            if report.manual_review_required:
                flag_labels.append("manual review")
            if profile_outlier:
                flag_labels.append("profile outlier")
            if report.warnings:
                warning_label = "warning" if len(report.warnings) == 1 else "warnings"
                flag_labels.append(f"{len(report.warnings)} {warning_label}")
            row = {
                "source_path": report.source_path,
                "source_name": Path(report.source_path).name,
                "detected_source_class": report.detected_source_class,
                "recommended_profile_id": report.recommended_profile_id,
                "confidence": round(report.confidence, 2),
                "manual_review_required": report.manual_review_required,
                "warning_count": len(report.warnings),
                "flag_summary": ", ".join(flag_labels) if flag_labels else "aligned",
                "profile_outlier": profile_outlier,
                "duration_seconds": report.duration_seconds,
                "geometry": geometry,
                "artifact_hints": list(report.artifact_hints),
                "warnings": list(report.warnings),
            }
            source_rows.append(row)
            if report.manual_review_required or report.warnings:
                flagged_sources.append(
                    {
                        "source_path": report.source_path,
                        "warnings": list(report.warnings),
                        "confidence": report.confidence,
                    }
                )
            if profile_outlier or report.manual_review_required:
                outlier_sources.append(report.source_path)

        source_rows.sort(
            key=lambda item: (
                not item["manual_review_required"],
                not item["profile_outlier"],
                item["warning_count"] == 0,
                item["confidence"],
                item["source_name"].lower(),
            )
        )
        return {
            "source_count": len(reports),
            "dominant_profile": dominant_profile,
            "all_match_profile": len(profile_counts) <= 1,
            "manual_review_count": sum(1 for report in reports if report.manual_review_required),
            "flagged_sources": flagged_sources,
            "outlier_sources": outlier_sources,
            "source_rows": source_rows,
            "source_class_counts": dict(source_class_counts),
            "profile_counts": dict(profile_counts),
            "backend_plan": backend_selection.get("backend_id", "unknown"),
        }

    def _platform_summary(self, platform_context: dict[str, Any]) -> str:
        if not platform_context:
            return ""
        environment_label = str(platform_context.get("environment_label", "")).strip()
        release = str(platform_context.get("release", "")).strip()
        machine = str(platform_context.get("machine", "")).strip()
        python_status = self.backend_manager.environment.get("python")
        python_version = python_status.detail if python_status is not None else ""
        parts = [part for part in (environment_label, release, machine) if part]
        summary = " · ".join(parts)
        if python_version:
            summary = f"{summary} · Python {python_version}" if summary else f"Python {python_version}"
        return summary

    def _location_payload(self, location_id: str, raw_path: str | Path) -> dict[str, Any]:
        resolved = resolve_runtime_path(raw_path)
        return {
            "location_id": location_id,
            "path": str(resolved),
            "exists": resolved.exists(),
            "writable": resolved.is_dir() or not resolved.exists(),
        }

    def _normalize_encode_profile_id(self, encode_profile_id: str | None) -> str | None:
        if encode_profile_id is None:
            return None
        normalized = str(encode_profile_id).strip()
        if not normalized:
            return None
        self.config.encode_profile_by_id(normalized)
        return normalized

    def _recent_targets_state_key(self) -> str:
        return f"{self.RECENT_TARGETS_STATE_KEY}:{self.config.app.project_history_scope}"

    def _dashboard_focus_job(self, jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
        for status in ["running", "failed", "paused", "queued", "planned", "completed"]:
            match = next((job for job in jobs if job.get("status") == status), None)
            if match is not None:
                return self._dashboard_job_brief(match)
        return None

    def _dashboard_job_brief(self, job: dict[str, Any] | None) -> dict[str, Any] | None:
        if not job:
            return None
        source_path = str(job.get("source_path", ""))
        return {
            "job_id": str(job.get("job_id", "")),
            "source_name": Path(source_path).name if source_path else "Unknown source",
            "status": str(job.get("status", "")),
            "progress": float(job.get("progress", 0.0) or 0.0),
            "updated_at": str(job.get("updated_at", "")),
            "error_message": str(job.get("error_message") or ""),
        }
