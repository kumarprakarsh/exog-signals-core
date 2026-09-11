"""FR-SPINE.10 — the prior-calibration report (D-EXOG-4 guardrail 3): keep score on the auto-accept
lane. Compares auto-accepted priors against the measured layer; if they are contradicted too often
the threshold is not calibrated. The report only *recommends* — it never self-applies (a human
raises the bar)."""
from __future__ import annotations

import math
from datetime import datetime
from typing import List

from ..domain.types import ImpactRead

CONTRADICTION_LIMIT = 0.20


def _key(r: ImpactRead) -> tuple:
    return (r.category, r.signal_type, r.signal_id, r.region_key)


def run(company_key: str, auto_priors: List[ImpactRead], measured: List[ImpactRead],
        now: datetime, spot_fraction: float = 0.15) -> dict:
    measured_dir = {_key(m): m.direction for m in measured}
    autos = [p for p in auto_priors if p.status == "accepted_auto" and p.evidence == "prior"]

    contradicted = 0
    contradictions = []
    for p in autos:
        md = measured_dir.get(_key(p))
        if md is not None and md != p.direction:
            contradicted += 1
            contradictions.append({"category": p.category, "signal_id": p.signal_id,
                                   "prior": p.direction, "measured": md})

    n = len(autos)
    rate = (contradicted / n) if n else 0.0
    spot_checked = math.ceil(spot_fraction * n) if n else 0
    recommendation = "raise_threshold" if rate > CONTRADICTION_LIMIT else "hold"

    return {
        "company_key": company_key,
        "run_at": now.isoformat(),
        "auto_accepted": n,
        "contradicted": contradicted,
        "rate": round(rate, 4),
        "spot_checked": spot_checked,
        "recommendation": recommendation,
        "contradictions": contradictions,
        "note": "recommendation only — a human raises the threshold; the report never self-applies",
    }
