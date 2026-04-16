from __future__ import annotations

from pathlib import Path
from typing import Any

from upskayledd.core.json_utils import read_json, write_json


def write_artifact(path: str | Path, payload: dict[str, Any]) -> Path:
    return write_json(path, payload)


def read_artifact(path: str | Path) -> dict[str, Any]:
    return read_json(path)

