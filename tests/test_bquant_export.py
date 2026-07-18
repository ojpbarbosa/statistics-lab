import json

import pytest

from issuer_opportunity_screener.pipeline import run_pipeline
from issuer_opportunity_screener.scoring import score_snapshot
from issuer_opportunity_screener.snapshots import load_snapshot
from issuer_opportunity_screener.sources.bquant_export import BquantExportMissing, BquantExportSource
from test_fixture_source import make_universe


@pytest.fixture()
def export_dir(tmp_path):
    directory = tmp_path / "bquant_export"
    directory.mkdir()
    (directory / "meta.json").write_text(json.dumps({"as_of": "2026-07-16T09:30:00"}), encoding="utf-8")
    (directory / "issuers.csv").write_text(
        "ticker,cds_5y_bps,cds_security,bond_security,bond_z_spread_bps,bond_last_price,bond_maturity,bond_coupon,"
        "rating_moody,rating_sp,rating_fitch,rating_composite,equity_ticker,px_chg_3m_pct,px_chg_12m_pct,rec_balance\n"
        "TICK0,245.5,TICK0 CDS USD SR 5Y D14 Corp,TICK0 5.5 2031 Corp,260.0,97.25,2031-06-15,5.5,"
        "Ba1,BB+,BB+,BB+,TICK0 US Equity,4.2,-8.0,0.4\n"
        "TICK1,,,TICK1 6.0 2030 Corp,310.0,95.00,2030-03-01,6.0,"
        ",BB,,,TICK1 US Equity,,,\n",
        encoding="utf-8",
    )
    (directory / "history.csv").write_text(
        "ticker,date,spread_bps,instrument\n"
        + "".join(f"TICK0,2026-{month:02d}-01,{200 + month * 5}.0,cds\n" for month in range(1, 8)),
        encoding="utf-8",
    )
    (directory / "brazil.csv").write_text(
        "cds_5y_bps,z_spread_bps,rating_sp,bond_security\n123.0,,BB,BRAZIL 4.75 06/15/31 Govt\n",
        encoding="utf-8",
    )
    return directory


def test_export_ingestion_maps_fields(export_dir):
    universe = make_universe(3)  # TICK0..TICK2
    result = BquantExportSource(export_dir).fetch(universe)

    assert result.source == "bquant"
    assert result.as_of.isoformat() == "2026-07-16T09:30:00"
    assert result.brazil.cds_5y_bps == 123.0
    assert result.brazil.bond_security == "BRAZIL 4.75 06/15/31 Govt"

    by_ticker = {c.ticker: c for c in result.issuers}
    tick0 = by_ticker["TICK0"]
    assert tick0.cds_5y_bps == 245.5
    assert tick0.bond.z_spread_bps == 260.0
    assert tick0.ratings == {"moody": "Ba1", "sp": "BB+", "fitch": "BB+", "composite": "BB+"}

    tick1 = by_ticker["TICK1"]
    assert tick1.cds_5y_bps is None
    assert tick1.bond.security == "TICK1 6.0 2030 Corp"
    assert any("no CDS quote" in note for note in tick1.quality_notes)

    assert result.failures == {"TICK2": "not present in the BQuant export"}
    assert len(result.history) == 7


def test_export_flows_through_pipeline_and_scoring(export_dir, tmp_path):
    universe_path = tmp_path / "universe.csv"
    universe_path.write_text(
        "issuer,ticker,basket,country,sector,recognition_score,internal_rating,equity_ticker,cds_ticker\n"
        "Zero,TICK0,Brazil,Brazil,Energy,90,,,\n"
        "One,TICK1,Brazil,Brazil,Energy,80,,,\n",
        encoding="utf-8",
    )
    directory = run_pipeline(universe_path, BquantExportSource(export_dir), tmp_path / "snaps")
    snap = load_snapshot(directory)
    scores = score_snapshot(snap)
    assert {s.ticker for s in scores} == {"TICK0", "TICK1"}
    assert snap.manifest["brazil"]["cds_5y_bps"] == 123.0


def test_missing_export_raises_clear_error(tmp_path):
    with pytest.raises(BquantExportMissing, match="bquant_export.py"):
        BquantExportSource(tmp_path / "nowhere").fetch(make_universe(1))
