from __future__ import annotations

from exog_signals.application.composer import ImpactComposer
from exog_signals.domain.types import CompanyProfile
from conftest import measured_read, prior_read, prov, unknown_read, NOW


def _profile(mix, evidence="measured"):
    return CompanyProfile("colgate-in", "Colgate", mix, "ars:M10", ["IN"], prov(), evidence=evidence)


def _compose(profile, reads):
    return ImpactComposer().compose(profile, reads, "calendar", "diwali-2026", "IN-MH", 21, 7, NOW)


def test_single_category_returns_that_read_unchanged():
    a = measured_read(category="A")
    out = _compose(_profile({"A": 1.0}), {"A": a})
    assert out is a


def test_measured_plus_prior_composes_to_prior_with_no_number():
    out = _compose(_profile({"A": 0.6, "B": 0.4}),
                   {"A": measured_read(category="A"), "B": prior_read(category="B")})
    assert out.evidence == "prior" and out.magnitude is None and out.direction == "lift"
    assert out.citations  # a prior read must carry its citations


def test_neutral_category_contributes_zero():
    out = _compose(_profile({"A": 0.5, "B": 0.5}),
                   {"A": measured_read(category="A", point=0.2), "B": unknown_read(category="B")})
    assert out.evidence == "measured" and out.direction == "lift"


def test_all_neutral_is_unknown():
    out = _compose(_profile({"A": 0.5, "B": 0.5}),
                   {"A": unknown_read(category="A"), "B": unknown_read(category="B")})
    assert out.evidence == "unknown" and out.direction == "neutral"
