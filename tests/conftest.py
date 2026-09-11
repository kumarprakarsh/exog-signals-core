from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

import pytest

from exog_signals.application.llm import RawPrior
from exog_signals.domain.types import Citation, ImpactRead, Magnitude, Provenance, Sample

NOW = datetime(2026, 9, 9, 0, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def now() -> datetime:
    return NOW


def prov(source="test", as_of=NOW, fetched_at=NOW, licence="MIT", attribution=None) -> Provenance:
    return Provenance(source=source, as_of=as_of, fetched_at=fetched_at, licence=licence, attribution=attribution)


def measured_read(category="oral_care_toothpaste", region="IN-MH", point=0.15, direction="lift",
                  signal_id="diwali-2026") -> ImpactRead:
    return ImpactRead(
        signal_id=signal_id, signal_type="calendar", region_key=region, category=category,
        direction=direction, lead_days=21, tail_days=7, evidence="measured", confidence=0.8,
        method="matched-baseline-uplift v1", provenance=prov(source="demand-history/x", licence="derived"),
        magnitude=Magnitude(point=point, low=point - 0.05, high=point + 0.05),
        sample=Sample(years=3, n_obs=90, events_observed=3), status="measured")


def prior_read(category="oral_care_giftpack", region="IN-MH", direction="lift", confidence=0.2,
               signal_id="diwali-2026", status="accepted_auto") -> ImpactRead:
    return ImpactRead(
        signal_id=signal_id, signal_type="calendar", region_key=region, category=category,
        direction=direction, lead_days=21, tail_days=7, evidence="prior", confidence=confidence,
        research_confidence=0.9, method="research-prior v1",
        provenance=prov(source="research-prior", licence="derived"),
        magnitude=Magnitude(point=0.10, low=0.05, high=0.15),
        citations=[Citation(source="trade-report", quality=0.7)], status=status)


def unknown_read(category="oral_care_brush", region="IN-MH", signal_id="diwali-2026") -> ImpactRead:
    return ImpactRead(
        signal_id=signal_id, signal_type="calendar", region_key=region, category=category,
        direction="neutral", lead_days=21, tail_days=7, evidence="unknown", confidence=0.0,
        method="research-prior v1", provenance=prov(source="research-prior", licence="derived"),
        status="unknown")


class FakeLlmClient:
    """A deterministic LLM stand-in for the prior-builder tests."""

    def __init__(self, available: bool, runs: Optional[List[RawPrior]] = None) -> None:
        self._available = available
        self._runs = runs or []

    def available(self) -> bool:
        return self._available

    def propose_prior(self, category, signal_id, region_key, runs):
        return list(self._runs)


class InMemoryDemandProvider:
    def __init__(self, rows: List[dict]) -> None:
        self._rows = rows

    def weekly_demand(self, company_key: str) -> List[dict]:
        return list(self._rows)
