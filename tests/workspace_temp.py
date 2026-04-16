from __future__ import annotations

import shutil
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_TEMP_ROOT = ROOT / "runtime" / "test-scratch"


class WorkspaceTemporaryDirectory:
    """Lightweight test temp-dir replacement rooted inside the workspace."""

    def __init__(
        self,
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | None = None,
        ignore_cleanup_errors: bool = False,
    ) -> None:
        base = Path(dir) if dir else BASE_TEMP_ROOT
        base.mkdir(parents=True, exist_ok=True)
        folder_name = f"{prefix or 'tmp'}{uuid.uuid4().hex}{suffix or ''}"
        self.path = base / folder_name
        self.path.mkdir(parents=True, exist_ok=False)
        self.name = str(self.path)
        self.ignore_cleanup_errors = ignore_cleanup_errors

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        shutil.rmtree(self.path, ignore_errors=self.ignore_cleanup_errors)
