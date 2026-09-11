"""NFR-SPINE.4 — the honesty invariants hold everywhere. These are the tests that make a fabricated
number impossible to construct."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from exog_signals.domain.errors import InvariantError
from exog_signals.domain.types import (
    Citation, CompanyProfile, ImpactRead, Magnitude, Provenance, Sample)
from conftest import prov, NOW


def _base(**over):
    d = dict(signal_id="s", signal_type="calendar", region_key="IN-MH", category="c",
             direction="lift", lead_days=21, tail_days=7, evidence="prior", confidence=0.2,
             method="m", provenance=prov(licence="derived"),
             magnitude=Magnitude(0.1, 0.05, 0.15), citations=[Citation("src", quality=0.7)], status="accepted_auto")
    d.update(over)
    return d


def test_measured_requires_magnitude_and_sample():
    with pytest.raises(InvariantError):
        ImpactRead(**_base(evidence="measured", magnitude=None, sample=None, citations=[], confidence=0.8))


def test_measured_ok_with_magnitude_and_sample():
    r = ImpactRead(**_base(evidence="measured", confidence=0.8, citations=[],
                           magnitude=Magnitude(0.15, 0.1, 0.2), sample=Sample(3, 90, 3), status="measured"))
    assert r.evidence == "measured"


def test_prior_confidence_capped():
    with pytest.raises(InvariantError):
        ImpactRead(**_base(evidence="prior", confidence=0.5))


def test_prior_requires_citations():
    with pytest.raises(InvariantError):
        ImpactRead(**_base(evidence="prior", citations=[]))


def test_prior_magnitude_must_be_band_not_point():
    with pytest.raises(InvariantError):
        ImpactRead(**_base(evidence="prior", magnitude=Magnitude(0.1, 0.1, 0.1)))  # degenerate = point


def test_unknown_must_be_neutral_and_no_magnitude():
    with pytest.raises(InvariantError):
        ImpactRead(**_base(evidence="unknown", direction="lift", magnitude=None, citations=[]))
    ok = ImpactRead(**_base(evidence="unknown", direction="neutral", magnitude=None, citations=[],
                            confidence=0.0, status="unknown"))
    assert ok.evidence == "unknown"


def test_provenance_must_be_tz_aware():
    naive = datetime(2026, 9, 9)
    with pytest.raises(InvariantError):
        Provenance(source="s", as_of=naive, fetched_at=naive, licence="MIT")


def test_provenance_as_of_not_after_fetched():
    later = datetime(2026, 9, 10, tzinfo=timezone.utc)
    with pytest.raises(InvariantError):
        Provenance(source="s", as_of=later, fetched_at=NOW, licence="MIT")


def test_provenance_requires_licence():
    with pytest.raises(InvariantError):
        Provenance(source="s", as_of=NOW, fetched_at=NOW, licence="")


def test_company_profile_mix_must_sum_to_one():
    with pytest.raises(InvariantError):
        CompanyProfile("k", "K", {"a": 0.6, "b": 0.6}, "t", ["IN"], prov())
    ok = CompanyProfile("k", "K", {"a": 0.6, "b": 0.4}, "t", ["IN"], prov(), evidence="measured")
    assert abs(sum(ok.category_mix.values()) - 1.0) < 1e-9


def test_magnitude_point_within_band():
    with pytest.raises(InvariantError):
        Magnitude(point=0.5, low=0.1, high=0.2)
