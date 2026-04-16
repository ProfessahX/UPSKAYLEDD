from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any

from upskayledd.config import load_app_config
from upskayledd.core.paths import RuntimeTemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
SUBPROCESS_TIMEOUT_SECONDS = 300


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
    actionable_check_names: set[str] | None = None,
    available: bool = True,
    error: str = "",
) -> dict[str, Any]:
    doctor = dict(doctor_report or {})
    setup = dict(setup_payload or {})
    checks = list(doctor.get("checks", []))
    actions = list(setup.get("actions", []))
    missing_checks = [item for item in checks if str(item.get("status", "")) == "missing"]
    degraded_checks = [item for item in checks if str(item.get("status", "")) == "degraded"]
    actionable_names = set(actionable_check_names or ())
    actionable_missing_checks = [
        item
        for item in missing_checks
        if not actionable_names or str(item.get("name", "")).strip() in actionable_names
    ]
    actionable_degraded_checks = [
        item
        for item in degraded_checks
        if not actionable_names or str(item.get("name", "")).strip() in actionable_names
    ]
    if not available:
        health = "unavailable"
    elif actions:
        health = "attention"
    elif actionable_missing_checks or actionable_degraded_checks or doctor.get("warnings"):
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
        "actionable_missing_check_count": len(actionable_missing_checks),
        "actionable_degraded_check_count": len(actionable_degraded_checks),
        "action_count": len(actions),
        "missing_check_names": [str(item.get("name", "")).strip() for item in missing_checks if str(item.get("name", "")).strip()],
        "actionable_missing_check_names": [
            str(item.get("name", "")).strip()
            for item in actionable_missing_checks
            if str(item.get("name", "")).strip()
        ],
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
        actionable_missing_count = int(context.get("actionable_missing_check_count", context.get("missing_check_count", 0)) or 0)
        actionable_degraded_count = int(
            context.get("actionable_degraded_check_count", context.get("degraded_check_count", 0)) or 0
        )
        if actionable_missing_count > 0:
            items.append(f"{label} still has missing runtime checks.")
        elif actionable_degraded_count > 0:
            items.append(f"{label} is usable but still carries degraded runtime checks.")
        if int(context.get("action_count", 0) or 0) > 0:
            items.append(f"{label} still has prioritized setup actions to clear.")
        elif str(context.get("health", "")).strip() == "watch":
            items.append(f"{label} has warning-level runtime issues worth checking before a long validation run.")
    if len(contexts) >= 2:
        native = next((item for item in contexts if item.get("context_id") == "windows_native"), None)
        wsl = next((item for item in contexts if item.get("context_id") == "linux_wsl"), None)
        if native and wsl and native.get("health") != wsl.get("health"):
            items.append("Native Windows and Linux-side WSL currently differ in runtime readiness.")
    if not items:
        items.append("Native and collected secondary runtime contexts look aligned enough for the current release-hardening pass.")
    return items


def _failure_detail(label: str, exc: subprocess.CalledProcessError) -> RuntimeError:
    stderr = str(exc.stderr or "").replace("\x00", "").strip()
    stdout = str(exc.stdout or "").replace("\x00", "").strip()
    detail = stderr or stdout or f"exit code {exc.returncode}"
    return RuntimeError(f"{label} failed: {detail}")


def _timeout_detail(label: str, exc: subprocess.TimeoutExpired) -> RuntimeError:
    stderr = str(exc.stderr or "").replace("\x00", "").strip()
    stdout = str(exc.stdout or "").replace("\x00", "").strip()
    detail = stderr or stdout or f"timed out after {exc.timeout} seconds"
    return RuntimeError(f"{label} failed: {detail}")


def _native_payload(repo_root: Path, scratch_root: str | Path) -> dict[str, Any]:
    src_dir = repo_root / "src"
    with RuntimeTemporaryDirectory(scratch_root, prefix="platform-matrix-native-") as temp_dir:
        temp_root = Path(temp_dir)
        doctor_json = temp_root / "doctor.json"
        setup_json = temp_root / "setup.json"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(src_dir)
        try:
            subprocess.run(
                [sys.executable, "-m", "upskayledd", "doctor", "--json-output", str(doctor_json)],
                cwd=repo_root,
                env=env,
                check=True,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
            )  # noqa: S603 # trust-boundary: intentional internal CLI invocation
            subprocess.run(
                [sys.executable, "-m", "upskayledd", "setup-plan", "--json-output", str(setup_json)],
                cwd=repo_root,
                env=env,
                check=True,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
            )  # noqa: S603 # trust-boundary: intentional internal CLI invocation
        except subprocess.CalledProcessError as exc:
            raise _failure_detail("Native Windows validation command", exc) from exc
        except subprocess.TimeoutExpired as exc:
            raise _timeout_detail("Native Windows validation command", exc) from exc
        return {
            "doctor": json.loads(doctor_json.read_text(encoding="utf-8")),
            "setup_plan": json.loads(setup_json.read_text(encoding="utf-8")),
        }


def _wsl_payload(repo_root: Path, scratch_root: str | Path) -> dict[str, Any]:
    wsl = shutil.which("wsl.exe")
    if not wsl:
        raise RuntimeError("wsl.exe is not available on this machine.")
    with RuntimeTemporaryDirectory(scratch_root, prefix="platform-matrix-wsl-") as temp_dir:
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
        try:
            subprocess.run(
                [wsl, "bash", "-lc", command],
                check=True,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
            )  # noqa: S603 # trust-boundary: intentional internal CLI invocation
        except subprocess.CalledProcessError as exc:
            raise _failure_detail("Linux-side WSL validation command", exc) from exc
        except subprocess.TimeoutExpired as exc:
            raise _timeout_detail("Linux-side WSL validation command", exc) from exc
        return {
            "doctor": json.loads(doctor_json.read_text(encoding="utf-8")),
            "setup_plan": json.loads(setup_json.read_text(encoding="utf-8")),
        }


def collect_contexts(repo_root: Path) -> list[dict[str, Any]]:
    app_config = load_app_config(str(repo_root / "config"))
    actionable_check_names = set(app_config.runtime_actions.checks.keys())
    scratch_root = app_config.app.scratch_dir
    contexts: list[dict[str, Any]] = []
    if platform.system() == "Windows":
        try:
            native_payload = _native_payload(repo_root, scratch_root)
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
                    actionable_check_names=actionable_check_names,
                )
            )
    else:
        contexts.append(
            summarize_context(
                "windows_native",
                "Windows (native)",
                None,
                None,
                available=False,
                error="not running on a Windows host",
            )
        )
    try:
        wsl_payload = _wsl_payload(repo_root, scratch_root)
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
                actionable_check_names=actionable_check_names,
            )
        )
    return contexts


def build_platform_validation_payload(repo_root: str | Path | None = None) -> dict[str, Any]:
    resolved_repo_root = Path(repo_root or ROOT).resolve()
    contexts = collect_contexts(resolved_repo_root)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "repo_root": str(resolved_repo_root),
        "contexts": contexts,
        "watch_items": build_watch_items(contexts),
    }
