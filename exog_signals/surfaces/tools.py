"""FR-SPINE.5 — the transport-agnostic tool registry both the MCP (stdio) and HTTP surfaces bind to.

The registry holds pure handlers + their input JSON-schemas; ``handle(method, path, body)`` is a pure
function so it can be tested without sockets. Surfaces hold zero logic (Anuj §8.1): the stdio ``mcp``
SDK and the stdlib HTTP server both just call ``handle``. The two agents register their
``calendar.*`` / ``weather.*`` tools into this same registry."""
from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Callable, Dict, Optional, Tuple


def to_jsonable(obj):
    """Serialise domain dataclasses / datetimes to plain JSON types (no pydantic dependency)."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: to_jsonable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj


class ToolRegistry:
    def __init__(self) -> None:
        self._handlers: Dict[str, Callable[[dict], object]] = {}
        self._schemas: Dict[str, dict] = {}

    def register(self, name: str, handler: Callable[[dict], object], input_schema: dict) -> None:
        self._handlers[name] = handler
        self._schemas[name] = input_schema

    def names(self):
        return sorted(self._handlers)

    def schemas(self) -> Dict[str, dict]:
        return dict(self._schemas)

    def call(self, name: str, params: Optional[dict] = None):
        if name not in self._handlers:
            raise KeyError(name)
        return to_jsonable(self._handlers[name](params or {}))

    def handle(self, method: str, path: str, body: Optional[dict]) -> Tuple[int, dict]:
        """Pure request handler. Path is ``/mcp/tools/<name>``; params come from the JSON body."""
        prefix = "/mcp/tools/"
        if not path.startswith(prefix):
            return 404, {"error": f"unknown path {path!r}"}
        name = path[len(prefix):]
        if name == "":  # discovery
            return 200, {"tools": self.names(), "schemas": self.schemas()}
        try:
            return 200, {"result": self.call(name, body or {})}
        except KeyError:
            return 404, {"error": f"unknown tool {name!r}"}
        except Exception as exc:  # noqa: BLE001 — typed domain errors surface as 422 to the caller
            return 422, {"error": type(exc).__name__, "detail": str(exc)}


def build_core_registry(store, resolver, profile_service, now_provider) -> ToolRegistry:
    """Register the spine's own tools. ``now_provider()`` returns a tz-aware datetime (injected so the
    call is deterministic in tests)."""
    reg = ToolRegistry()

    reg.register(
        "signals.feed_status",
        lambda p: {"feeds": store.get_feed_statuses()},
        {"type": "object", "properties": {}, "additionalProperties": False})

    def _profile(p: dict):
        prof = profile_service.get(p["company"], now_provider())
        if prof is None:
            return {"company": p["company"], "profile": None, "evidence": "unknown"}
        return {"company": p["company"], "profile": prof}

    reg.register(
        "company.get_profile", _profile,
        {"type": "object", "required": ["company"],
         "properties": {"company": {"type": "string"}}, "additionalProperties": False})

    reg.register(
        "signals.refresh",
        lambda p: {"status": "not_implemented_in_spine",
                   "note": "calendar/weather agents register their own refresh"},
        {"type": "object", "properties": {"feed": {"type": "string"}}, "additionalProperties": True})

    return reg
