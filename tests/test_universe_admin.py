import csv

import pytest

from issuer_opportunity_screener.pipeline import run_pipeline
from issuer_opportunity_screener.scoring import score_snapshot
from issuer_opportunity_screener.snapshots import load_snapshot
from issuer_opportunity_screener.sources.fixture import FixtureSource
from issuer_opportunity_screener.universe import UniverseError, load_universe
from issuer_opportunity_screener.universe_admin import (
    append_issuer,
    quarantine_unscored,
    restore_issuer,
    unscored_reasons,
)

HEADER = "issuer,ticker,basket,country,sector,recognition_score,internal_rating,equity_ticker,cds_ticker\n"


@pytest.fixture()
def universe_path(tmp_path):
    path = tmp_path / "universe.csv"
    path.write_text(
        HEADER + "".join(f"Issuer {i},TICK{i},Brazil,Brazil,Energy,80,,,\n" for i in range(12)),
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def snap(universe_path, tmp_path):
    directory = run_pipeline(universe_path, FixtureSource(), tmp_path / "snapshots")
    return load_snapshot(directory)


def test_append_issuer_validates_and_appends(universe_path):
    append_issuer(universe_path, {
        "issuer": "New Co", "ticker": "NEWCO", "basket": "Brazil",
        "country": "Brazil", "sector": "Energy", "recognition_score": 65,
        "equity_ticker": "NEWCO BZ Equity",
    })
    issuers = load_universe(universe_path)
    added = next(i for i in issuers if i.ticker == "NEWCO")
    assert added.equity_ticker == "NEWCO BZ Equity"

    with pytest.raises(UniverseError, match="duplicate ticker"):
        append_issuer(universe_path, {
            "issuer": "Dupe", "ticker": "NEWCO", "basket": "Brazil",
            "country": "Brazil", "sector": "Energy", "recognition_score": 50,
        })
    # failed append must not corrupt the file
    assert len(load_universe(universe_path)) == 13


def test_unscored_reasons_cover_failures_and_missing_spreads(snap):
    reasons = unscored_reasons(snap, score_snapshot(snap))
    assert set(reasons) == {"TICK4", "TICK10"}  # fixture roles idx % 6 == 4
    assert "fetch failed" in reasons["TICK4"]


def test_quarantine_and_restore_roundtrip(universe_path, snap, tmp_path):
    quarantine_path = tmp_path / "universe_quarantine.csv"
    moved = quarantine_unscored(universe_path, quarantine_path, snap, score_snapshot(snap))
    assert sorted(moved) == ["TICK10", "TICK4"]

    remaining = {i.ticker for i in load_universe(universe_path)}
    assert "TICK4" not in remaining and "TICK10" not in remaining and len(remaining) == 10

    with open(quarantine_path, newline="", encoding="utf-8") as f:
        quarantined = {row["ticker"]: row for row in csv.DictReader(f)}
    assert quarantined["TICK4"]["quarantine_reason"].startswith("fetch failed")
    assert quarantined["TICK4"]["quarantined_at"] == snap.manifest["as_of"]

    restore_issuer(universe_path, quarantine_path, "TICK4")
    assert "TICK4" in {i.ticker for i in load_universe(universe_path)}
    with open(quarantine_path, newline="", encoding="utf-8") as f:
        assert {row["ticker"] for row in csv.DictReader(f)} == {"TICK10"}

    with pytest.raises(ValueError, match="not in the quarantine file"):
        restore_issuer(universe_path, quarantine_path, "TICK4")


def test_auto_quarantine_env_flag(universe_path, tmp_path, monkeypatch):
    monkeypatch.setenv("IOS_AUTO_QUARANTINE", "1")
    # fixture source is never auto-quarantined (source gate protects dev data)
    run_pipeline(universe_path, FixtureSource(), tmp_path / "snaps2")
    assert len(load_universe(universe_path)) == 12
