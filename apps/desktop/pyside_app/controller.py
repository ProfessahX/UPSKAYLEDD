from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices

from upskayledd.app_service import AppService
from upskayledd.models import ComparisonMode, FidelityMode, ProjectManifest

from .async_task import AsyncTask
from .models import CurrentProject, DesktopSessionState
from .ui_config import DesktopUiConfig, load_ui_config


class DesktopController(QObject):
    sessionChanged = Signal(object)
    projectChanged = Signal(object)
    previewChanged = Signal(object)
    dashboardChanged = Signal(object)
    runManifestChanged = Signal(object)
    doctorReportChanged = Signal(object)
    modelPacksChanged = Signal(object)
    supportBundleReady = Signal(object)
    runtimeStatusChanged = Signal(object)
    recentTargetsChanged = Signal(object)
    busyChanged = Signal(bool)
    messageChanged = Signal(str)
    errorRaised = Signal(str)
    pageRequested = Signal(str)

    def __init__(
        self,
        *,
        service: AppService | None = None,
        ui_config: DesktopUiConfig | None = None,
    ) -> None:
        super().__init__()
        self.service = service or AppService()
        self.ui_config = ui_config or load_ui_config()
        self.thread_pool = QThreadPool.globalInstance()

        self.session = self._load_session()
        self.current_project: CurrentProject | None = None
        self.preview_payload: dict[str, Any] | None = None
        self.dashboard_payload = self.service.dashboard_snapshot()
        self.run_manifest_payload: dict[str, Any] | None = None
        self.doctor_payload: dict[str, Any] | None = None
        self.model_packs_payload: dict[str, Any] | None = None
        self.support_bundle_payload: dict[str, Any] | None = None
        self.recent_targets_payload = self.service.prune_recent_targets()

    def initialize(self) -> None:
        self.sessionChanged.emit(self.session)
        self.dashboardChanged.emit(self.dashboard_payload)
        self.runtimeStatusChanged.emit(self._runtime_status_payload())
        self.recentTargetsChanged.emit(self.recent_targets_payload)
        self._refresh_runtime_status()
        self.pageRequested.emit(self.session.current_page)

    def set_page(self, page: str) -> None:
        self.session.current_page = page
        self._persist_session()
        self.sessionChanged.emit(self.session)
        self.pageRequested.emit(page)

    def set_simple_mode(self, enabled: bool) -> None:
        self.session.simple_mode = enabled
        self._persist_session()
        self.sessionChanged.emit(self.session)

    def set_queue_collapsed(self, collapsed: bool) -> None:
        self.session.queue_collapsed = collapsed
        self._persist_session()
        self.sessionChanged.emit(self.session)

    def select_stage(self, stage_id: str) -> None:
        if not stage_id:
            return
        self.session.selected_stage = stage_id
        self._persist_session()
        self.sessionChanged.emit(self.session)
        self._emit_project()

    def select_source(self, source_path: str) -> None:
        if not source_path or source_path == self.session.selected_source:
            return
        self.session.selected_source = source_path
        self.preview_payload = None
        self._persist_session()
        self.sessionChanged.emit(self.session)
        self.previewChanged.emit(None)

    def set_comparison_mode(self, comparison_mode: str) -> None:
        self.session.comparison_mode = comparison_mode
        self._persist_session()
        self.sessionChanged.emit(self.session)

    def set_fidelity_mode(self, fidelity_mode: str) -> None:
        self.session.fidelity_mode = fidelity_mode
        self._persist_session()
        self.sessionChanged.emit(self.session)

    def set_preview_window(self, *, start_seconds: float | None = None, duration_seconds: float | None = None) -> None:
        if start_seconds is not None:
            self.session.preview_start_seconds = start_seconds
        if duration_seconds is not None:
            self.session.preview_duration_seconds = duration_seconds
        self._persist_session()
        self.sessionChanged.emit(self.session)

    def select_job(self, job_id: str) -> None:
        self.session.selected_job_id = job_id
        self._persist_session()
        self.sessionChanged.emit(self.session)
        self.run_manifest_payload = self.service.run_manifest_for_job(job_id)
        self.runManifestChanged.emit(self.run_manifest_payload)

    def set_stage_expanded(self, stage_id: str, expanded: bool) -> None:
        self.session.stage_expansion_memory[stage_id] = expanded
        self._persist_session()
        self.sessionChanged.emit(self.session)

    def update_stage_enabled(self, stage_id: str, enabled: bool) -> None:
        stage = self._stage_by_id(stage_id)
        if stage is None:
            return
        stage.enabled = enabled
        stage.reason = "customized" if enabled else "skipped_by_user"
        self._emit_project()

    def update_stage_setting(self, stage_id: str, key: str, value: Any) -> None:
        stage = self._stage_by_id(stage_id)
        if stage is None:
            return
        stage.settings[key] = value
        stage.reason = "customized"
        if stage_id == "upscale" and key in {"target_width", "target_height"}:
            policy_key = "width" if key == "target_width" else "height"
            self.current_project.manifest.output_policy[policy_key] = value
        self._emit_project()

    def update_output_policy(self, key: str, value: Any) -> None:
        if self.current_project is None:
            return
        if key == "encode_profile_id":
            self.current_project.manifest.output_policy = self.service.encode_mux_planner.apply_output_overrides(
                self.current_project.manifest.output_policy,
                {"encode_profile_id": value},
            )
        else:
            self.current_project.manifest.output_policy[key] = value
        if self.session.selected_stage == "encode":
            stage = self._stage_by_id("encode")
            if stage is not None:
                stage.reason = "customized"
        if self.session.selected_stage == "upscale":
            stage = self._stage_by_id("upscale")
            if stage is not None:
                stage.reason = "customized"
                if key in {"width", "height"}:
                    stage_key = "target_width" if key == "width" else "target_height"
                    stage.settings[stage_key] = value
        self._emit_project()

    def ingest_target(self, target: str) -> None:
        target = target.strip()
        if not target:
            self.errorRaised.emit("Choose a file or folder before analysis.")
            return
        self.session.last_target = target
        self._persist_session()
        self.sessionChanged.emit(self.session)
        self._run_task(
            busy_message="Inspecting source and building a recommendation...",
            fn=lambda: self.service.recommend_target(target),
            on_success=self._apply_ingest_payload,
        )

    def run_doctor(self) -> None:
        self._run_task(
            busy_message="Checking the local runtime environment...",
            fn=self.service.doctor_report,
            on_success=self._handle_doctor_report,
        )

    def refresh_model_packs(self) -> None:
        self._run_task(
            busy_message="Refreshing curated model pack status...",
            fn=self.service.list_model_packs,
            on_success=self._handle_model_packs,
        )

    def install_recommended_models(self) -> None:
        self._run_task(
            busy_message="Installing recommended curated model packs...",
            fn=lambda: self.service.install_model_pack("recommended"),
            on_success=self._handle_model_install,
        )

    def export_support_bundle(self) -> None:
        selected_job_id = self.session.selected_job_id.strip() or None
        self._run_task(
            busy_message="Preparing a support bundle...",
            fn=lambda: self.service.export_support_bundle(
                session_state_key=self.ui_config.behavior.session_state_key,
                selected_job_id=selected_job_id,
            ),
            on_success=self._handle_support_bundle_ready,
        )

    def open_recent_target(self, target: str) -> None:
        self.ingest_target(target)

    def prune_recent_targets(self) -> None:
        self.recent_targets_payload = self.service.prune_recent_targets()
        self.recentTargetsChanged.emit(self.recent_targets_payload)
        self.messageChanged.emit("Recent targets cleaned up.")

    def open_runtime_location(self, location_id: str) -> None:
        payload = self.service.runtime_locations()
        match = next(
            (item for item in payload.get("locations", []) if item.get("location_id") == location_id),
            None,
        )
        if match is None:
            self.errorRaised.emit("That runtime path is not available in the current configuration.")
            return
        target_path = str(match.get("path", "")).strip()
        if not target_path:
            self.errorRaised.emit("That runtime path is empty.")
            return
        resolved_path = Path(target_path)
        resolved_path.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved_path))):
            self.errorRaised.emit(f"Could not open {resolved_path}.")
            return
        label = self.ui_config.copy.runtime.location_labels.get(location_id, location_id.replace("_", " ").title())
        self.messageChanged.emit(f"Opened {label.lower()} at {resolved_path}.")

    def open_selected_job_output(self) -> None:
        job_id = self.session.selected_job_id.strip()
        if not job_id:
            self.errorRaised.emit("Select a job before opening its output folder.")
            return
        payload = self.service.job_output_location(job_id)
        if payload is None:
            self.errorRaised.emit("That job no longer has a readable output location.")
            return
        resolved_path = Path(str(payload.get("path", ""))).resolve()
        resolved_path.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved_path))):
            self.errorRaised.emit(f"Could not open {resolved_path}.")
            return
        self.messageChanged.emit(f"Opened output folder at {resolved_path}.")

    def request_preview(
        self,
        *,
        comparison_mode: str,
        fidelity_mode: str,
        sample_start_seconds: float,
        sample_duration_seconds: float | None,
    ) -> None:
        if self.current_project is None:
            self.errorRaised.emit("Analyze a source before generating a preview.")
            return
        source_path = self.session.selected_source or self.current_project.source_files[0]
        stage = self._stage_by_id(self.session.selected_stage)
        if stage is None:
            self.errorRaised.emit("No stage is selected for preview.")
            return
        stage_settings = dict(stage.settings)
        if stage.stage_id == "upscale":
            stage_settings.setdefault(
                "target_width",
                int(self.current_project.manifest.output_policy.get("width", 0) or 0),
            )
            stage_settings.setdefault(
                "target_height",
                int(self.current_project.manifest.output_policy.get("height", 0) or 0),
            )
        backend_id = self.current_project.backend_selection.get("backend_id", "planning_only")
        model_ids = list(self.current_project.manifest.model_preferences)
        self._run_task(
            busy_message=f"Rendering {stage.stage_id.replace('_', ' ')} preview...",
            fn=lambda: self.service.prepare_preview(
                source_path=source_path,
                stage_id=stage.stage_id,
                comparison_mode=ComparisonMode(comparison_mode),
                stage_settings=stage_settings,
                sample_start_seconds=sample_start_seconds,
                sample_duration_seconds=sample_duration_seconds,
                fidelity_mode=FidelityMode(fidelity_mode),
                backend_id=backend_id,
                model_ids=model_ids,
            ),
            on_success=self._handle_preview_ready,
        )

    def queue_current_project(self) -> None:
        self._dispatch_run(execute=False, execute_degraded=False)

    def run_current_project(self, *, execute_degraded: bool = False) -> None:
        self._dispatch_run(execute=not execute_degraded, execute_degraded=execute_degraded)

    def resume_selected_job(self, *, execute: bool = False, execute_degraded: bool = False) -> None:
        job_id = self.session.selected_job_id.strip()
        if not job_id:
            self.errorRaised.emit("Select a job in the dashboard before trying to resume it.")
            return
        busy_message = "Updating selected job state..."
        if execute_degraded:
            busy_message = "Retrying selected job on the degraded path..."
        elif execute:
            busy_message = "Retrying selected job..."
        self._run_task(
            busy_message=busy_message,
            fn=lambda: self.service.resume_job(
                job_id=job_id,
                execute=execute,
                execute_degraded=execute_degraded,
            ),
            on_success=self._handle_resume_complete,
        )

    def refresh_dashboard(self) -> None:
        self.dashboard_payload = self.service.dashboard_snapshot()
        self.dashboardChanged.emit(self.dashboard_payload)
        if self.session.selected_job_id:
            self.run_manifest_payload = self.service.run_manifest_for_job(self.session.selected_job_id)
            self.runManifestChanged.emit(self.run_manifest_payload)

    def open_workspace(self) -> None:
        if self.current_project is None:
            self.errorRaised.emit("Analyze a source before opening the workspace.")
            return
        self.set_page("workspace")

    def open_workspace_for_source(self, source_path: str) -> None:
        if self.current_project is None:
            self.errorRaised.emit("Analyze a source before opening the workspace.")
            return
        if source_path and source_path in self.current_project.source_files:
            self.select_source(source_path)
        self.open_workspace()

    def open_dashboard(self) -> None:
        self.refresh_dashboard()
        self.set_page("dashboard")

    def _dispatch_run(self, *, execute: bool, execute_degraded: bool) -> None:
        if self.current_project is None:
            self.errorRaised.emit("Analyze a source before queueing or running it.")
            return
        manifest_payload = self.current_project.manifest.to_dict()
        busy_message = "Queueing project jobs..." if not (execute or execute_degraded) else "Running project jobs..."
        self._run_task(
            busy_message=busy_message,
            fn=lambda: self.service.run_project(
                ProjectManifest.from_dict(manifest_payload),
                execute=execute,
                execute_degraded=execute_degraded,
            ),
            on_success=self._handle_run_complete,
        )

    def _handle_model_install(self, payload: dict[str, Any]) -> None:
        self.messageChanged.emit("Recommended model packs installed.")
        self.doctor_payload = self.service.doctor_report()
        self.model_packs_payload = self.service.list_model_packs()
        self.doctorReportChanged.emit(self.doctor_payload)
        self.modelPacksChanged.emit(payload)
        self.runtimeStatusChanged.emit(self._runtime_status_payload())

    def _handle_doctor_report(self, payload: dict[str, Any]) -> None:
        self.doctor_payload = payload
        self.doctorReportChanged.emit(payload)
        self.runtimeStatusChanged.emit(self._runtime_status_payload())

    def _handle_model_packs(self, payload: dict[str, Any]) -> None:
        self.model_packs_payload = payload
        self.modelPacksChanged.emit(payload)
        self.runtimeStatusChanged.emit(self._runtime_status_payload())

    def _handle_support_bundle_ready(self, payload: dict[str, Any]) -> None:
        self.support_bundle_payload = payload
        self.supportBundleReady.emit(payload)
        self.messageChanged.emit(f"Support bundle exported to {payload.get('bundle_path', 'the configured support directory')}.")

    def _refresh_runtime_status(self) -> None:
        self._run_task(
            busy_message="Refreshing runtime readiness...",
            fn=lambda: {
                "doctor": self.service.doctor_report(),
                "model_packs": self.service.list_model_packs(),
            },
            on_success=self._handle_runtime_status_refresh,
            announce=False,
        )

    def _handle_runtime_status_refresh(self, payload: dict[str, Any]) -> None:
        self.doctor_payload = dict(payload.get("doctor", {}))
        self.model_packs_payload = dict(payload.get("model_packs", {}))
        self.runtimeStatusChanged.emit(self._runtime_status_payload())

    def _runtime_status_payload(self) -> dict[str, Any]:
        checks = list((self.doctor_payload or {}).get("checks", []))
        healthy = sum(1 for item in checks if item.get("status") == "healthy")
        degraded = sum(1 for item in checks if item.get("status") == "degraded")
        missing = sum(1 for item in checks if item.get("status") == "missing")
        packs = list((self.model_packs_payload or {}).get("packs", []))
        installed_packs = sum(1 for pack in packs if pack.get("installed"))
        recommended_missing = sum(
            1
            for pack in packs
            if pack.get("recommended") and not pack.get("installed")
        )
        focus_checks = [
            {
                "name": item.get("name", "unknown"),
                "status": item.get("status", "unknown"),
                "detail": item.get("detail", ""),
            }
            for item in checks
            if item.get("status") in {"missing", "degraded"}
        ]
        focus_checks.sort(key=lambda item: (item["status"] != "missing", item["name"]))
        pack_rows = [
            {
                "label": pack.get("label", pack.get("id", "unknown")),
                "status": "installed" if pack.get("installed") else "missing",
                "recommended": bool(pack.get("recommended")),
                "size_hint_mb": pack.get("size_hint_mb"),
            }
            for pack in packs
        ]
        copy = self.ui_config.copy.runtime
        if not checks and not packs:
            return {
                "headline": copy.checking.headline,
                "doctor_summary": copy.checking.doctor_summary,
                "model_summary": copy.checking.model_summary,
                "action": copy.checking.action,
                "status": "checking",
                "focus_checks": [],
                "pack_rows": [],
                "guided_actions": [],
                "location_rows": [],
            }
        status = "ready"
        if missing or recommended_missing:
            status = "attention"
        elif degraded:
            status = "watch"
        status_copy = {
            "ready": copy.ready,
            "watch": copy.watch,
            "attention": copy.attention,
        }[status]
        guided_actions = self.service.runtime_action_plan(
            doctor_report=self.doctor_payload or {"checks": []},
            model_pack_payload=self.model_packs_payload or {"packs": []},
        )
        return {
            "headline": status_copy.headline,
            "doctor_summary": f"{healthy} healthy · {degraded} degraded · {missing} missing runtime checks",
            "model_summary": (
                f"{installed_packs}/{len(packs)} curated packs installed"
                + (f" · {recommended_missing} recommended pack missing" if packs else "")
            ),
            "action": status_copy.action,
            "status": status,
            "focus_checks": focus_checks,
            "pack_rows": pack_rows,
            "guided_actions": guided_actions,
            "location_rows": [
                {
                    "location_id": item.get("location_id", ""),
                    "label": copy.location_labels.get(
                        str(item.get("location_id", "")),
                        str(item.get("location_id", "")).replace("_", " ").title(),
                    ),
                    "path": item.get("path", ""),
                    "exists": bool(item.get("exists")),
                }
                for item in self.service.runtime_locations().get("locations", [])
            ],
        }

    def _apply_ingest_payload(self, payload: dict[str, Any]) -> None:
        self.current_project = CurrentProject.from_payload(payload)
        self.recent_targets_payload = self.service.remember_recent_target(
            self.session.last_target,
            recommended_profile_id=self.current_project.manifest.selected_profile_id,
            source_count=len(self.current_project.source_files),
            manual_review_count=int(self.current_project.batch_summary.get("manual_review_count", 0)),
        )
        if not self.session.selected_source or self.session.selected_source not in self.current_project.source_files:
            self.session.selected_source = self.current_project.source_files[0] if self.current_project.source_files else ""
        if self.session.selected_stage not in self.current_project.stage_ids:
            self.session.selected_stage = self.current_project.stage_ids[0] if self.current_project.stage_ids else self.ui_config.preview.default_stage
        self.preview_payload = None
        self.run_manifest_payload = None
        self._persist_session()
        self.sessionChanged.emit(self.session)
        self.recentTargetsChanged.emit(self.recent_targets_payload)
        self._emit_project()
        self.previewChanged.emit(None)
        self.runManifestChanged.emit(None)
        self.set_page("summary")
        self.messageChanged.emit("Analysis complete. Review the recommendation, then move into the workspace.")

    def _handle_preview_ready(self, result) -> None:
        payload = result.to_dict()
        self.preview_payload = payload
        self.previewChanged.emit(payload)
        fidelity = payload.get("fidelity_mode", "unknown")
        self.messageChanged.emit(f"Preview ready ({fidelity}).")

    def _handle_run_complete(self, payload: tuple[dict[str, Any], list[Any]]) -> None:
        backend_selection, jobs = payload
        if jobs:
            self.session.selected_job_id = jobs[0].job_id
            self._persist_session()
            self.sessionChanged.emit(self.session)
            self.run_manifest_payload = self.service.run_manifest_for_job(jobs[0].job_id)
        self.dashboard_payload = self.service.dashboard_snapshot()
        self.dashboardChanged.emit(self.dashboard_payload)
        if jobs:
            self.runManifestChanged.emit(self.run_manifest_payload)
        self.set_page("dashboard")
        self.messageChanged.emit(
            "Job dispatch complete via "
            f"{backend_selection.get('backend_id', 'unknown backend')}."
        )

    def _handle_resume_complete(self, job_record) -> None:
        if job_record is None:
            self.errorRaised.emit("The selected job could not be found.")
            return
        self.session.selected_job_id = job_record.job_id
        self._persist_session()
        self.sessionChanged.emit(self.session)
        self.refresh_dashboard()
        self.set_page("dashboard")
        self.messageChanged.emit(f"Job {job_record.job_id[:8]} is now {job_record.status.value}.")

    def _emit_project(self) -> None:
        if self.current_project is None:
            self.projectChanged.emit(None)
            return
        payload = {
            "inspection_reports": list(self.current_project.inspection_reports),
            "backend_selection": dict(self.current_project.backend_selection),
            "project_manifest": self.current_project.manifest.to_dict(),
            "batch_summary": dict(self.current_project.batch_summary),
        }
        self.projectChanged.emit(payload)

    def _load_session(self) -> DesktopSessionState:
        defaults = DesktopSessionState(
            current_page=self.ui_config.behavior.default_page,
            simple_mode=self.ui_config.behavior.default_simple_mode,
            queue_collapsed=self.ui_config.behavior.default_queue_collapsed,
            selected_stage=self.ui_config.preview.default_stage,
            comparison_mode=self.ui_config.preview.default_comparison_mode,
            fidelity_mode=self.ui_config.preview.default_fidelity_mode,
            preview_start_seconds=self.ui_config.preview.default_sample_start_seconds,
            preview_duration_seconds=self.ui_config.preview.default_sample_duration_seconds,
            selected_source="",
            selected_job_id="",
            last_target="",
        )
        payload = self.service.load_session_state(
            self.ui_config.behavior.session_state_key,
            default=defaults.to_dict(),
        )
        return DesktopSessionState.from_dict(
            payload,
            default_page=self.ui_config.behavior.default_page,
            default_simple_mode=self.ui_config.behavior.default_simple_mode,
            default_queue_collapsed=self.ui_config.behavior.default_queue_collapsed,
            default_stage=self.ui_config.preview.default_stage,
            default_comparison_mode=self.ui_config.preview.default_comparison_mode,
            default_fidelity_mode=self.ui_config.preview.default_fidelity_mode,
            default_preview_start_seconds=self.ui_config.preview.default_sample_start_seconds,
            default_preview_duration_seconds=self.ui_config.preview.default_sample_duration_seconds,
        )

    def _persist_session(self) -> None:
        self.service.save_session_state(self.ui_config.behavior.session_state_key, self.session.to_dict())

    def _stage_by_id(self, stage_id: str):
        if self.current_project is None:
            return None
        return self.current_project.stage_by_id(stage_id)

    def _run_task(
        self,
        *,
        busy_message: str,
        fn,
        on_success,
        announce: bool = True,
    ) -> None:
        if announce:
            self.busyChanged.emit(True)
            self.messageChanged.emit(busy_message)
        task = AsyncTask(fn)
        task.signals.succeeded.connect(on_success)
        task.signals.failed.connect(self._handle_error)
        if announce:
            task.signals.finished.connect(lambda: self.busyChanged.emit(False))
        self.thread_pool.start(task)

    def _handle_error(self, detail: str) -> None:
        self.errorRaised.emit(detail)
        self.messageChanged.emit(detail)
