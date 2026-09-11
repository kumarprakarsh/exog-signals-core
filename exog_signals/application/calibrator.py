"""FR-SPINE.8 — the measured-lift calibrator (pure functions) + the DemandHistoryProvider seam.

``measured`` is the only evidence class that carries a number, and it comes *only* from a company's
own demand history, under a **pre-registered bar** (CI excludes 0 AND |effect| >= margin AND enough
events). The math is stdlib-pure (DEVIATIONS.md: Polars is an optional fast-path). The demand series
must be **consumption/offtake**, never orders or invoices (§3 construct-validity rule 1) — the
provider enforces that."""
from __future__ import annotations

import csv
import math
from datetime import datetime
from statistics import fmean, pstdev
from typing import Dict, List, Optional, Protocol, Sequence

from ..domain.errors import ConstructError
from ..domain.types import ImpactRead, Magnitude, Provenance, Sample

_ALLOWED_CONSTRUCTS = {"CONSUMPTION", "OFFTAKE", "SECONDARY_SELLOUT"}

# ── the pre-registered bar (locked in config BEFORE a run — validation-preregister discipline) ────
DEFAULT_BAR = {"margin": 0.05, "min_events": 2}


def _se(values: Sequence[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    return pstdev(values) / math.sqrt(n)  # population sd / sqrt(n): 0 when all samples identical


def matched_baseline_uplift(event_means: Sequence[float], baseline_means: Sequence[float]) -> dict:
    """Per-event relative uplift = event_mean / baseline_mean − 1; point = mean of per-event uplifts,
    95% CI = point ± 1.96·SE. Needs ≥ 2 events. Deterministic (no bootstrap)."""
    if len(event_means) != len(baseline_means):
        raise ValueError("event_means and baseline_means must align per event")
    ratios = []
    for e, b in zip(event_means, baseline_means):
        if b <= 0:
            continue
        ratios.append(e / b - 1.0)
    k = len(ratios)
    if k == 0:
        return {"point": 0.0, "low": 0.0, "high": 0.0, "events": 0}
    point = fmean(ratios)
    se = _se(ratios)
    return {"point": point, "low": point - 1.96 * se, "high": point + 1.96 * se, "events": k}


def anomaly_regression(units: Sequence[float], zscores: Sequence[float]) -> dict:
    """OLS of demand on an anomaly z-score; effect is the per-+1σ change as a fraction of mean demand.
    95% CI from the slope standard error. ``events`` = weeks with |z| >= 1."""
    n = len(units)
    if n != len(zscores) or n < 3:
        return {"point": 0.0, "low": 0.0, "high": 0.0, "events": 0}
    zbar = fmean(zscores)
    ybar = fmean(units)
    sxx = sum((z - zbar) ** 2 for z in zscores)
    if sxx == 0 or ybar == 0:
        return {"point": 0.0, "low": 0.0, "high": 0.0, "events": 0}
    sxy = sum((z - zbar) * (u - ybar) for z, u in zip(zscores, units))
    slope = sxy / sxx
    resid = [u - (ybar + slope * (z - zbar)) for u, z in zip(units, zscores)]
    dof = n - 2
    s2 = sum(r * r for r in resid) / dof if dof > 0 else 0.0
    se_slope = math.sqrt(s2 / sxx) if sxx > 0 else 0.0
    frac = slope / ybar
    frac_se = se_slope / ybar
    events = sum(1 for z in zscores if abs(z) >= 1.0)
    return {"point": frac, "low": frac - 1.96 * frac_se, "high": frac + 1.96 * frac_se, "events": events}


def clears_bar(stat: dict, bar: dict) -> bool:
    """The pre-registered decision: CI excludes 0 AND |point| >= margin AND enough events."""
    excludes_zero = stat["low"] > 0 or stat["high"] < 0
    return excludes_zero and abs(stat["point"]) >= bar["margin"] and stat["events"] >= bar["min_events"]


def to_measured_read(category: str, signal_type: str, signal_id: str, region_key: str,
                     lead_days: int, tail_days: int, stat: dict, years: int, n_obs: int,
                     method: str, now: datetime, source: str) -> ImpactRead:
    """Assemble a ``measured`` ImpactRead when the bar is cleared; a magnitude + sample are mandatory
    (the invariant enforces it)."""
    point = stat["point"]
    lo, hi = sorted((stat["low"], stat["high"]))
    direction = "lift" if point > 0 else "dip"
    mag = Magnitude(point=abs(point), low=min(abs(lo), abs(hi)), high=max(abs(lo), abs(hi)))
    prov = Provenance(source=source, as_of=now, fetched_at=now, licence="derived")
    return ImpactRead(
        signal_id=signal_id, signal_type=signal_type, region_key=region_key, category=category,
        direction=direction, lead_days=lead_days, tail_days=tail_days, evidence="measured",
        confidence=0.8, method=method, provenance=prov, magnitude=mag,
        sample=Sample(years=years, n_obs=n_obs, events_observed=stat["events"]), status="measured")


class DemandHistoryProvider(Protocol):
    def weekly_demand(self, company_key: str) -> List[dict]:
        """Rows: {category, region_key, iso_week, units, construct}. Construct must be consumption."""
        ...


class CsvDemandHistoryProvider:
    """Reference DemandHistoryProvider over a CSV — so anyone can run the measured layer on their own
    sales with zero infrastructure (D-EXOG-2). Refuses non-consumption constructs (ConstructError)."""

    def __init__(self, path: str) -> None:
        self._path = path

    def weekly_demand(self, company_key: str) -> List[dict]:
        rows = []
        with open(self._path, newline="") as fh:
            for r in csv.DictReader(fh):
                construct = (r.get("construct") or "CONSUMPTION").upper()
                if construct not in _ALLOWED_CONSTRUCTS:
                    raise ConstructError(
                        f"demand construct {construct!r} is not consumption/offtake — orders/invoices "
                        "are not demand (§3 rule 1)")
                rows.append({"category": r["category"], "region_key": r["region_key"],
                             "iso_week": r["iso_week"], "units": float(r["units"]), "construct": construct})
        return rows


class MeasuredCalibrator:
    """Calendar matched-baseline calibration over a provider's consumption series. (Weather anomaly
    calibration uses ``anomaly_regression`` directly, wired by the weather agent.)"""

    def calibrate_calendar(self, company_key: str, provider: DemandHistoryProvider,
                           event_index: Dict[str, dict], bar: dict, now: datetime) -> List[ImpactRead]:
        rows = provider.weekly_demand(company_key)
        by_scope: Dict[tuple, Dict[str, float]] = {}
        for r in rows:
            by_scope.setdefault((r["category"], r["region_key"]), {})[r["iso_week"]] = r["units"]

        out: List[ImpactRead] = []
        for (category, region_key), units_by_week in by_scope.items():
            for signal_id, spec in event_index.items():
                if spec.get("type") != "calendar":
                    continue
                ev_weeks = [units_by_week[w] for ev in spec["events"] for w in ev["event_weeks"]
                            if w in units_by_week]
                base_means, ev_means = [], []
                for ev in spec["events"]:
                    e = [units_by_week[w] for w in ev["event_weeks"] if w in units_by_week]
                    b = [units_by_week[w] for w in ev["baseline_weeks"] if w in units_by_week]
                    if e and b:
                        ev_means.append(fmean(e))
                        base_means.append(fmean(b))
                if len(ev_means) < bar["min_events"]:
                    continue
                stat = matched_baseline_uplift(ev_means, base_means)
                if clears_bar(stat, bar):
                    out.append(to_measured_read(
                        category, "calendar", signal_id, region_key, spec.get("lead_days", 21),
                        spec.get("tail_days", 7), stat, years=spec.get("years", len(ev_means)),
                        n_obs=len(ev_weeks), method="matched-baseline-uplift v1", now=now,
                        source=f"demand-history/{company_key}"))
        return out
