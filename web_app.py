"""Local web frontend for the thread scheduling simulator (standard library only)."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import thread_simulator as simulator

ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"

class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, content_type: str, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            target = WEB_ROOT / "index.html"
            self._send(200, "text/html; charset=utf-8", target.read_bytes())
        elif path == "/PROJECT_GUIDE.md":
            target = ROOT / "PROJECT_GUIDE.md"
            self._send(200, "text/markdown; charset=utf-8", target.read_bytes())
        elif path == "/PARAMETER_REFERENCE.md":
            target = ROOT / "PARAMETER_REFERENCE.md"
            self._send(200, "text/markdown; charset=utf-8", target.read_bytes())
        elif path == "/training-data.csv":
            payload = simulator.training_dataset_csv().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=synthetic_training_data.csv")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif path == "/health":
            self._send(200, "application/json; charset=utf-8", b'{"status":"ok"}')
        else:
            self._send(404, "text/plain; charset=utf-8", b"Not found")

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/run":
            self._send(404, "application/json; charset=utf-8", b'{"error":"Not found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 4096:
                raise ValueError("Request is too large")
            values = json.loads(self.rfile.read(length) or b"{}")
            phase = str(values.get("phase", "all"))
            quantum = int(values.get("quantum", 10))
            ult_switch = int(values.get("ult_switch", 1))
            klt_switch = int(values.get("klt_switch", 2))
            cores = int(values.get("cores", 4))
            if phase not in ("1", "2", "all"):
                raise ValueError("Choose Phase 1, Phase 2, or both.")
            if quantum < 1 or cores < 1 or min(ult_switch, klt_switch) < 0:
                raise ValueError("Quantum and cores must be positive; switch costs cannot be negative.")
            baseline = simulator.compare(quantum, ult_switch, klt_switch, cores) if phase in ("1", "all") else None
            classification = simulator.phase2(quantum, ult_switch, klt_switch, cores) if phase in ("2", "all") else None
            response = {"phase1": baseline, "phase2": classification}
            self._send(200, "application/json; charset=utf-8", json.dumps(response).encode("utf-8"))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self._send(400, "application/json; charset=utf-8", body)
        except Exception as exc:
            body = json.dumps({"error": f"Simulation failed: {exc}"}).encode("utf-8")
            self._send(500, "application/json; charset=utf-8", body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")

def main() -> None:
    host, port = "127.0.0.1", 8000
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Thread Model Simulator UI: http://{host}:{port}")
    print("Press Ctrl+C to stop the local server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
