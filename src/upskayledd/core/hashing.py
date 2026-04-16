from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return sha256_text(payload)


def fingerprint_path(path: str | Path) -> str:
    resolved = Path(path)
    stat = resolved.stat()
    payload = {
        "path": str(resolved.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }
    return sha256_json(payload)

