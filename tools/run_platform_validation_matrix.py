from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PureWindowsPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"


def windows_to_wsl_path(path: Path) -> str:
    raw = str(path).replace("\\", "/")
    windows_path = PureWindowsPath(raw)
    drive = windows_path.drive.rstrip(":")
    if drive:
        tail = "/".join(windows_path.parts[1:])
        return f"/mnt/{drive.lower()}/{tail}" if tail else f"/mnt/{drive.lower()}"
    return raw


def summarize_context(
    context_id: str,
    display_name: str,
    doctor_report: dict[str, Any] | None,
    setup_payload: dict[str, Any] | None,
    *,
    available: bool = True,
    error: str = "",
) -> dict[str, Any]:
    doctor = dict(doctor_report or {})
    setup = dict(setup_payload or {})
    checks = list(doctor.get("checks", []))
    actions = list(setup.get("actions", []))
    missing_checks = [item for item in checks if str(item.get("status", "")) == "missing"]
    degraded_checks = [item for item in checks if str(item.get("status", "")) == "degraded"]
    if not available:
        health = "unavailable"
    elif actions:
        health = "attention"
    elif missing_checks or degraded_checks or doctor.get("warnings"):
        health = "watch"
    else:
        health = "ready"
    return {
        "context_id": context_id,
        "display_name": display_name,
        "available": available,
        "health": health,
        "platform_summary": str(doctor.get("platform_summary", "")).strip(),
        "missing_check_count": len(missing_checks),
        "degraded_check_count": len(degraded_checks),
        "action_count": len(actions),
        "missing_check_names": [str(item.get("name", "")).strip() for item in missing_checks if str(item.get("name", "")).strip()],
        "path_rules": list(doctor.get("path_rules", [])),
        "warnings": list(doctor.get("warnings", [])),
        "actions": actions,
        "doctor_report": doctor,
        "setup_plan": setup,
        "error": error,
    }


def build_watch_items(contexts: list[dict[str, Any]]) -> list[str]:
    items: list[str] = []
    for context in contexts:
        label = str(context.get("display_name", context.get("context_id", "context")))
        if not context.get("available", True):
            items.append(f"{label} validation could not be collected automatically.")
            continue
        if int(context.get("missing_check_count", 0) or 0) > 0:
            items.append(f"{label} still has missing runtime checks.")
        elif int(context.get("degraded_check_count", 0) or 0) > 0 and context.get("warnings"):
            items.append(f"{label} is usable but still carries degraded runtime checks.")
        if int(context.get("action_count", 0) or 0) > 0:
            items.append(f"{label} still has prioritized setup actions to clear.")
    if len(contexts) >= 2:
        native = next((item for item in contexts if item.get("context_id") == "windows_native"), None)
        wsl = next((item for item in contexts if item.get("context_id") == "linux_wsl"), None)
        if native and wsl and native.get("health") != wsl.get("health"):
            items.append("Native Windows and Linux-side WSL currently differ in runtime readiness.")
    if not items:
        items.append("Native and collected secondary runtime contexts look aligned enough for the current release-hardening pass.")
    return items


def _native_payload(repo_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        doctor_json = temp_root / "doctor.json"
        setup_json = temp_root / "setup.json"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SRC_DIR)
        subprocess.run(
            [sys.executable, "-m", "upskayledd", "doctor", "--json-output", str(doctor_json)],
            cwd=repo_root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [sys.executable, "-m", "upskayledd", "setup-plan", "--json-output", str(setup_json)],
            cwd=repo_root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        return {
            "doctor": json.loads(doctor_json.read_text(encoding="utf-8")),
            "setup_plan": json.loads(setup_json.read_text(encoding="utf-8")),
        }


def _wsl_payload(repo_root: Path) -> dict[str, Any]:
    wsl = shutil.which("wsl.exe")
    if not wsl:
        raise RuntimeError("wsl.exe is not available on this machine.")
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        doctor_json = temp_root / "doctor.json"
        setup_json = temp_root / "setup.json"
        repo_root_wsl = windows_to_wsl_path(repo_root)
        doctor_json_wsl = windows_to_wsl_path(doctor_json)
        setup_json_wsl = windows_to_wsl_path(setup_json)
        command = (
            f"cd {shlex.quote(repo_root_wsl)} && "
            f"PYTHONPATH=src python3 -m upskayledd doctor --json-output {shlex.quote(doctor_json_wsl)} >/dev/null && "
            f"PYTHONPATH=src python3 -m upskayledd setup-plan --json-output {shlex.quote(setup_json_wsl)} >/dev/null"
        )
        subprocess.run(
            [wsl, "bash", "-lc", command],
            check=True,
            capture_output=True,
            text=True,
        )
        return {
            "doctor": json.loads(doctor_json.read_text(encoding="utf-8")),
            "setup_plan": json.loads(setup_json.read_text(encoding="utf-8")),
        }


def collect_contexts(repo_root: Path) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    try:
        native_payload = _native_payload(repo_root)
    except Exception as exc:  # noqa: BLE001
        contexts.append(
            summarize_context(
                "windows_native",
                "Windows (native)",
                None,
                None,
                available=False,
                error=str(exc),
            )
        )
    else:
        contexts.append(
            summarize_context(
                "windows_native",
                "Windows (native)",
                native_payload["doctor"],
                native_payload["setup_plan"],
            )
        )
    try:
        wsl_payload = _wsl_payload(repo_root)
    except Exception as exc:  # noqa: BLE001
        contexts.append(
            summarize_context(
                "linux_wsl",
                "Linux (WSL)",
                None,
                None,
                available=False,
                error=str(exc),
            )
        )
    else:
        contexts.append(
            summarize_context(
                "linux_wsl",
                "Linux (WSL)",
                wsl_payload["doctor"],
                wsl_payload["setup_plan"],
            )
        )
    return contexts


def main(argv: list[str] | None = None) -> int:
    output_path = ROOT / "runtime" / "validation" / "platform_validation_matrix.json"
    if argv:
        output_path = Path(argv[0]).resolve()
    contexts = collect_contexts(ROOT)
    payload = {
        "repo_root": str(ROOT),
        "contexts": contexts,
        "watch_items": build_watch_items(contexts),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
