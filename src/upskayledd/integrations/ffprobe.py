from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from upskayledd.core.errors import ExternalToolError


class FFprobeAdapter:
    def __init__(self, executable: str = "ffprobe") -> None:
        self.executable = executable

    def is_available(self) -> bool:
        return shutil.which(self.executable) is not None

    def probe(self, path: str | Path) -> dict[str, Any]:
        if not self.is_available():
            raise ExternalToolError("ffprobe is not available on PATH.")

        command = [
            self.executable,
            "-v",
            "error",
            "-show_entries",
            "format:stream:chapter",
            "-show_streams",
            "-show_format",
            "-show_chapters",
            "-of",
            "json",
            str(path),
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise ExternalToolError(
                f"ffprobe failed for {path}: {completed.stderr.strip() or completed.stdout.strip()}"
            )
        return json.loads(completed.stdout or "{}")

