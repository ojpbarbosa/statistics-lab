import dataclasses

import pytest

from issuer_opportunity_screener.scoring import (
    WEIGHTS,
    normalize_rating,
    score_snapshot,
    screen_frame,
)
from issuer_opportunity_screener.snapshots import load_snapshot, write_snapshot
from issuer_opportunity_screener.sources.fixture import FixtureSource
from test_fixture_source import make_universe


@pytest.fixture(scope="module")
def snap(tmp_path_factory):
    universe = make_universe(12)
    result = FixtureSource().fetch(universe)
    root = tmp_path_factory.mktemp("snaps")
    return load_snapshot(write_snapshot(root, universe, result))


def test_weights_sum_to_one():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


def test_scores_one_per_fetched_issuer(snap):
    scores = score_snapshot(snap)
    # 12 universe rows, TICK4 and TICK10 failed (no spread) -> 10 scored
    assert {s.ticker for s in scores} == {
        "TICK0", "TICK1", "TICK2", "TICK3", "TICK5",
        "TICK6", "TICK7", "TICK8", "TICK9", "TICK11",
    }
    for s in scores:
        assert 0.0 <= s.composite <= 100.0
        assert s.tier in {"A", "B", "C"}
        assert len(s.blocks) == 5


def test_composite_renormalizes_missing_blocks(snap):
    scores = {s.ticker: s for s in score_snapshot(snap)}
    unlisted = scores["TICK2"]  # role 2: no equity -> block 4 None
    equity_block = next(b for b in unlisted.blocks if b.name == "Equity Overlay")
    assert equity_block.score is None
    assert unlisted.partial_data is True
    available = [b for b in unlisted.blocks if b.score is not None]
    expected = sum(b.weight * b.score for b in available) / sum(b.weight for b in available)
    assert unlisted.composite == pytest.approx(round(expected, 1))


def test_viability_flags(snap):
    scores = {s.ticker: s for s in score_snapshot(snap)}
    # TICK5: 140 bps vs Brazil 180 = -40 -> below tolerance, not viable even at BBB+
    assert scores["TICK5"].viable is False
    assert scores["TICK5"].spread_vs_brazil_bps == pytest.approx(-40.0)
    # TICK0: base spread 90+0=90? No: idx0 -> 90.0 bps -> -90 not viable
    assert scores["TICK0"].viable is False
    # TICK6: 90 + (6*37)%320 = 90+222 = 312 -> viable
    assert scores["TICK6"].viable is True


def test_screen_frame_shape_and_order(snap):
    scores = score_snapshot(snap)
    frame = screen_frame(snap, scores)
    assert list(frame.columns) == [
        "issuer", "ticker", "basket", "tier", "composite", "viable",
        "spread_vs_brazil_bps", "cds_5y_bps", "bond_z_spread_bps",
        "bond_last_price", "rating_composite", "internal_rating",
        "recognition_score", "partial_data", "quality_notes",
    ]
    assert len(frame) == len(scores)
    assert list(frame.composite) == sorted(frame.composite, reverse=True)
    tick1 = frame[frame.ticker == "TICK1"].iloc[0]
    assert tick1.rating_composite in {"BB", "BB+", "BB-", "B+", "BBB+"}


def test_breakdown_signals_present(snap):
    score = next(s for s in score_snapshot(snap) if s.ticker == "TICK0")
    block1 = next(b for b in score.blocks if b.name == "Credit and Spread Attractiveness")
    assert {sig.name for sig in block1.signals} == {
        "spread_level", "history_percentile", "vs_1y_ma", "vs_1y_p75", "vs_peer_median",
    }


def test_normalize_rating_tolerates_nan():
    assert normalize_rating(float("nan")) is None


def test_partially_filled_internal_rating_survives_parquet_roundtrip(tmp_path):
    # A universe where exactly one issuer has an internal_rating and the rest
    # are None reproduces the partially-filled string column that pandas 3.0
    # round-trips through parquet as float NaN for the unset entries.
    universe = make_universe(12)
    universe = [
        dataclasses.replace(u, internal_rating="BB+") if i == 0 else u
        for i, u in enumerate(universe)
    ]
    result = FixtureSource().fetch(universe)
    snap = load_snapshot(write_snapshot(tmp_path, universe, result))

    scores = score_snapshot(snap)  # must not raise AttributeError
    frame = screen_frame(snap, scores)

    rated = frame[frame.ticker == "TICK0"].iloc[0]
    assert rated.internal_rating == "BB+"
    unrated = frame[frame.ticker != "TICK0"]
    assert unrated.internal_rating.isna().all()


def test_screen_frame_empty_scores(snap):
    frame = screen_frame(snap, [])
    assert frame.empty
    assert list(frame.columns) == [
        "issuer", "ticker", "basket", "tier", "composite", "viable",
        "spread_vs_brazil_bps", "cds_5y_bps", "bond_z_spread_bps",
        "bond_last_price", "rating_composite", "internal_rating",
        "recognition_score", "partial_data", "quality_notes",
    ]
