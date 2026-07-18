import pytest

from issuer_opportunity_screener.pipeline import run_pipeline
from issuer_opportunity_screener.snapshots import load_snapshot
from issuer_opportunity_screener.sources.base import BloombergUnavailable
from issuer_opportunity_screener.sources.fixture import FixtureSource
from issuer_opportunity_screener.universe import UniverseError

VALID_CSV = (
    "issuer,ticker,basket,country,sector,recognition_score,internal_rating\n"
    "Petrobras,PETBRA,Brazil,Brazil,Energy,100,\n"
    "Vale,VALEBZ,Brazil,Brazil,Materials and Mining,100,\n"
)


def test_pipeline_end_to_end(tmp_path):
    universe_path = tmp_path / "universe.csv"
    universe_path.write_text(VALID_CSV, encoding="utf-8")
    snap_dir = run_pipeline(universe_path, FixtureSource(), tmp_path / "snapshots")
    snap = load_snapshot(snap_dir)
    assert list(snap.frame.ticker) == ["PETBRA", "VALEBZ"]
    assert snap.manifest["source"] == "fixture"


def test_pipeline_propagates_universe_error(tmp_path):
    universe_path = tmp_path / "universe.csv"
    universe_path.write_text(
        "issuer,ticker,basket,country,sector,recognition_score,internal_rating\n"
        "X,ABC,Nope,Brazil,Energy,50,\n",
        encoding="utf-8",
    )
    with pytest.raises(UniverseError):
        run_pipeline(universe_path, FixtureSource(), tmp_path / "snapshots")


class ExplodingSource:
    name = "exploding"

    def fetch(self, issuers):
        raise BloombergUnavailable("no session")


def test_pipeline_propagates_bloomberg_unavailable(tmp_path):
    universe_path = tmp_path / "universe.csv"
    universe_path.write_text(VALID_CSV, encoding="utf-8")
    with pytest.raises(BloombergUnavailable):
        run_pipeline(universe_path, ExplodingSource(), tmp_path / "snapshots")
    assert not (tmp_path / "snapshots").exists()
