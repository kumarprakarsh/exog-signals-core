"""FR-SPINE.9 — the impact composer. ``impact(company) = Σ_category weight · elasticity`` (D-EXOG-1).

Rules that keep it honest:
* a composed read carries the **weakest** evidence among the categories that actually contribute an
  effect (unknown < prior < measured) — a measured + prior mix composes to ``prior``;
* a composed **number** (magnitude) is emitted **only** when every contributor is ``measured``;
  otherwise magnitude is ``None`` and only the direction is given;
* a ``neutral`` category contributes 0.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ..domain.types import Citation, ImpactRead, Magnitude, Provenance, Sample, PRIOR_CONFIDENCE_CAP

_RANK = {"unknown": 0, "prior": 1, "measured": 2}
_NAME = {v: k for k, v in _RANK.items()}


def _signed(read: ImpactRead) -> Optional[float]:
    """A category's signed estimate: measured point, or prior band midpoint; None if not estimable."""
    if read.magnitude is None:
        return None
    mid = read.magnitude.point
    return mid if read.direction == "lift" else -mid


class ImpactComposer:
    def compose(self, profile, reads: Dict[str, ImpactRead], signal_type: str, signal_id: str,
                region_key: str, lead_days: int, tail_days: int, now: datetime) -> ImpactRead:
        prov = Provenance(source="composed", as_of=now, fetched_at=now, licence="derived")
        base = dict(signal_id=signal_id, signal_type=signal_type, region_key=region_key,
                    category="__company__", lead_days=lead_days, tail_days=tail_days, provenance=prov,
                    method="impact-composer v1")

        contributors: List[Tuple[float, ImpactRead]] = [
            (w, reads[cat]) for cat, w in profile.category_mix.items() if w > 0 and cat in reads]
        effective = [(w, r) for (w, r) in contributors if r.direction != "neutral"]

        if not effective:
            return ImpactRead(direction="neutral", evidence="unknown", confidence=0.0, status="unknown", **base)

        # single-category shortcut (AC1): 100% one category → return that category's read unchanged.
        total_w = sum(w for w, _ in contributors)
        if len(effective) == 1 and abs(effective[0][0] - total_w) < 1e-9:
            return effective[0][1]

        weakest = min(_RANK[r.evidence] for _, r in effective)
        evidence = _NAME[weakest]
        wsum = sum(w for w, _ in effective) or 1.0
        signed = sum(w * (_signed(r) or 0.0) for w, r in effective) / wsum
        direction = "lift" if signed > 0 else "dip" if signed < 0 else "neutral"

        if evidence == "measured":
            lo = sum(w * (min(abs(r.magnitude.low), abs(r.magnitude.high))) for w, r in effective) / wsum
            hi = sum(w * (max(abs(r.magnitude.low), abs(r.magnitude.high))) for w, r in effective) / wsum
            mag = Magnitude(point=abs(signed), low=min(lo, hi, abs(signed)), high=max(lo, hi, abs(signed)))
            sample = Sample(years=min(r.sample.years for _, r in effective),
                            n_obs=sum(r.sample.n_obs for _, r in effective),
                            events_observed=min(r.sample.events_observed for _, r in effective))
            return ImpactRead(direction=direction, evidence="measured",
                              confidence=min(r.confidence for _, r in effective), magnitude=mag,
                              sample=sample, status="measured", **base)

        if evidence == "prior":
            citations: List[Citation] = [c for _, r in effective if r.evidence == "prior" for c in r.citations]
            if not citations:  # defensive — a prior contributor always has citations by invariant
                citations = [Citation(source="composed-from-priors", quality=0.5)]
            conf = min(min(r.confidence for _, r in effective), PRIOR_CONFIDENCE_CAP)
            if direction == "neutral":
                return ImpactRead(direction="neutral", evidence="unknown", confidence=0.0,
                                  status="unknown", **base)
            return ImpactRead(direction=direction, evidence="prior", confidence=conf,
                              citations=citations, status="accepted_review", **base)

        return ImpactRead(direction="neutral", evidence="unknown", confidence=0.0, status="unknown", **base)
