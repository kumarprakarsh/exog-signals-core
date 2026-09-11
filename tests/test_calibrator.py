from __future__ import annotations

import pytest

from exog_signals.application.calibrator import (
    CsvDemandHistoryProvider, DEFAULT_BAR, MeasuredCalibrator, anomaly_regression, clears_bar,
    matched_baseline_uplift)
from exog_signals.domain.errors import ConstructError
from conftest import InMemoryDemandProvider, NOW


def test_matched_baseline_uplift_recovers_a_known_lift():
    stat = matched_baseline_uplift([115, 115, 115], [100, 100, 100])
    assert abs(stat["point"] - 0.15) < 1e-9 and stat["events"] == 3
    assert stat["low"] - 1e-9 <= stat["point"] <= stat["high"] + 1e-9  # CI brackets the point
    assert clears_bar(stat, DEFAULT_BAR) is True


def test_matched_baseline_noise_does_not_clear_the_bar():
    stat = matched_baseline_uplift([110, 90, 105], [100, 100, 100])  # ~0 mean, CI spans 0
    assert clears_bar(stat, DEFAULT_BAR) is False


def test_anomaly_regression_recovers_slope():
    zs = [-2, -1, 0, 1, 2, -1, 1, 0]
    units = [100 * (1 + 0.1 * z) for z in zs]
    stat = anomaly_regression(units, zs)
    assert abs(stat["point"] - 0.1) < 1e-6 and stat["events"] == 6
    assert clears_bar(stat, DEFAULT_BAR) is True


def test_calibrate_calendar_end_to_end_produces_a_measured_read():
    weeks = {"e1a": 115, "e1b": 115, "b1a": 100, "b1b": 100,
             "e2a": 115, "e2b": 115, "b2a": 100, "b2b": 100}
    rows = [{"category": "oral_care_giftpack", "region_key": "IN-MH", "iso_week": w, "units": u,
             "construct": "CONSUMPTION"} for w, u in weeks.items()]
    provider = InMemoryDemandProvider(rows)
    event_index = {"diwali": {"type": "calendar", "lead_days": 21, "tail_days": 7, "years": 2, "events": [
        {"event_weeks": ["e1a", "e1b"], "baseline_weeks": ["b1a", "b1b"]},
        {"event_weeks": ["e2a", "e2b"], "baseline_weeks": ["b2a", "b2b"]}]}}
    reads = MeasuredCalibrator().calibrate_calendar("colgate-in", provider, event_index, DEFAULT_BAR, NOW)
    assert len(reads) == 1
    r = reads[0]
    assert r.evidence == "measured" and r.direction == "lift"
    assert abs(r.magnitude.point - 0.15) < 1e-9 and r.sample.events_observed == 2


def test_csv_provider_refuses_non_consumption_construct(tmp_path):
    p = tmp_path / "demand.csv"
    p.write_text("category,region_key,iso_week,units,construct\nc,IN-MH,2026-W44,100,ORDER\n")
    with pytest.raises(ConstructError):
        CsvDemandHistoryProvider(str(p)).weekly_demand("colgate-in")


def test_csv_provider_accepts_consumption(tmp_path):
    p = tmp_path / "demand.csv"
    p.write_text("category,region_key,iso_week,units,construct\nc,IN-MH,2026-W44,100,CONSUMPTION\n")
    rows = CsvDemandHistoryProvider(str(p)).weekly_demand("colgate-in")
    assert rows[0]["units"] == 100.0 and rows[0]["construct"] == "CONSUMPTION"
