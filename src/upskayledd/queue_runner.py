from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

from upskayledd.config import AppConfig
from upskayledd.integrations.ffmpeg import FFmpegAdapter
from upskayledd.integrations.ffprobe import FFprobeAdapter
from upskayledd.integrations.vapoursynth import VapourSynthAdapter
from upskayledd.manifest_writer import read_artifact, write_artifact
from upskayledd.media_metrics import compare_media_metrics, summarize_media_probe
from upskayledd.models import BackendSelection
from upskayledd.models import JobRecord, JobStatus, ProjectManifest, RunManifest, StreamOutcome, utc_now
from upskayledd.project_store import ProjectStore


class QueueRunner:
    def __init__(
        self,
        store: ProjectStore,
        config: AppConfig,
        ffmpeg: FFmpegAdapter | None = None,
        vapoursynth: VapourSynthAdapter | None = None,
        ffprobe: FFprobeAdapter | None = None,
    ) -> None:
        self.store = store
        self.config = config
        self.ffmpeg = ffmpeg or FFmpegAdapter()
        self.vapoursynth = vapoursynth or VapourSynthAdapter(config, ffmpeg=self.ffmpeg)
        self.ffprobe = ffprobe or FFprobeAdapter()

    def enqueue_manifest(
        self,
        manifest: ProjectManifest,
        output_dir: str | Path,
        backend_selection: BackendSelection | None = None,
        encode_plan: dict[str, object] | None = None,
    ) -> list[JobRecord]:
        output_root = Path(output_dir)
        output_root.mkdir(parents=True, exist_ok=True)
        backend_payload = (
            backend_selection.to_dict()
            if backend_selection is not None
            else {"backend_id": "planned", "runtime": "not executed yet"}
        )
        encode_plan = encode_plan or {}
        jobs: list[JobRecord] = []
        container = str(encode_plan.get("container") or manifest.output_policy.get("container", "mkv"))
        reserved_outputs: set[Path] = set()
        for source_path in manifest.source_files:
            run_id = str(uuid4())
            payload_path = output_root / f"{run_id}.run_manifest.json"
            planned_output = self._planned_output_path(
                manifest=manifest,
                output_root=output_root,
                source_path=Path(source_path),
                container=container,
                reserved_outputs=reserved_outputs,
            )
            reserved_outputs.add(planned_output.resolve())
            run_manifest = RunManifest(
                run_id=run_id,
                project_id=manifest.project_id,
                input_files=[source_path],
                final_pipeline=manifest.resolved_pipeline_stages,
                actual_backend=backend_payload,
                models_used=manifest.model_preferences,
                output_files=[str(planned_output.resolve())],
                encode_settings={
                    **encode_plan,
                    "status": "planned_only",
                    "restart_policy": "partial_preview_rerenders; partial_encode_restarts_current_file",
                    "execution_context": {
                        "selected_profile_id": manifest.selected_profile_id,
                        "output_policy": manifest.output_policy,
                        "backend_preferences": manifest.backend_preferences,
                        "batch_settings": manifest.batch_settings,
                        "per_file_overrides": manifest.per_file_overrides,
                        "custom_model_paths": manifest.custom_model_paths,
                        "hook_references": manifest.hook_references,
                        "warnings": manifest.warnings,
                    },
                },
                stream_outcomes=[
                    StreamOutcome(
                        stream_type="audio",
                        source_index=-1,
                        action="preserve_if_possible",
                        reason="foundation_default_policy",
                    ),
                    StreamOutcome(
                        stream_type="subtitle",
                        source_index=-1,
                        action="preserve_if_possible",
                        reason="foundation_default_policy",
                    ),
                    StreamOutcome(
                        stream_type="chapter",
                        source_index=-1,
                        action="preserve_if_possible",
                        reason="foundation_default_policy",
                    ),
                ],
                warnings=[
                    "Queue record created; execution details will be finalized when the job runs.",
                    "Audio, subtitle, and chapter preservation are preferred defaults and will be validated at execution time.",
                ],
                fallbacks=(
                    ["Selected backend is degraded; review before long batch runs."]
                    if backend_selection is not None and backend_selection.degraded
                    else []
                ),
                errors=[],
                created_at=utc_now(),
            )
            write_artifact(payload_path, run_manifest.to_dict())
            record = JobRecord(
                job_id=run_id,
                project_id=manifest.project_id,
                source_path=source_path,
                status=JobStatus.QUEUED,
                progress=0.0,
                payload_path=str(payload_path.resolve()),
            )
            self.store.upsert_job(record)
            jobs.append(record)
        return jobs

    def resume(self, job_id: str) -> JobRecord | None:
        record = self.store.get_job(job_id)
        if record is None:
            return None
        if record.status in {JobStatus.FAILED, JobStatus.PAUSED, JobStatus.PLANNED, JobStatus.QUEUED}:
            record.status = JobStatus.QUEUED
            record.progress = 0.0
            record.error_message = None
            record.updated_at = utc_now()
            self.store.upsert_job(record)
        return record

    def execute_degraded_manifest(
        self,
        manifest: ProjectManifest,
        output_dir: str | Path,
        backend_selection: BackendSelection,
        encode_plan: dict[str, object] | None = None,
    ) -> list[JobRecord]:
        jobs = self.enqueue_manifest(
            manifest,
            output_dir,
            backend_selection=backend_selection,
            encode_plan=encode_plan,
        )
        return self._run_jobs(
            jobs=jobs,
            manifest=manifest,
            backend_selection=backend_selection,
            encode_plan=encode_plan or {},
            force_degraded=True,
        )

    def execute_manifest(
        self,
        manifest: ProjectManifest,
        output_dir: str | Path,
        backend_selection: BackendSelection,
        encode_plan: dict[str, object] | None = None,
    ) -> list[JobRecord]:
        jobs = self.enqueue_manifest(
            manifest,
            output_dir,
            backend_selection=backend_selection,
            encode_plan=encode_plan,
        )
        return self._run_jobs(
            jobs=jobs,
            manifest=manifest,
            backend_selection=backend_selection,
            encode_plan=encode_plan or {},
            force_degraded=False,
        )

    def execute_saved_job(
        self,
        job_id: str,
        backend_selection: BackendSelection,
        force_degraded: bool = False,
    ) -> JobRecord | None:
        record = self.resume(job_id)
        if record is None:
            return None
        run_manifest = RunManifest.from_dict(read_artifact(record.payload_path))
        manifest = self._rebuild_manifest(record, run_manifest)
        return self._run_single_job(
            job=record,
            manifest=manifest,
            backend_selection=backend_selection,
            encode_plan=dict(run_manifest.encode_settings),
            force_degraded=force_degraded,
        )

    def _run_jobs(
        self,
        jobs: list[JobRecord],
        manifest: ProjectManifest,
        backend_selection: BackendSelection,
        encode_plan: dict[str, object],
        force_degraded: bool,
    ) -> list[JobRecord]:
        video_filters = self._build_video_filters(manifest)
        current_results: list[JobRecord] = []

        for job in jobs:
            updated = self._run_single_job(
                job=job,
                manifest=manifest,
                backend_selection=backend_selection,
                encode_plan=encode_plan,
                force_degraded=force_degraded,
                video_filters=video_filters,
            )
            if updated is not None:
                current_results.append(updated)
        return current_results

    def _run_single_job(
        self,
        job: JobRecord,
        manifest: ProjectManifest,
        backend_selection: BackendSelection,
        encode_plan: dict[str, object],
        force_degraded: bool,
        video_filters: list[str] | None = None,
    ) -> JobRecord | None:
        filters = video_filters or self._build_video_filters(manifest)
        self.store.update_job_status(job.job_id, JobStatus.RUNNING, 0.1)
        try:
            run_payload = self._execute_job(
                job=job,
                manifest=manifest,
                backend_selection=backend_selection,
                encode_plan=encode_plan,
                video_filters=filters,
                force_degraded=force_degraded,
            )
            self.store.update_job_status(job.job_id, JobStatus.COMPLETED, 1.0)
            write_artifact(job.payload_path, run_payload.to_dict())
        except Exception as exc:  # noqa: BLE001
            self.store.update_job_status(job.job_id, JobStatus.FAILED, 0.0, str(exc))
        return self.store.get_job(job.job_id)

    def _execute_job(
        self,
        job: JobRecord,
        manifest: ProjectManifest,
        backend_selection: BackendSelection,
        encode_plan: dict[str, object],
        video_filters: list[str],
        force_degraded: bool,
    ) -> RunManifest:
        run_manifest = RunManifest.from_dict(read_artifact(job.payload_path))
        output_path = Path(run_manifest.output_files[0])
        working_output_path = self._working_output_path(output_path)
        self._prepare_execution_context(run_manifest, manifest, output_path, working_output_path)
        self._prepare_restart_state(run_manifest, output_path, working_output_path)

        try:
            if not force_degraded and self.vapoursynth.is_available():
                try:
                    run_manifest.encode_settings["status"] = "running_canonical_execution"
                    write_artifact(job.payload_path, run_manifest.to_dict())
                    execution = self.vapoursynth.execute_job(
                        manifest=manifest,
                        stage_plan=run_manifest.final_pipeline,
                        source_path=job.source_path,
                        output_path=working_output_path,
                        backend_selection=backend_selection,
                        encode_plan=encode_plan,
                    )
                    self._finalize_output(working_output_path, output_path)
                    return self._apply_execution_result(
                        run_manifest=run_manifest,
                        source_path=job.source_path,
                        output_path=output_path,
                        working_output_path=working_output_path,
                        execution=execution,
                        execution_status="completed_canonical_execution",
                        execution_mode="vapoursynth_canonical",
                    )
                except Exception as exc:  # noqa: BLE001
                    run_manifest.warnings.append(
                        f"Canonical execution failed and will fall back to the FFmpeg degraded path: {exc}"
                    )
                    run_manifest.fallbacks.append("canonical_execution_failed_retry_degraded")
                    self._remove_partial_output(working_output_path, run_manifest, "canonical_partial_output_removed_before_retry")

            if not self.ffmpeg.is_available():
                raise RuntimeError("ffmpeg is not available for degraded execution.")
            run_manifest.encode_settings["status"] = "running_degraded_execution"
            write_artifact(job.payload_path, run_manifest.to_dict())
            execution = self.ffmpeg.run_processing_pipeline(
                source_path=job.source_path,
                output_path=working_output_path,
                video_filters=video_filters,
                encode_plan=encode_plan,
            )
            self._finalize_output(working_output_path, output_path)
            result = self._apply_execution_result(
                run_manifest=run_manifest,
                source_path=job.source_path,
                output_path=output_path,
                working_output_path=working_output_path,
                execution=execution,
                execution_status="completed_degraded_execution",
                execution_mode="ffmpeg_degraded",
            )
            result.encode_settings["filter_chain"] = execution["filter_chain"]
            result.warnings.append("Output was produced through the FFmpeg degraded execution path.")
            return result
        except Exception as exc:  # noqa: BLE001
            run_manifest.encode_settings["status"] = "failed_execution"
            run_manifest.encode_settings["last_failure"] = str(exc)
            run_manifest.errors.append(str(exc))
            write_artifact(job.payload_path, run_manifest.to_dict())
            raise

    def _apply_execution_result(
        self,
        run_manifest: RunManifest,
        source_path: str | Path,
        output_path: Path,
        working_output_path: Path,
        execution: dict[str, object],
        execution_status: str,
        execution_mode: str,
    ) -> RunManifest:
        run_manifest.output_files = [str(output_path.resolve())]
        run_manifest.stream_outcomes = [
            StreamOutcome(
                stream_type=item["stream_type"],
                source_index=-1,
                action=item["action"],
                reason=item["reason"],
            )
            for item in execution["stream_outcomes"]
        ]
        run_manifest.fallbacks.extend(list(execution.get("fallbacks", [])))
        run_manifest.warnings.extend(list(execution.get("warnings", [])))
        run_manifest.encode_settings["status"] = execution_status
        run_manifest.encode_settings["execution_mode"] = execution_mode
        run_manifest.encode_settings["final_output_path"] = str(output_path.resolve())
        run_manifest.encode_settings["working_output_path"] = str(working_output_path.resolve())
        if "operations" in execution:
            run_manifest.encode_settings["stage_operations"] = execution["operations"]
        if "script_path" in execution:
            run_manifest.encode_settings["script_path"] = execution["script_path"]
        self._attach_size_summary(run_manifest, source_path=source_path, output_path=output_path)
        self._attach_media_metrics(run_manifest, source_path=source_path, output_path=output_path)
        run_manifest.actual_backend["execution_attempt"] = execution["attempt"]
        return run_manifest

    def _prepare_execution_context(
        self,
        run_manifest: RunManifest,
        manifest: ProjectManifest,
        output_path: Path,
        working_output_path: Path,
    ) -> None:
        run_manifest.encode_settings["attempt_count"] = int(run_manifest.encode_settings.get("attempt_count", 0)) + 1
        run_manifest.encode_settings["final_output_path"] = str(output_path.resolve())
        run_manifest.encode_settings["working_output_path"] = str(working_output_path.resolve())
        run_manifest.encode_settings.setdefault(
            "execution_context",
            {
                "selected_profile_id": manifest.selected_profile_id,
                "output_policy": manifest.output_policy,
                "backend_preferences": manifest.backend_preferences,
                "batch_settings": manifest.batch_settings,
                "per_file_overrides": manifest.per_file_overrides,
                "custom_model_paths": manifest.custom_model_paths,
                "hook_references": manifest.hook_references,
                "warnings": manifest.warnings,
            },
        )

    def _prepare_restart_state(
        self,
        run_manifest: RunManifest,
        output_path: Path,
        working_output_path: Path,
    ) -> None:
        previous_status = str(run_manifest.encode_settings.get("status", "planned_only"))
        if self.config.queue.restart_partial_encode and working_output_path.exists():
            working_output_path.unlink()
            run_manifest.warnings.append("Removed a stale partial output before restarting the current file.")
            run_manifest.fallbacks.append("restart_removed_partial_output")
        if previous_status.startswith("completed_"):
            return
        if output_path.exists():
            output_path.unlink()
            run_manifest.warnings.append("Removed a stale incomplete output before restarting the current file.")
            run_manifest.fallbacks.append("restart_removed_incomplete_output")

    def _finalize_output(self, working_output_path: Path, output_path: Path) -> None:
        if not working_output_path.exists():
            raise RuntimeError("Working output was not created.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        working_output_path.replace(output_path)

    def _remove_partial_output(self, working_output_path: Path, run_manifest: RunManifest, fallback_id: str) -> None:
        if working_output_path.exists():
            working_output_path.unlink()
            run_manifest.warnings.append("Removed a failed partial output before retrying the current file.")
            run_manifest.fallbacks.append(fallback_id)

    def _attach_size_summary(self, run_manifest: RunManifest, *, source_path: str | Path, output_path: Path) -> None:
        source = Path(source_path)
        if not source.exists() or not output_path.exists():
            return
        input_size_bytes = source.stat().st_size
        output_size_bytes = output_path.stat().st_size
        run_manifest.encode_settings["input_size_bytes"] = input_size_bytes
        run_manifest.encode_settings["output_size_bytes"] = output_size_bytes
        if input_size_bytes <= 0:
            return
        size_ratio = round(output_size_bytes / input_size_bytes, 4)
        run_manifest.encode_settings["size_ratio"] = size_ratio
        if size_ratio > 1.05:
            run_manifest.warnings.append(
                "Output file is larger than the source file; review delivery settings if file size matters for this batch."
            )

    def _attach_media_metrics(self, run_manifest: RunManifest, *, source_path: str | Path, output_path: Path) -> None:
        source = Path(source_path)
        if not source.exists() or not output_path.exists() or not self.ffprobe.is_available():
            return
        try:
            input_metrics = summarize_media_probe(self.ffprobe.probe(source))
            output_metrics = summarize_media_probe(self.ffprobe.probe(output_path))
        except Exception:  # noqa: BLE001
            run_manifest.warnings.append("Detailed before/after media metrics were not collected for this run.")
            return
        comparison = compare_media_metrics(
            input_metrics,
            output_metrics,
            encode_profile_id=str(run_manifest.encode_settings.get("encode_profile_id") or ""),
            preserve_chapters=bool(run_manifest.encode_settings.get("preserve_chapters", True)),
            config=self.config.conversion_guidance,
        )
        run_manifest.encode_settings["media_metrics"] = {
            "input": input_metrics,
            "output": output_metrics,
            "comparison": comparison,
        }
        if comparison.get("guidance"):
            run_manifest.encode_settings["conversion_guidance"] = list(comparison["guidance"])

    def _working_output_path(self, output_path: Path) -> Path:
        return output_path.with_name(f"{output_path.stem}.partial{output_path.suffix}")

    def _planned_output_path(
        self,
        *,
        manifest: ProjectManifest,
        output_root: Path,
        source_path: Path,
        container: str,
        reserved_outputs: set[Path],
    ) -> Path:
        relative_parent = self._relative_output_parent(manifest.source_files, source_path)
        filename_stem = self._render_output_stem(manifest, source_path)
        candidate_dir = output_root / relative_parent
        candidate_dir.mkdir(parents=True, exist_ok=True)
        candidate = candidate_dir / f"{filename_stem}.{container}"
        if candidate.resolve() not in reserved_outputs and not candidate.exists():
            return candidate

        suffix_index = 2
        while True:
            suffix = self.config.app.output_collision_template.format(index=suffix_index)
            collision_candidate = candidate_dir / f"{filename_stem}{suffix}.{container}"
            if collision_candidate.resolve() not in reserved_outputs and not collision_candidate.exists():
                return collision_candidate
            suffix_index += 1

    def _relative_output_parent(self, source_files: list[str], source_path: Path) -> Path:
        if self.config.app.output_layout != "preserve_relative":
            return Path()
        if len(source_files) <= 1:
            return Path()
        try:
            common_root = Path(os.path.commonpath([str(Path(item).resolve().parent) for item in source_files]))
            if common_root == source_path.resolve().parent:
                return Path()
            return source_path.resolve().parent.relative_to(common_root)
        except ValueError:
            return Path()

    def _render_output_stem(self, manifest: ProjectManifest, source_path: Path) -> str:
        relative_parent = self._relative_output_parent(manifest.source_files, source_path)
        relative_stem = source_path.stem
        if relative_parent != Path():
            relative_stem = "__".join([part for part in relative_parent.parts if part] + [source_path.stem])
        try:
            rendered = self.config.app.output_name_template.format(
                stem=source_path.stem,
                suffix=source_path.suffix.lstrip("."),
                relative_stem=relative_stem,
                parent_name=source_path.parent.name,
                profile_id=manifest.selected_profile_id,
            )
        except KeyError:
            rendered = source_path.stem
        return self._sanitize_output_stem(rendered or source_path.stem)

    def _sanitize_output_stem(self, value: str) -> str:
        sanitized = re.sub(r'[<>:"/\\\\|?*]+', "_", value).strip().strip(".")
        return sanitized or "output"

    def _rebuild_manifest(self, record: JobRecord, run_manifest: RunManifest) -> ProjectManifest:
        context = dict(run_manifest.encode_settings.get("execution_context", {}))
        selected_profile_id = context.get("selected_profile_id")
        output_policy = context.get("output_policy")
        if not selected_profile_id or not isinstance(output_policy, dict):
            raise RuntimeError("Run manifest is missing execution context; the job cannot be resumed safely.")
        return ProjectManifest(
            project_id=run_manifest.project_id,
            created_at=run_manifest.created_at,
            source_files=[record.source_path],
            selected_profile_id=str(selected_profile_id),
            output_policy=output_policy,
            resolved_pipeline_stages=run_manifest.final_pipeline,
            backend_preferences=list(context.get("backend_preferences", [])),
            model_preferences=run_manifest.models_used,
            batch_settings=dict(context.get("batch_settings", {})),
            per_file_overrides=dict(context.get("per_file_overrides", {})),
            custom_model_paths=list(context.get("custom_model_paths", [])),
            hook_references=list(context.get("hook_references", [])),
            warnings=list(context.get("warnings", [])),
        )

    def _build_video_filters(self, manifest: ProjectManifest) -> list[str]:
        filters: list[str] = []
        for stage in manifest.resolved_pipeline_stages:
            if not stage.enabled:
                continue
            template = self.config.fallback_filters.stage_filters.get(stage.stage_id, {}).get("execution")
            if not template:
                continue
            if stage.stage_id == "upscale":
                width = manifest.output_policy.get("width")
                height = manifest.output_policy.get("height")
                if width and height:
                    filters.append(template.format(width=width, height=height))
                else:
                    filters.append(self.config.fallback_filters.execution_default_upscale)
            else:
                filters.append(template)
        return filters
