"""FR-SPINE.2 — the generic, region-aware ranked source registry both agents use.

Per region match, a ranked list of source adapters, each carrying ``licence`` / ``attribution`` /
``rate_limit`` / ``independent_model`` / ``enabled``. Resolution returns the enabled entries in rank
order; ``select_with_fallback`` tries them in order and records which served and which fell back — so
"the honest top-N for this region" is data, not a guess. A disabled entry (e.g. a scraper) is never
tried. An entry without a ``licence`` is refused at load time (D-EXOG-2)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ..domain.errors import InvariantError, SourceUnavailable
from ..domain.types import RegionKey


@dataclass(frozen=True)
class SourceEntry:
    name: str
    licence: str = ""  # default empty so an omitted licence fails as an InvariantError, not a TypeError
    attribution: Optional[str] = None
    rate_limit_per_min: Optional[int] = None
    independent_model: bool = True
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.name:
            raise InvariantError("SourceEntry.name is required")
        if not self.licence:
            raise InvariantError(f"SourceEntry {self.name!r} has no licence (D-EXOG-2: free/open, licence always known)")


@dataclass(frozen=True)
class MatchRule:
    country: str  # ISO-3166-1 or "*"
    sources: List[SourceEntry]


@dataclass
class FallbackReport:
    used: Optional[str] = None
    skipped_disabled: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)  # "name: reason"


class SourceRegistry:
    def __init__(self, rules: List[MatchRule]) -> None:
        self._rules = rules

    @classmethod
    def from_list(cls, spec: list) -> "SourceRegistry":
        rules = []
        for r in spec:
            match = r.get("match", {})
            entries = [SourceEntry(**s) for s in r.get("sources", [])]
            rules.append(MatchRule(country=match.get("country", "*"), sources=entries))
        return cls(rules)

    def resolve(self, region: RegionKey) -> List[SourceEntry]:
        """Ranked, enabled entries for this region: the country-specific rule if present, else the
        wildcard rule. Disabled entries are dropped here (never surfaced to the caller)."""
        specific = next((r for r in self._rules if r.country == region.country), None)
        wildcard = next((r for r in self._rules if r.country == "*"), None)
        rule = specific or wildcard
        if rule is None:
            return []
        return [e for e in rule.sources if e.enabled]

    def resolve_all(self, region: RegionKey) -> List[SourceEntry]:
        """Every entry incl. disabled — for reporting what was skipped."""
        specific = next((r for r in self._rules if r.country == region.country), None)
        wildcard = next((r for r in self._rules if r.country == "*"), None)
        rule = specific or wildcard
        return list(rule.sources) if rule else []


def select_with_fallback(entries: List[SourceEntry], try_fn: Callable[[SourceEntry], object]):
    """Try each enabled entry in rank order; return (result, report). ``try_fn`` may raise to signal a
    dead source — the next entry is tried. All failing raises SourceUnavailable (the caller degrades)."""
    report = FallbackReport()
    for e in entries:
        if not e.enabled:
            report.skipped_disabled.append(e.name)
            continue
        try:
            result = try_fn(e)
            if result is not None:
                report.used = e.name
                return result, report
            report.failed.append(f"{e.name}: returned no data")
        except Exception as exc:  # noqa: BLE001 — a dead source is expected; fall through to the next
            report.failed.append(f"{e.name}: {exc}")
    raise SourceUnavailable(f"all sources failed/empty: {report.failed}; skipped_disabled={report.skipped_disabled}")
