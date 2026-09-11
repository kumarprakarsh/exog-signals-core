from __future__ import annotations

import pytest

from exog_signals.application.source_registry import SourceRegistry, select_with_fallback
from exog_signals.domain.errors import InvariantError, SourceUnavailable
from exog_signals.domain.types import RegionKey

SPEC = [
    {"match": {"country": "IN"}, "sources": [
        {"name": "imd", "licence": "OGD-India", "attribution": "IMD", "independent_model": True},
        {"name": "open_meteo_selfhost", "licence": "AGPL-selfhost"},
        {"name": "scraper_lastresort", "licence": "none-scrape", "enabled": False},
    ]},
    {"match": {"country": "*"}, "sources": [
        {"name": "open_meteo_selfhost", "licence": "AGPL-selfhost"},
        {"name": "nasa_power", "licence": "NASA-open"},
    ]},
]


def test_ranked_enabled_order_and_wildcard():
    reg = SourceRegistry.from_list(SPEC)
    assert [e.name for e in reg.resolve(RegionKey("IN"))] == ["imd", "open_meteo_selfhost"]  # scraper disabled dropped
    assert [e.name for e in reg.resolve(RegionKey("US"))] == ["open_meteo_selfhost", "nasa_power"]


def test_entry_without_licence_is_refused_at_load():
    with pytest.raises(InvariantError):
        SourceRegistry.from_list([{"match": {"country": "IN"}, "sources": [{"name": "x"}]}])


def test_fallback_tries_next_when_first_dead_and_never_calls_disabled():
    reg = SourceRegistry.from_list(SPEC)
    called = []

    def try_fn(entry):
        called.append(entry.name)
        if entry.name == "imd":
            raise RuntimeError("imd down")
        return {"served_by": entry.name}

    result, report = select_with_fallback(reg.resolve(RegionKey("IN")), try_fn)
    assert result["served_by"] == "open_meteo_selfhost"
    assert report.used == "open_meteo_selfhost"
    assert any("imd" in f for f in report.failed)
    assert "scraper_lastresort" not in called  # disabled → never tried


def test_all_sources_failing_raises():
    reg = SourceRegistry.from_list(SPEC)
    with pytest.raises(SourceUnavailable):
        select_with_fallback(reg.resolve(RegionKey("IN")), lambda e: (_ for _ in ()).throw(RuntimeError("x")))
