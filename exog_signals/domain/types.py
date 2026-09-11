"""The domain types + the honesty invariants (LLD §2).

These dataclasses are the reference-impl stand-in for the LLD's pydantic models (see DEVIATIONS.md):
same field names, same invariants, enforced in ``__post_init__``. The invariants are the whole point
of this project — they make it *impossible* to construct a fabricated impact number:

* ``evidence == "measured"``  <=>  a confidence interval AND a sample exist.
* ``evidence == "prior"``     =>   magnitude is None or a *band*, forecasting ``confidence`` <= 0.35,
                                   and at least one citation.
* ``evidence == "unknown"``   =>   ``direction == "neutral"`` and no magnitude.
* every emitted object carries a ``Provenance`` with a timezone-aware ``as_of``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from .errors import InvariantError

# ── controlled vocabularies ────────────────────────────────────────────────────────────────────
EVIDENCE = ("measured", "prior", "unknown")
DIRECTION = ("lift", "dip", "neutral")
SIGNAL_TYPE = ("calendar", "weather")
STATUS = ("accepted_auto", "accepted_review", "pending_review", "rejected", "measured", "unknown")
PROFILE_EVIDENCE = ("measured", "prior", "unknown")

#: A prior may inform the *narrative* and cold-start, but its influence on the forecast is capped
#: low — it never competes with a measured effect (D-EXOG-4 guardrail 2).
PRIOR_CONFIDENCE_CAP = 0.35


@dataclass(frozen=True)
class RegionKey:
    """The canonical join key ARS uses (LLD §2). ``key()`` is the string ARS stamps on staged rows:
    the ISO-3166-2 subdivision when present, else the country. ``grid_id`` is weather-only and
    internal (a 0.25° cell)."""
    country: str                       # ISO-3166-1 alpha-2, e.g. "IN"
    subdivision: Optional[str] = None  # ISO-3166-2, e.g. "IN-MH"; None = national
    grid_id: Optional[str] = None      # weather grid, e.g. "g:19.75:75.75"

    def key(self) -> str:
        return self.subdivision or self.country


def _require_tz_aware(dt: datetime, field_name: str) -> None:
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise InvariantError(f"{field_name} must be timezone-aware (D-ENG: date math is never naive/UTC-assumed)")


@dataclass(frozen=True)
class Provenance:
    """Where a row came from and *as of when* — stamped on every emitted object (FR-SPINE.3).

    ``as_of`` is the source's business time (never ``now()``); ``fetched_at`` is when we pulled it.
    A row that cannot say how old its data is cannot be constructed."""
    source: str
    as_of: datetime
    fetched_at: datetime
    licence: str
    attribution: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.source:
            raise InvariantError("Provenance.source is required")
        if not self.licence:
            raise InvariantError("Provenance.licence is required (D-EXOG-2: free/open, licence always known)")
        _require_tz_aware(self.as_of, "Provenance.as_of")
        _require_tz_aware(self.fetched_at, "Provenance.fetched_at")
        if self.as_of > self.fetched_at:
            raise InvariantError("Provenance.as_of cannot be after fetched_at (business time <= pull time)")


@dataclass(frozen=True)
class Magnitude:
    """A measured effect size, always with a confidence interval. ``point`` must lie within
    ``[low, high]`` and the band must be non-degenerate for a real measurement."""
    point: float
    low: float
    high: float
    unit: str = "fraction_vs_baseline"

    def __post_init__(self) -> None:
        if not (self.low <= self.point <= self.high):
            raise InvariantError(f"Magnitude point {self.point} must lie within [{self.low}, {self.high}]")

    @property
    def is_band(self) -> bool:
        return self.low < self.high


@dataclass(frozen=True)
class Sample:
    """The evidence base behind a measured effect."""
    years: int
    n_obs: int
    events_observed: int

    def __post_init__(self) -> None:
        if self.n_obs <= 0 or self.events_observed <= 0:
            raise InvariantError("Sample must have positive n_obs and events_observed")


@dataclass(frozen=True)
class Citation:
    """A source behind a prior. Priors must be cited; ``quality`` in [0, 1] feeds the earned score."""
    source: str
    url: Optional[str] = None
    quote: Optional[str] = None
    quality: float = 0.5

    def __post_init__(self) -> None:
        if not self.source:
            raise InvariantError("Citation.source is required")
        if not (0.0 <= self.quality <= 1.0):
            raise InvariantError("Citation.quality must be in [0, 1]")


@dataclass(frozen=True)
class ImpactRead:
    """How one signal moves one category's sales, for one region — labelled by evidence class.

    This is the object F-EXPLAIN renders and the composer combines. Its invariants are what stop a
    number from being presented as a measurement when it is only a guess."""
    signal_id: str
    signal_type: str
    region_key: str
    category: str
    direction: str
    lead_days: int
    tail_days: int
    evidence: str
    confidence: float
    method: str
    provenance: Provenance
    magnitude: Optional[Magnitude] = None
    sample: Optional[Sample] = None
    research_confidence: Optional[float] = None
    citations: List[Citation] = field(default_factory=list)
    status: str = "unknown"

    def __post_init__(self) -> None:
        if self.signal_type not in SIGNAL_TYPE:
            raise InvariantError(f"signal_type {self.signal_type!r} not in {SIGNAL_TYPE}")
        if self.direction not in DIRECTION:
            raise InvariantError(f"direction {self.direction!r} not in {DIRECTION}")
        if self.evidence not in EVIDENCE:
            raise InvariantError(f"evidence {self.evidence!r} not in {EVIDENCE}")
        if self.status not in STATUS:
            raise InvariantError(f"status {self.status!r} not in {STATUS}")
        if not (0.0 <= self.confidence <= 1.0):
            raise InvariantError("confidence must be in [0, 1]")

        if self.evidence == "measured":
            if self.magnitude is None or self.sample is None:
                raise InvariantError("a 'measured' read must carry both a magnitude (CI) and a sample")
        elif self.evidence == "prior":
            if self.magnitude is not None and not self.magnitude.is_band:
                raise InvariantError("a 'prior' magnitude must be a band (low < high), never a point estimate")
            if self.confidence > PRIOR_CONFIDENCE_CAP:
                raise InvariantError(
                    f"a 'prior' forecasting confidence must be <= {PRIOR_CONFIDENCE_CAP} "
                    "(D-EXOG-4: a prior never competes with a measured effect)")
            if not self.citations:
                raise InvariantError("a 'prior' must carry at least one citation (D-EXOG-4: cited, not guessed)")
        else:  # unknown
            if self.direction != "neutral":
                raise InvariantError("an 'unknown' read must be direction='neutral'")
            if self.magnitude is not None:
                raise InvariantError("an 'unknown' read must carry no magnitude")

        if self.research_confidence is not None and not (0.0 <= self.research_confidence <= 1.0):
            raise InvariantError("research_confidence must be in [0, 1]")


@dataclass(frozen=True)
class CompanyProfile:
    """A company resolved to a weighted bag of categories (D-EXOG-1). Elasticity is a property of a
    category, so this is what makes the agents generic: no ``if company == ...`` anywhere."""
    company_key: str
    display_name: str
    category_mix: dict  # category_id -> weight, Σ = 1
    taxonomy: str
    geographies: List[str]
    provenance: Provenance
    evidence: str = "prior"

    def __post_init__(self) -> None:
        if self.evidence not in PROFILE_EVIDENCE:
            raise InvariantError(f"profile evidence {self.evidence!r} not in {PROFILE_EVIDENCE}")
        if not self.category_mix:
            raise InvariantError("category_mix cannot be empty")
        total = sum(self.category_mix.values())
        if abs(total - 1.0) > 1e-6:
            raise InvariantError(f"category_mix weights must sum to 1.0 (got {total})")
        for cat, w in self.category_mix.items():
            if w < 0:
                raise InvariantError(f"category weight for {cat!r} is negative")
