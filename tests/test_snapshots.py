import pytest

from issuer_opportunity_screener.snapshots import (
    latest,
    list_snapshots,
    load_snapshot,
    write_snapshot,
)
from issuer_opportunity_screener.sources.fixture import FixtureSource
from test_fixture_source import make_universe


@pytest.fixture()
def universe():
    return make_universe(12)


@pytest.fixture()
def result(universe):
    return FixtureSource().fetch(universe)


def test_write_and_load_roundtrip(tmp_path, universe, result):
    snap_dir = write_snapshot(tmp_path, universe, result)
    assert snap_dir.name == "2026-07-15T120000"
    snap = load_snapshot(snap_dir)

    assert len(snap.frame) == 12  # failed issuer still has a row
    failed = snap.frame[snap.frame.ticker == "TICK4"].iloc[0]
    assert failed.isna()["cds_5y_bps"]

    assert set(snap.history.columns) == {"ticker", "date", "spread_bps", "instrument"}
    assert snap.manifest["source"] == "fixture"
    assert snap.manifest["partial"] is True
    assert snap.manifest["failures"] == {
        "TICK4": "fixture: simulated reference-data failure",
        "TICK10": "fixture: simulated reference-data failure",
    }
    assert snap.manifest["issuer_count"] == 12
    assert snap.manifest["fetched_count"] == 10
    assert snap.manifest["brazil"]["cds_5y_bps"] == 180.0
    assert 0 < snap.manifest["coverage"]["cds_5y_bps"] < 1


def test_append_only(tmp_path, universe, result):
    write_snapshot(tmp_path, universe, result)
    with pytest.raises(FileExistsError):
        write_snapshot(tmp_path, universe, result)


def test_latest_and_list(tmp_path, universe, result):
    assert latest(tmp_path) is None
    d1 = write_snapshot(tmp_path, universe, result)
    assert list_snapshots(tmp_path) == [d1]
    assert latest(tmp_path) == d1


def test_quality_notes_joined(tmp_path, universe, result):
    snap = load_snapshot(write_snapshot(tmp_path, universe, result))
    row = snap.frame[snap.frame.ticker == "TICK1"].iloc[0]
    assert "no liquid CDS quote" in row.quality_notes


def test_manifest_brazil_carries_bond_and_ratings(tmp_path, universe, result):
    snap = load_snapshot(write_snapshot(tmp_path, universe, result))
    brazil = snap.manifest["brazil"]
    assert brazil["bond_security"] == "BRAZIL 4.75 06/15/31 Govt"
    assert brazil["ratings"] == {"sp": "BB", "moody": "Ba2", "fitch": "BB"}
