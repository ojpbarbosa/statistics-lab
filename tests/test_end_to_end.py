"""Fixture -> pipeline -> snapshot -> scoring -> screen frame, on the real universe file."""
from pathlib import Path

from issuer_opportunity_screener.pipeline import run_pipeline
from issuer_opportunity_screener.scoring import score_snapshot, screen_frame
from issuer_opportunity_screener.snapshots import load_snapshot
from issuer_opportunity_screener.sources.fixture import FixtureSource

REPO_UNIVERSE = Path(__file__).resolve().parents[1] / "data" / "universe.csv"


def test_full_flow_on_repo_universe(tmp_path):
    snap_dir = run_pipeline(REPO_UNIVERSE, FixtureSource(), tmp_path / "snapshots")
    snap = load_snapshot(snap_dir)
    scores = score_snapshot(snap)
    frame = screen_frame(snap, scores)

    assert snap.manifest["issuer_count"] >= 80
    assert len(scores) == snap.manifest["fetched_count"]
    assert set(frame.tier) <= {"A", "B", "C"}
    assert frame.composite.between(0, 100).all()
    # every scored issuer has a full 5-block breakdown
    assert all(len(s.blocks) == 5 for s in scores)
    # viability is decided (True/False, never None) for every scored name
    assert frame.viable.isin([True, False]).all()
