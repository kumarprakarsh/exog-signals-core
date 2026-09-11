from __future__ import annotations

from exog_signals.infrastructure.store import SqliteStore
from conftest import NOW


def test_feed_status_upsert_and_transition():
    s = SqliteStore(":memory:")
    s.upsert_feed_status({"feed": "signals_weather", "status": "PRESENT", "as_of": NOW.isoformat(),
                          "rows": 10, "source": "open-meteo", "updated_at": NOW.isoformat()})
    assert s.get_feed_statuses()[0]["status"] == "PRESENT"
    s.upsert_feed_status({"feed": "signals_weather", "status": "DEGRADED", "as_of": NOW.isoformat(),
                          "rows": 10, "source": "open-meteo", "updated_at": NOW.isoformat()})
    rows = s.get_feed_statuses()
    assert len(rows) == 1 and rows[0]["status"] == "DEGRADED"  # transition, not a duplicate


def test_signal_features_filter_and_idempotent():
    s = SqliteStore(":memory:")
    rows = [
        {"feed": "signals_festival", "region_key": "IN-MH", "iso_week": "2026-W44",
         "values": {"fest_is_lead_window": 1}, "source": "holidays-py", "as_of": NOW.isoformat()},
        {"feed": "signals_festival", "region_key": "IN-KL", "iso_week": "2026-W44",
         "values": {"fest_is_lead_window": 0}, "source": "holidays-py", "as_of": NOW.isoformat()},
    ]
    assert s.upsert_signal_features(rows) == 2
    assert s.upsert_signal_features(rows) == 2  # re-upsert same keys → still 2 rows total
    got = s.get_signal_features("signals_festival", ["IN-MH"])
    assert len(got) == 1 and got[0]["region_key"] == "IN-MH"
    assert got[0]["values"]["fest_is_lead_window"] == 1
    all_rows = s.get_signal_features("signals_festival", ["IN-MH", "IN-KL"])
    assert len(all_rows) == 2


def test_prior_queue_roundtrip():
    s = SqliteStore(":memory:")
    s.upsert_prior({"id": "p1", "category": "c", "signal_type": "calendar", "signal_id": "diwali-2026",
                    "region_key": "IN-MH", "direction": "lift", "band": [0.05, 0.15], "lead_days": 21,
                    "tail_days": 7, "research_confidence": 0.6, "citations": [{"source": "x", "quality": 0.7}],
                    "status": "pending_review"})
    assert len(s.list_priors(status="pending_review")) == 1
    s.set_prior_status("p1", "accepted_review", "prakarsh")
    assert s.list_priors(status="pending_review") == []
    accepted = s.list_priors(status="accepted_review")
    assert accepted[0]["reviewed_by"] == "prakarsh" and accepted[0]["band"] == [0.05, 0.15]


def test_profile_roundtrip():
    s = SqliteStore(":memory:")
    s.upsert_profile({"company_key": "colgate-in", "display_name": "Colgate", "category_mix": {"a": 1.0},
                      "taxonomy": "ars:M10", "geographies": ["IN"], "evidence": "measured",
                      "updated_at": NOW.isoformat()})
    p = s.get_profile("colgate-in")
    assert p["category_mix"] == {"a": 1.0} and p["evidence"] == "measured"
    assert s.get_profile("nope") is None
