from __future__ import annotations

import pytest

from exog_signals.application.region_resolver import RegionResolver
from exog_signals.domain.errors import RegionTooCoarse, UnresolvedRegion


@pytest.fixture
def r():
    return RegionResolver()


def test_name_iso_and_coords_all_resolve_to_the_subdivision(r):
    for value in ["Maharashtra", "IN-MH", (19.07, 72.88)]:
        rk = r.resolve(value)
        assert rk.subdivision == "IN-MH"
        assert rk.country == "IN"
        assert rk.grid_id and rk.grid_id.startswith("g:")


def test_country_resolves_with_no_subdivision(r):
    rk = r.resolve("India")
    assert rk.country == "IN" and rk.subdivision is None
    assert r.resolve("IN").subdivision is None


def test_state_only_event_stays_state(r):
    assert r.resolve("Kerala").subdivision == "IN-KL"


def test_unknown_is_a_typed_error_not_a_guess(r):
    with pytest.raises(UnresolvedRegion):
        r.resolve("Atlantis")
    with pytest.raises(UnresolvedRegion):
        r.resolve("")


def test_require_subcountry_rejects_a_country(r):
    with pytest.raises(RegionTooCoarse):
        r.resolve("IN", require_subcountry=True)
    # but a subdivision passes
    assert r.resolve("IN-MH", require_subcountry=True).subdivision == "IN-MH"


def test_tz_is_region_local(r):
    assert r.tz_of(r.resolve("IN-MH")) == "Asia/Kolkata"
    assert r.tz_of(r.resolve("US-TX")) == "America/Chicago"
