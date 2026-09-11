"""FR-SPINE.6 — resolve a company to its category mix (D-EXOG-1). Provider order:
ArsProfileProvider (a tenant's own masters → measured mix) → ResearchProfileProvider (LLM, cited →
prior mix) → UNKNOWN. The company is *only ever* a weighted bag of categories here; elasticity lives
on the category, so there is no per-company branch anywhere downstream."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Protocol

from ..domain.types import CompanyProfile, Provenance


class ProfileProvider(Protocol):
    def get(self, company: str, now: datetime) -> Optional[CompanyProfile]: ...


class CompanyProfileService:
    def __init__(self, providers: List[ProfileProvider]) -> None:
        self._providers = providers

    def get(self, company: str, now: datetime) -> Optional[CompanyProfile]:
        for p in self._providers:
            profile = p.get(company, now)
            if profile is not None:
                return profile
        return None


class StaticArsProfileProvider:
    """Reference ArsProfileProvider: a tenant's category mix from its own masters (evidence=measured).
    In agent-ars this reads M01/M10 by revenue share; here it is seeded from a dict for the tests and
    the demo."""

    def __init__(self, profiles: dict) -> None:
        self._profiles = profiles  # company_key -> {display_name, category_mix, geographies}

    def get(self, company: str, now: datetime) -> Optional[CompanyProfile]:
        spec = self._profiles.get(company)
        if spec is None:
            return None
        prov = Provenance(source="ars-masters", as_of=now, fetched_at=now, licence="internal")
        return CompanyProfile(
            company_key=company, display_name=spec["display_name"], category_mix=spec["category_mix"],
            taxonomy="ars:M10", geographies=spec.get("geographies", []), provenance=prov, evidence="measured")


class NullResearchProfileProvider:
    """The zero-secrets fallback: no LLM configured → no researched profile (service returns None →
    UNKNOWN). A real ResearchProfileProvider (llm extra) returns an evidence='prior' profile."""

    def get(self, company: str, now: datetime) -> Optional[CompanyProfile]:
        return None
