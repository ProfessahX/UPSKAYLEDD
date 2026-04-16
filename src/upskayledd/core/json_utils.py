from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def stable_json_dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True)


def write_json(path: str | Path, data: dict[str, Any]) -> Path:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(stable_json_dumps(data) + "\n", encoding="utf-8")
    return resolved


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))

