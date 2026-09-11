"""Typed domain errors. Every failure a caller must branch on has its own class — never a bare
string or a silent None (D-ENG: fail loud, never guess)."""
from __future__ import annotations


class ExogError(Exception):
    """Base for every exog-signals domain error."""


class InvariantError(ExogError):
    """A domain object was constructed in a state the honesty model forbids
    (e.g. a `measured` ImpactRead with no confidence interval)."""


class UnresolvedRegion(ExogError):
    """A region input could not be resolved to a canonical RegionKey — never guessed."""


class RegionTooCoarse(ExogError):
    """A country-level region was given where a sub-country region is required (weather).
    Surfaces as HTTP 422 REGION_TOO_COARSE."""


class UnknownCountry(ExogError):
    """A calendar was requested for a country with no adapter/seed — a typed error, not an empty
    success."""


class SourceUnavailable(ExogError):
    """Every ranked source for a region failed or is disabled; the caller decides how to degrade."""


class ConstructError(ExogError):
    """A demand series is not offtake/consumption (e.g. it is tagged ORDER or INVOICE). The measured
    calibrator refuses it — orders/invoices are not demand (§3 construct-validity rule 1)."""
