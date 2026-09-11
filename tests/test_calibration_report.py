from __future__ import annotations

from exog_signals.application import calibration_report
from conftest import measured_read, prior_read, NOW


def test_high_contradiction_recommends_raising_the_bar():
    autos = [prior_read(category=f"c{i}", direction="lift", signal_id=f"s{i}") for i in range(10)]
    # 3 of the 10 are contradicted by a measured dip
    measured = [measured_read(category=f"c{i}", direction="dip", signal_id=f"s{i}") for i in range(3)]
    rep = calibration_report.run("colgate-in", autos, measured, NOW)
    assert rep["auto_accepted"] == 10 and rep["contradicted"] == 3
    assert rep["rate"] == 0.3 and rep["recommendation"] == "raise_threshold"
    assert rep["spot_checked"] == 2  # ceil(0.15 * 10)


def test_no_contradiction_holds():
    autos = [prior_read(category=f"c{i}", direction="lift", signal_id=f"s{i}") for i in range(5)]
    measured = [measured_read(category=f"c{i}", direction="lift", signal_id=f"s{i}") for i in range(5)]
    rep = calibration_report.run("colgate-in", autos, measured, NOW)
    assert rep["contradicted"] == 0 and rep["recommendation"] == "hold"
    assert "never self-applies" in rep["note"]
