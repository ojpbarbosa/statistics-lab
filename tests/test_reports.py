import datetime as dt

from issuer_opportunity_screener.reports import build_report
from test_insights import make_snapshot


def test_report_sections_and_values(tmp_path):
    then = make_snapshot(tmp_path, dt.datetime(2026, 7, 9, 12, 0), {"TIGHT": 400.0, "WIDE": 200.0}, "then")
    now = make_snapshot(tmp_path, dt.datetime(2026, 7, 16, 12, 0), {"TIGHT": 300.0, "WIDE": 260.0}, "now")

    report = build_report(now, then)
    assert "# Issuer Opportunity Screener: snapshot report" in report
    assert "## Screening summary" in report
    assert "## Viability and edge cases" in report
    assert "## Movers vs 2026-07-09" in report
    assert "TIGHT" in report and "-100" in report
    assert "## Data quality" in report
    assert "## Method and caveats" in report


def test_report_without_baseline(tmp_path):
    snap = make_snapshot(tmp_path, dt.datetime(2026, 7, 16, 12, 0), {"ONLY": 250.0}, "solo")
    report = build_report(snap)
    assert "Movers" not in report
    assert "ONLY" in report
