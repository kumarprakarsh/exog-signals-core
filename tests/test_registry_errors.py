"""FR-SPINE.5 — the tool registry gives CONSUMERS distinguishable errors (App-API / recommendation / dashboard
clients need to tell an unknown tool from a bad request from a handler failure). A handler's own KeyError must not
be mislabelled "unknown tool"."""
from exog_signals.surfaces.tools import ToolRegistry


def _reg() -> ToolRegistry:
    r = ToolRegistry()
    r.register("echo", lambda p: {"got": p["x"]},
               {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}})

    def _boom(_p):
        raise ValueError("kaboom")

    r.register("boom", _boom, {"type": "object", "properties": {}})
    return r


def test_unknown_tool_is_404_with_available_list():
    status, body = _reg().handle("POST", "/mcp/tools/nope", {})
    assert status == 404
    assert "unknown tool" in body["error"] and "echo" in body["available"]


def test_missing_required_field_is_400_not_unknown_tool():
    status, body = _reg().handle("POST", "/mcp/tools/echo", {})
    assert status == 400
    assert body["fields"] == ["x"] and "required" in body["schema"]


def test_valid_call_is_200():
    status, body = _reg().handle("POST", "/mcp/tools/echo", {"x": "hi"})
    assert status == 200 and body["result"] == {"got": "hi"}


def test_handler_error_is_422_not_404():
    status, body = _reg().handle("POST", "/mcp/tools/boom", {})
    assert status == 422
    assert body["error"] == "ValueError" and "kaboom" in body["detail"]


def test_discovery_lists_tools_and_schemas():
    status, body = _reg().handle("POST", "/mcp/tools/", {})
    assert status == 200
    assert "echo" in body["tools"] and "echo" in body["schemas"]
