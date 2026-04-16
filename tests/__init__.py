from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from tests.workspace_temp import WorkspaceTemporaryDirectory

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# Keep test scratch data inside the repo because this Windows/Z-drive setup can
# deny writes to stdlib TemporaryDirectory roots even when normal repo writes work.
tempfile.TemporaryDirectory = WorkspaceTemporaryDirectory  # type: ignore[assignment]
