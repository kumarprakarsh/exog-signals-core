from __future__ import annotations

from exog_signals.application.company_profile import (
    CompanyProfileService, NullResearchProfileProvider, StaticArsProfileProvider)
from exog_signals.application.region_resolver import RegionResolver
from exog_signals.infrastructure.store import SqliteStore
from exog_signals.surfaces.tools import build_core_registry, to_jsonable
from conftest import measured_read, NOW

_PROFILES = {"colgate-in": {"display_name": "Colgate", "category_mix": {"oral_care_toothpaste": 1.0},
                            "geographies": ["IN"]}}


def _registry():
    store = SqliteStore(":memory:")
    store.upsert_feed_status({"feed": "signals_weather", "status": "PRESENT", "as_of": NOW.isoformat(),
                              "rows": 5, "source": "open-meteo", "updated_at": NOW.isoformat()})
    profiles = CompanyProfileService([StaticArsProfileProvider(_PROFILES), NullResearchProfileProvider()])
    return build_core_registry(store, RegionResolver(), profiles, lambda: NOW), store


def test_feed_status_tool_returns_200():
    reg, _ = _registry()
    status, payload = reg.handle("POST", "/mcp/tools/signals.feed_status", {})
    assert status == 200 and payload["result"]["feeds"][0]["status"] == "PRESENT"


def test_unknown_tool_is_404():
    reg, _ = _registry()
    status, payload = reg.handle("POST", "/mcp/tools/nope.nope", {})
    assert status == 404 and "unknown tool" in payload["error"]


def test_unknown_path_is_404():
    reg, _ = _registry()
    status, _payload = reg.handle("GET", "/health", None)
    assert status == 404


def test_company_profile_tool():
    reg, _ = _registry()
    status, payload = reg.handle("POST", "/mcp/tools/company.get_profile", {"company": "colgate-in"})
    assert status == 200
    assert payload["result"]["profile"]["category_mix"] == {"oral_care_toothpaste": 1.0}


def test_discovery_lists_tools_and_schemas():
    reg, _ = _registry()
    status, payload = reg.handle("GET", "/mcp/tools/", None)
    assert status == 200
    assert "signals.feed_status" in payload["tools"]
    assert "company.get_profile" in payload["schemas"]


def test_to_jsonable_serialises_an_impact_read():
    d = to_jsonable(measured_read())
    assert d["evidence"] == "measured"
    assert isinstance(d["provenance"], dict) and isinstance(d["provenance"]["as_of"], str)
