"""Thin stdlib HTTP surface over the tool registry (the ARS-facing ``/mcp/tools/<name>`` convention).
All logic is in ``ToolRegistry.handle`` — this file is only transport (Anuj §8.1).

Single-threaded by design: the in-memory SQLite stores are created on the serving thread (the CLI ``serve``
verbs build the registry and call :func:`serve_forever` on the same thread), so a request handler never touches
a SQLite connection cross-thread. Scale by running several single-worker instances behind a load balancer, or
mount the registry under the optional ``http`` (FastAPI/uvicorn) extra with thread-safe stores.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from .tools import ToolRegistry


def _read_body(handler: BaseHTTPRequestHandler) -> bytes:
    """Read the full request body, honouring ``Transfer-Encoding: chunked``.

    A ``Content-Length``-only reader silently drops a chunked body — and common clients (for example .NET
    ``HttpClient.PostAsJsonAsync``) send the body chunked with no ``Content-Length``. That produced an empty
    params dict here and a misleading "unknown tool" error downstream; reading the chunks fixes the interop.
    """
    te = (handler.headers.get("Transfer-Encoding") or "").lower()
    if "chunked" in te:
        chunks = []
        while True:
            size_line = handler.rfile.readline()
            if not size_line:
                break
            size = int(size_line.split(b";", 1)[0].strip() or b"0", 16)   # ignore any chunk extensions
            if size == 0:
                handler.rfile.readline()   # consume the trailing CRLF of the terminating chunk
                break
            chunks.append(handler.rfile.read(size))
            handler.rfile.readline()       # consume the CRLF after each chunk's data
        return b"".join(chunks)
    length = int(handler.headers.get("Content-Length") or 0)
    return handler.rfile.read(length) if length else b""


def make_handler(registry: ToolRegistry):
    class _Handler(BaseHTTPRequestHandler):
        def _run(self, method: str) -> None:
            raw = _read_body(self)
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
    """Build (but do not start) the HTTP server bound to ``registry``."""
    return HTTPServer((host, port), make_handler(registry))


def serve_forever(registry: ToolRegistry, host: str = "127.0.0.1", port: int = 8080) -> None:
    """Build and run the server until interrupted (blocking). Build the registry on the SAME thread that calls
    this so the single-threaded server never touches the SQLite stores from another thread."""
    server = serve(registry, host, port)
    print(f"exog MCP serving on http://{host}:{port}  tools={registry.names()}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover — operator Ctrl-C
        pass
    finally:
        server.server_close()
