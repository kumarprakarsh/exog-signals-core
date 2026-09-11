"""Thin stdlib HTTP surface over the tool registry (the ARS-facing ``/mcp/tools/<name>`` convention).
All logic is in ``ToolRegistry.handle`` — this file is only transport (Anuj §8.1). The optional
``http`` extra (FastAPI) can mount the same registry; the stdio ``mcp`` extra binds it over JSON-RPC."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from .tools import ToolRegistry


def make_handler(registry: ToolRegistry):
    class _Handler(BaseHTTPRequestHandler):
        def _run(self, method: str) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                status, payload = 400, {"error": "invalid JSON body"}
            else:
                status, payload = registry.handle(method, self.path, body)
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:   # noqa: N802
            self._run("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._run("POST")

        def log_message(self, *args) -> None:  # silence default logging
            return

    return _Handler


def serve(registry: ToolRegistry, host: str = "127.0.0.1", port: int = 8080) -> HTTPServer:
    server = HTTPServer((host, port), make_handler(registry))
    return server
