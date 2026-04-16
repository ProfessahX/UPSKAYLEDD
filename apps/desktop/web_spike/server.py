from __future__ import annotations

import json
import mimetypes
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from upskayledd.app_service import AppService
from upskayledd.models import ComparisonMode, FidelityMode


STATIC_DIR = Path(__file__).resolve().parent / "static"
PREVIEW_ROOT = ROOT / "runtime" / "cache" / "previews"


class SpikeHandler(BaseHTTPRequestHandler):
    service = AppService()

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/api/doctor":
            self._write_json(self.service.doctor_report())
            return
        if route == "/api/model-packs":
            self._write_json(self.service.list_model_packs())
            return
        if route == "/api/shell-criteria":
            self._write_json(
                {
                    "criteria": [
                        "synced preview quality",
                        "three-zone layout effort",
                        "packaging/bootstrap complexity",
                        "cross-platform integration",
                        "dashboard/workspace development speed",
                    ],
                    "service_boundary": "The browser shell calls AppService-backed endpoints and does not own processing logic.",
                }
            )
            return
        if route == "/preview-artifact":
            self._write_preview_artifact()
            return
        if route in {"/", "/index.html"}:
            self._write_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route != "/api/preview":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        source_path = str(payload.get("source_path", "")).strip()
        if not source_path:
            self.send_error(HTTPStatus.BAD_REQUEST, "source_path is required")
            return
        stage_id = str(payload.get("stage_id", "cleanup"))
        stage_settings = dict(payload.get("stage_settings", {}))
        result = self.service.prepare_preview(
            source_path=source_path,
            stage_id=stage_id,
            comparison_mode=ComparisonMode.SLIDER_WIPE,
            stage_settings=stage_settings,
            fidelity_mode=FidelityMode.EXACT,
        )
        payload = result.to_dict()
        payload["preview_urls"] = {
            key: f"/preview-artifact?path={quote(value)}"
            for key, value in result.comparison_artifacts.items()
        }
        self._write_json(payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _write_json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_file(self, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_preview_artifact(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        raw_path = query.get("path", [""])[0]
        if not raw_path:
            self.send_error(HTTPStatus.BAD_REQUEST, "path is required")
            return
        candidate = Path(raw_path).resolve()
        try:
            candidate.relative_to(PREVIEW_ROOT.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN, "preview artifact must live under runtime/cache/previews")
            return
        if not candidate.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "preview artifact not found")
            return
        content_type, _ = mimetypes.guess_type(candidate.name)
        self._write_file(candidate, content_type or "application/octet-stream")


def main(port: int = 8765) -> int:
    server = ThreadingHTTPServer(("127.0.0.1", port), SpikeHandler)
    print(f"UPSKAYLEDD web spike listening at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
