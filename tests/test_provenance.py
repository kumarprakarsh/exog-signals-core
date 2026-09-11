from __future__ import annotations

from datetime import timedelta

from exog_signals.application.provenance import age_hours, freshness_status, is_stale, stamp
from conftest import NOW


def test_is_stale_boundary_both_sides():
    assert is_stale(NOW - timedelta(hours=24), NOW, max_age_hours=24) is False   # exactly at threshold
    assert is_stale(NOW - timedelta(hours=24, minutes=1), NOW, max_age_hours=24) is True


def test_freshness_status_present_degraded_absent():
    assert freshness_status(NOW - timedelta(hours=1), NOW, cadence_hours=24) == "PRESENT"
    assert freshness_status(NOW - timedelta(hours=30), NOW, cadence_hours=24, grace_hours=2) == "DEGRADED"
    assert freshness_status(NOW - timedelta(days=10), NOW, cadence_hours=24, absent_after_hours=168) == "ABSENT"


def test_stamp_builds_provenance():
    p = stamp("open-meteo-selfhost", NOW, NOW, "AGPL-selfhost")
    assert p.source == "open-meteo-selfhost" and p.licence == "AGPL-selfhost"
    assert round(age_hours(NOW - timedelta(hours=3), NOW), 3) == 3.0
