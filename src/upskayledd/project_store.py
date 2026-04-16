from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from upskayledd.core.paths import ensure_directory, resolve_runtime_path
from upskayledd.models import JobRecord, JobStatus, PreviewResult, utc_now


class ProjectStore:
    def __init__(self, database_path: str | Path) -> None:
        resolved = resolve_runtime_path(database_path)
        ensure_directory(resolved.parent)
        self.database_path = resolved
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> sqlite3.Connection:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL,
                    payload_path TEXT NOT NULL,
                    error_message TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS preview_cache (
                    cache_key TEXT PRIMARY KEY,
                    metadata_path TEXT NOT NULL,
                    fidelity_mode TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS app_state (
                    state_key TEXT PRIMARY KEY,
                    state_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def upsert_job(self, record: JobRecord) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO jobs (job_id, project_id, source_path, status, progress, payload_path, error_message, updated_at)
                VALUES (:job_id, :project_id, :source_path, :status, :progress, :payload_path, :error_message, :updated_at)
                ON CONFLICT(job_id) DO UPDATE SET
                    project_id=excluded.project_id,
                    source_path=excluded.source_path,
                    status=excluded.status,
                    progress=excluded.progress,
                    payload_path=excluded.payload_path,
                    error_message=excluded.error_message,
                    updated_at=excluded.updated_at
                """,
                {
                    "job_id": record.job_id,
                    "project_id": record.project_id,
                    "source_path": record.source_path,
                    "status": record.status.value,
                    "progress": record.progress,
                    "payload_path": record.payload_path,
                    "error_message": record.error_message,
                    "updated_at": record.updated_at,
                },
            )

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return JobRecord.from_row(dict(row)) if row else None

    def list_jobs(self) -> list[JobRecord]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM jobs ORDER BY updated_at DESC").fetchall()
        return [JobRecord.from_row(dict(row)) for row in rows]

    def update_job_status(self, job_id: str, status: JobStatus, progress: float, error_message: str | None = None) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, progress = ?, error_message = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (status.value, progress, error_message, utc_now(), job_id),
            )

    def record_preview_cache(self, cache_key: str, metadata_path: str, fidelity_mode: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO preview_cache (cache_key, metadata_path, fidelity_mode, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    metadata_path=excluded.metadata_path,
                    fidelity_mode=excluded.fidelity_mode,
                    updated_at=excluded.updated_at
                """,
                (cache_key, metadata_path, fidelity_mode, utc_now()),
            )

    def get_preview_cache(self, cache_key: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM preview_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        return dict(row) if row else None

    def set_app_state(self, key: str, value: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO app_state (state_key, state_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    state_value=excluded.state_value,
                    updated_at=excluded.updated_at
                """,
                (key, value, utc_now()),
            )

    def get_app_state(self, key: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT state_value FROM app_state WHERE state_key = ?",
                (key,),
            ).fetchone()
        return row["state_value"] if row else None

    def read_preview_result(self, metadata_path: str | Path) -> PreviewResult:
        from upskayledd.manifest_writer import read_artifact

        return PreviewResult.from_dict(read_artifact(metadata_path))
