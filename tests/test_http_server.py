"""FR-SPINE.5 — the stdlib HTTP surface: the body reader (Content-Length AND chunked) and a live round-trip.

The chunked path is the one that matters for interop: clients like .NET ``HttpClient.PostAsJsonAsync`` send the
body chunked with no Content-Length, and a Content-Length-only reader silently drops it.
"""
import io
import json
import threading
import http.client
from datetime import datetime, timezone

from exog_signals.surfaces.http_server import _read_body, serve
from exog_signals.surfaces.tools import build_core_registry
from exog_signals.application.company_profile import (
    CompanyProfileService, NullResearchProfileProvider, StaticArsProfileProvider)
from exog_signals.application.region_resolver import RegionResolver
from exog_signals.infrastructure.store import SqliteStore


class _FakeHandler:
    """Minimal stand-in for a BaseHTTPRequestHandler: just .headers and .rfile, which is all _read_body touches."""
    def __init__(self, headers: dict, body: bytes):
        self.headers = headers
        self.rfile = io.BytesIO(body)


def test_read_body_content_length():
    h = _FakeHandler({"Content-Length": "5"}, b"helloEXTRA")
    assert _read_body(h) == b"hello"


def test_read_body_chunked():
    # "hi there" split into two chunks, terminated by a 0-length chunk (the shape .NET emits).
    body = b"2\r\nhi\r\n6\r\n there\r\n0\r\n\r\n"
    h = _FakeHandler({"Transfer-Encoding": "chunked"}, body)
    assert _read_body(h) == b"hi there"


def test_read_body_empty():
    assert _read_body(_FakeHandler({}, b"")) == b""


def test_server_roundtrip_serves_a_real_tool():
    now = lambda: datetime(2026, 9, 14, tzinfo=timezone.utc)
    holder = {}
    ready = threading.Event()

    def run():
        # Build the registry (and its SQLite store) ON THIS thread, then serve on it — mirrors the CLI serve verb
        # and keeps the single-threaded server off cross-thread SQLite.
        store = SqliteStore(":memory:")
        reg = build_core_registry(
            store, RegionResolver(),
            CompanyProfileService([StaticArsProfileProvider({}), NullResearchProfileProvider()]), now)
        srv = serve(reg, "127.0.0.1", 0)         # port 0 → an ephemeral free port
        holder["port"] = srv.server_address[1]
        holder["srv"] = srv
        ready.set()
        srv.serve_forever()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    assert ready.wait(5), "server did not start"
    try:
        conn = http.client.HTTPConnection("127.0.0.1", holder["port"], timeout=5)
        conn.request("POST", "/mcp/tools/signals.feed_status", body="{}",
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        assert resp.status == 200
        payload = json.loads(resp.read())
        assert "result" in payload and "feeds" in payload["result"]
    finally:
        holder["srv"].shutdown()
        holder["srv"].server_close()
