"""FR-SPINE.7 — the research-prior builder with the 80%-earned-confidence auto-accept lane (D-EXOG-4).

An impact *prior* is a first educated guess before we can measure. It is produced by an LLM (or SME),
with citations, and:

* the confidence that decides auto-accept is **earned from evidence**, never self-reported:
  ``earned = 0.4·citation_score + 0.4·self_consistency + 0.2·claim_type_score``;
* **any specific magnitude claim is capped below 0.80** (``claim_type_score = 0`` and a hard cap) so a
  number always goes to a human;
* ``earned >= 0.80`` → ``accepted_auto``; otherwise ``pending_review``; no citations → ``rejected``;
* an auto-accepted prior is still ``evidence="prior"`` with forecasting confidence ≤ 0.35 — it can
  colour the narrative and cold-start, never inject lift into the forecast.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

from ..domain.types import Citation, ImpactRead, Magnitude, Provenance, PRIOR_CONFIDENCE_CAP
from .llm import LlmClient, RawPrior

AUTO_ACCEPT_THRESHOLD = 0.80
_MAGNITUDE_CAP = 0.79  # strictly below the threshold: a magnitude claim can never auto-accept


@dataclass(frozen=True)
class PriorScore:
    earned: float
    citation_score: float
    self_consistency: float
    claim_type_score: float
    modal_direction: Optional[str]
    claim_has_magnitude: bool
    decision: str  # accepted_auto | pending_review | rejected | unknown


def _citation_score(citations: List[dict]) -> float:
    if not citations:
        return 0.0
    return min(1.0, sum(float(c.get("quality", 0.5)) for c in citations) / 1.5)


def score_prior(runs: List[RawPrior], threshold: float = AUTO_ACCEPT_THRESHOLD) -> PriorScore:
    """Pure scoring over the independent research runs — the testable heart of the 80% lane."""
    if not runs:
        return PriorScore(0.0, 0.0, 0.0, 0.0, None, False, "unknown")

    # modal direction across runs; require a strict majority to have a usable direction
    counts = {}
    for r in runs:
        counts[r.direction] = counts.get(r.direction, 0) + 1
    modal, modal_n = max(counts.items(), key=lambda kv: kv[1])
    self_consistency = modal_n / len(runs)
    has_majority = modal_n * 2 > len(runs)

    agreeing = [r for r in runs if r.direction == modal]
    citations = [c for r in agreeing for c in r.citations]
    claim_has_magnitude = sum(1 for r in agreeing if r.claim_has_magnitude) * 2 >= len(agreeing) and any(
        r.claim_has_magnitude for r in agreeing)

    citation_score = _citation_score(citations)
    claim_type_score = 0.0 if claim_has_magnitude else 1.0
    earned = 0.4 * citation_score + 0.4 * self_consistency + 0.2 * claim_type_score
    if claim_has_magnitude:
        earned = min(earned, _MAGNITUDE_CAP)

    if not citations:
        decision = "rejected"
    elif not has_majority or modal == "neutral":
        decision = "unknown"
    elif earned >= threshold:
        decision = "accepted_auto"
    else:
        decision = "pending_review"

    return PriorScore(round(earned, 4), round(citation_score, 4), round(self_consistency, 4),
                      claim_type_score, modal if has_majority else None, claim_has_magnitude, decision)


def _agreeing_band(runs: List[RawPrior], direction: str) -> Optional[Tuple[float, float]]:
    bands = [r.band for r in runs if r.direction == direction and r.band is not None]
    if not bands:
        return None
    lo = min(b[0] for b in bands)
    hi = max(b[1] for b in bands)
    return (lo, hi) if lo < hi else (lo, hi + 1e-9)  # keep it a genuine band


class PriorBuilder:
    def __init__(self, llm: LlmClient, threshold: float = AUTO_ACCEPT_THRESHOLD, runs: int = 3) -> None:
        self._llm = llm
        self._threshold = threshold
        self._runs = runs

    def build(self, category: str, signal_type: str, signal_id: str, region_key: str,
              lead_days: int, tail_days: int, now: datetime) -> ImpactRead:
        prov = Provenance(source="research-prior", as_of=now, fetched_at=now, licence="derived",
                          attribution=None)
        base = dict(signal_id=signal_id, signal_type=signal_type, region_key=region_key,
                    category=category, lead_days=lead_days, tail_days=tail_days, provenance=prov)

        if not self._llm.available():
            return ImpactRead(direction="neutral", evidence="unknown", confidence=0.0,
                              method="research-prior v1 (skipped: no LLM provider)", status="unknown", **base)

        runs = self._llm.propose_prior(category, signal_id, region_key, self._runs)
        score = score_prior(runs, self._threshold)

        if score.decision in ("unknown", "rejected"):
            return ImpactRead(direction="neutral", evidence="unknown", confidence=0.0,
                              method="research-prior v1", status=score.decision, **base)

        band = _agreeing_band(runs, score.modal_direction)
        magnitude = Magnitude(point=(band[0] + band[1]) / 2, low=band[0], high=band[1]) if band else None
        citations = [Citation(source=c.get("source", "?"), url=c.get("url"), quote=c.get("quote"),
                              quality=float(c.get("quality", 0.5)))
                     for r in runs if r.direction == score.modal_direction for c in r.citations]
        return ImpactRead(
            direction=score.modal_direction, evidence="prior",
            confidence=round(score.earned * PRIOR_CONFIDENCE_CAP, 4),
            research_confidence=score.earned, magnitude=magnitude, citations=citations,
            method="research-prior v1", status=score.decision, **base)
