from __future__ import annotations

from exog_signals.application.llm import NullLlmClient, RawPrior
from exog_signals.application.prior_builder import PriorBuilder, score_prior
from conftest import FakeLlmClient, NOW


def _runs(direction="lift", n=3, quality=0.7, band=None, magnitude=False):
    return [RawPrior(direction=direction, band=band,
                     citations=[{"source": f"src{i}", "quality": quality}], claim_has_magnitude=magnitude)
            for i in range(n)]


def test_direction_only_with_good_citations_auto_accepts():
    s = score_prior(_runs())
    assert s.decision == "accepted_auto" and s.earned >= 0.80 and s.modal_direction == "lift"


def test_any_specific_magnitude_claim_is_capped_below_threshold():
    s = score_prior(_runs(magnitude=True))
    assert s.claim_has_magnitude and s.earned < 0.80 and s.decision == "pending_review"


def test_no_citations_is_rejected():
    runs = [RawPrior("lift", None, [], False) for _ in range(3)]
    assert score_prior(runs).decision == "rejected"


def test_no_majority_direction_is_unknown():
    runs = [RawPrior("lift", None, [{"source": "a", "quality": 0.7}], False),
            RawPrior("dip", None, [{"source": "b", "quality": 0.7}], False),
            RawPrior("neutral", None, [{"source": "c", "quality": 0.7}], False)]
    assert score_prior(runs).decision == "unknown"


def test_builder_auto_accepts_a_prior_read_capped_confidence():
    b = PriorBuilder(FakeLlmClient(True, _runs(band=(0.05, 0.20))))
    r = b.build("oral_care_giftpack", "calendar", "diwali-2026", "IN-MH", 21, 7, NOW)
    assert r.evidence == "prior" and r.status == "accepted_auto"
    assert r.confidence <= 0.35 and r.citations
    assert r.magnitude is not None and r.magnitude.is_band  # a band is fine for a prior


def test_builder_with_no_provider_returns_unknown_skipped():
    b = PriorBuilder(NullLlmClient())
    r = b.build("oral_care_toothpaste", "calendar", "diwali-2026", "IN-MH", 21, 7, NOW)
    assert r.evidence == "unknown" and r.status == "unknown" and "skipped" in r.method
    assert r.direction == "neutral" and r.magnitude is None


def test_builder_magnitude_claim_goes_to_review_never_auto():
    b = PriorBuilder(FakeLlmClient(True, _runs(magnitude=True)))
    r = b.build("oral_care_toothpaste", "calendar", "diwali-2026", "IN-MH", 21, 7, NOW)
    assert r.status == "pending_review" and r.evidence == "prior" and r.confidence <= 0.35
