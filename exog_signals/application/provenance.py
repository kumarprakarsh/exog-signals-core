"""FR-SPINE.3 — provenance stamping + feed staleness + the FeedStatusService.

Every emitted row is stamped with a ``Provenance`` (``source`` + ``as_of`` + ``fetched_at`` +
``licence``). Staleness is a pure comparison of ``as_of`` against ``now`` and a cadence; the
FeedStatusService records PRESENT / DEGRADED / ABSENT per feed (backed by the Store)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from ..domain.types import Provenance


def stamp(source: str, as_of: datetime, fetched_at: datetime, licence: str,
          attribution: Optional[str] = None) -> Provenance:
    return Provenance(source=source, as_of=as_of, fetched_at=fetched_at, licence=licence, attribution=attribution)


def age_hours(as_of: datetime, now: datetime) -> float:
    return (now - as_of).total_seconds() / 3600.0


def is_stale(as_of: datetime, now: datetime, max_age_hours: float) -> bool:
    """Strictly greater-than the threshold (the boundary is asserted both sides in tests)."""
    return age_hours(as_of, now) > max_age_hours


def freshness_status(as_of: datetime, now: datetime, cadence_hours: float,
                     grace_hours: float = 0.0, absent_after_hours: Optional[float] = None) -> str:
    """PRESENT within cadence+grace; ABSENT past ``absent_after_hours`` (if given); else DEGRADED."""
    age = age_hours(as_of, now)
    if absent_after_hours is not None and age > absent_after_hours:
        return "ABSENT"
    if age > cadence_hours + grace_hours:
        return "DEGRADED"
    return "PRESENT"


class FeedStatusService:
    """Records/reads per-feed status. Delegates persistence to the Store so the same rows drive the
    ARS-side readiness cards."""

    def __init__(self, store) -> None:
        self._store = store

    def upsert(self, feed: str, status: str, as_of: datetime, rows: int, source: str,
               updated_at: datetime) -> None:
        self._store.upsert_feed_status({
            "feed": feed, "status": status, "as_of": as_of.isoformat(),
            "rows": rows, "source": source, "updated_at": updated_at.isoformat(),
        })

    def all(self) -> List[dict]:
        return self._store.get_feed_statuses()
