"""FR-SPINE.5 — the CLI (stdlib argparse; the LLD's typer is an optional swap). ``demo`` proves the
spine end-to-end on an in-memory store with zero secrets; ``feed-status`` and ``review`` operate the
prior queue."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from ..application.company_profile import CompanyProfileService, NullResearchProfileProvider, StaticArsProfileProvider
from ..application.provenance import FeedStatusService
from ..application.region_resolver import RegionResolver
from ..infrastructure.store import SqliteStore
from .tools import build_core_registry, to_jsonable

_DEMO_PROFILES = {
    "colgate-in": {
        "display_name": "Colgate (India)",
        "category_mix": {"oral_care_toothpaste": 0.7, "oral_care_brush": 0.2, "oral_care_giftpack": 0.1},
        "geographies": ["IN"],
    }
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _demo(_args) -> int:
    store = SqliteStore(":memory:")
    resolver = RegionResolver()
    profiles = CompanyProfileService([StaticArsProfileProvider(_DEMO_PROFILES), NullResearchProfileProvider()])
    feeds = FeedStatusService(store)
    now = _now()

    rk = resolver.resolve("Maharashtra")
    feeds.upsert("signals_festival", "PRESENT", now, rows=0, source="holidays-py", updated_at=now)
    feeds.upsert("signals_weather", "PRESENT", now, rows=0, source="open-meteo-selfhost", updated_at=now)

    reg = build_core_registry(store, resolver, profiles, _now)
    out = {
        "resolved_region": to_jsonable(rk),
        "company_profile": reg.call("company.get_profile", {"company": "colgate-in"}),
        "feed_status": reg.call("signals.feed_status", {}),
        "note": "spine demo — no secrets, in-memory sqlite; calendar/weather agents plug in on top",
    }
    print(json.dumps(out, indent=2))
    return 0


def _feed_status(_args) -> int:
    store = SqliteStore(_args.db)
    print(json.dumps(FeedStatusService(store).all(), indent=2))
    return 0


def _review(args) -> int:
    store = SqliteStore(args.db)
    if args.set_status:
        store.set_prior_status(args.prior_id, args.set_status, args.reviewer)
        print(json.dumps({"prior_id": args.prior_id, "status": args.set_status}, indent=2))
    else:
        print(json.dumps(store.list_priors(status="pending_review"), indent=2, default=str))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="exog", description="exog-signals-core CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Core-only: the agent composition (`agents-demo`) lives in each agent repo, which depends on this core.
    sub.add_parser("demo", help="run the core end-to-end on an in-memory store (no secrets)").set_defaults(fn=_demo)

    fs = sub.add_parser("feed-status", help="print feed_status rows")
    fs.add_argument("--db", default=":memory:")
    fs.set_defaults(fn=_feed_status)

    rv = sub.add_parser("review", help="list pending priors, or set a prior's status")
    rv.add_argument("--db", default=":memory:")
    rv.add_argument("--prior-id", dest="prior_id")
    rv.add_argument("--set-status", dest="set_status", choices=["accepted_review", "rejected"])
    rv.add_argument("--reviewer")
    rv.set_defaults(fn=_review)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
