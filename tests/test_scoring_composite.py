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
    # TICK5: 165 bps vs Brazil 180 = -15 -> within tolerance, BBB+ beats BB: edge case
    assert scores["TICK5"].viable is True
    assert scores["TICK5"].spread_vs_brazil_bps == pytest.approx(-15.0)
    assert "edge case" in scores["TICK5"].viability_note
    # TICK0: base spread 90+0=90? No: idx0 -> 90.0 bps -> -90 not viable
    assert scores["TICK0"].viable is False
    # TICK6: 90 + (6*37)%320 = 90+222 = 312 -> viable
    assert scores["TICK6"].viable is True


def test_screen_frame_shape_and_order(snap):
    scores = score_snapshot(snap)
    frame = screen_frame(snap, scores)
    assert list(frame.columns) == [
        "issuer", "ticker", "basket", "country", "sector", "tier", "composite", "viable",
        "spread_vs_brazil_bps", "cds_5y_bps", "bond_z_spread_bps",
        "bond_last_price", "rating_composite", "rating_source",
        "internal_rating", "recognition_score", "partial_data",
        "quality_notes", "viability_note", "flag_codes", "flag_notes",
        "coverage", "benchmark_basis", "rating_dispersion",
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
        "issuer", "ticker", "basket", "country", "sector", "tier", "composite", "viable",
        "spread_vs_brazil_bps", "cds_5y_bps", "bond_z_spread_bps",
        "bond_last_price", "rating_composite", "rating_source",
        "internal_rating", "recognition_score", "partial_data",
        "quality_notes", "viability_note", "flag_codes", "flag_notes",
        "coverage", "benchmark_basis", "rating_dispersion",
    ]


def test_signal_details_and_composite_detail_present(snap):
    score = next(s for s in score_snapshot(snap) if s.ticker == "TICK0")
    block1 = next(b for b in score.blocks if b.name == "Credit and Spread Attractiveness")
    for signal in block1.signals:
        assert signal.detail, f"missing detail for {signal.name}"
    assert "weekly closes" in next(s for s in block1.signals if s.name == "history_percentile").detail
    assert score.composite_detail.endswith(f"= {score.composite:.1f}")
    assert "*" in score.composite_detail  # weighted terms are spelled out


def test_ratings_all_flows_from_snapshot(snap):
    row = snap.frame[snap.frame.ticker == "TICK0"].iloc[0]
    assert row.ratings_all and "composite" in row.ratings_all
    scores = {s.ticker: s for s in score_snapshot(snap)}
    external = next(
        sig for b in scores["TICK0"].blocks for sig in b.signals if sig.name == "external_rating"
    )
    assert external.score is not None
    assert "median of" in external.detail


def _one_issuer_snapshot(tmp_path, spread_bps, internal_rating=None, ratings=None):
    import datetime as dtmod

    from issuer_opportunity_screener.snapshots import load_snapshot, write_snapshot
    from issuer_opportunity_screener.sources.base import (
        BrazilBenchmark,
        FetchResult,
        HistoryPoint,
        IssuerCredit,
        UniverseIssuer,
    )

    issuer = UniverseIssuer(
        issuer="Edge Case", ticker="EDGE", basket="Global Financials",
        country="Spain", sector="Financials", recognition_score=75.0,
        internal_rating=internal_rating,
    )
    credit = IssuerCredit(
        ticker="EDGE", cds_5y_bps=spread_bps, cds_liquidity_score=100.0,
        cds_security="EDGE CDS USD SR 5Y D14 Corp", ratings=ratings or {},
    )
    result = FetchResult(
        as_of=dtmod.datetime(2026, 7, 15, 12, 0),
        source="fixture",
        issuers=[credit],
        history=[
            HistoryPoint("EDGE", dtmod.date(2026, 7, 1) - dtmod.timedelta(weeks=w), spread_bps, "cds")
            for w in range(20)
        ],
        brazil=BrazilBenchmark(cds_5y_bps=180.0, z_spread_bps=None, rating_sp="BB"),
    )
    return load_snapshot(write_snapshot(tmp_path, [issuer], result))


def test_edge_case_viable_with_agency_rating(tmp_path):
    snap = _one_issuer_snapshot(tmp_path, 170.0, ratings={"sp": "A-", "moody": "A3"})
    score = score_snapshot(snap)[0]
    assert score.spread_vs_brazil_bps == pytest.approx(-10.0)
    assert score.viable is True
    assert "edge case" in score.viability_note


def test_edge_case_falls_back_to_internal_rating(tmp_path):
    snap = _one_issuer_snapshot(tmp_path, 170.0, internal_rating="BBB+")
    score = score_snapshot(snap)[0]
    assert score.viable is True
    assert "BBB+" in score.viability_note


def test_edge_case_not_viable_without_any_rating(tmp_path):
    snap = _one_issuer_snapshot(tmp_path, 170.0)
    score = score_snapshot(snap)[0]
    assert score.viable is False
    assert "no issuer rating" in score.viability_note


def test_rating_source_column_names_providers(snap):
    scores = score_snapshot(snap)
    frame = screen_frame(snap, scores)
    tick0 = frame[frame.ticker == "TICK0"].iloc[0]
    assert tick0.rating_source == "moody, sp, fitch, composite"
    assert tick0.viability_note


def test_edge_case_rows_identifiable_in_screen_frame(snap):
    frame = screen_frame(snap, score_snapshot(snap))
    edge = frame[frame.viable & (frame.spread_vs_brazil_bps < 0)]
    assert "TICK5" in set(edge.ticker)
    assert (edge.spread_vs_brazil_bps >= -20).all()
