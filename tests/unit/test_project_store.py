from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from upskayledd.models import JobRecord, JobStatus
from upskayledd.project_store import ProjectStore


class ProjectStoreTests(unittest.TestCase):
    def test_upserts_and_reads_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "state.sqlite3"
            store = ProjectStore(db_path)
            record = JobRecord(
                job_id="job-1",
                project_id="proj-1",
                source_path="source.mkv",
                status=JobStatus.QUEUED,
                progress=0.0,
                payload_path="payload.json",
            )
            store.upsert_job(record)
            loaded = store.get_job("job-1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.status, JobStatus.QUEUED)


if __name__ == "__main__":
    unittest.main()

