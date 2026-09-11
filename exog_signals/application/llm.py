"""The LLM seam for research-backed priors (D-EXOG-4). The core never depends on a live model: the
default ``NullLlmClient`` reports unavailable, and the prior builder then returns ``unknown`` with a
``skipped: no provider`` note. A real client (Anthropic, behind the ``llm`` extra) implements the
same protocol. NOTHING on the signal/feature hot path imports this (NFR-SPINE.2)."""
from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable


class RawPrior:
    """One research run's proposal for a (category, signal, region) prior. Deliberately plain (not a
    domain type) — the PriorBuilder scores and validates a set of these into an ImpactRead."""

    def __init__(self, direction: str, band: Optional[tuple], citations: List[dict],
                 claim_has_magnitude: bool) -> None:
        self.direction = direction                      # "lift" | "dip" | "neutral"
        self.band = band                                # (low, high) or None
        self.citations = citations                      # [{"source":..., "quality":0..1, "url":...}]
        self.claim_has_magnitude = claim_has_magnitude  # True if the model asserted a specific number


@runtime_checkable
class LlmClient(Protocol):
    def available(self) -> bool: ...

    def propose_prior(self, category: str, signal_id: str, region_key: str, runs: int) -> List[RawPrior]:
        """Return ``runs`` independent proposals (for self-consistency scoring)."""
        ...


class NullLlmClient:
    """The zero-secrets default: no provider configured."""

    def available(self) -> bool:
        return False

    def propose_prior(self, category: str, signal_id: str, region_key: str, runs: int) -> List[RawPrior]:
        return []
