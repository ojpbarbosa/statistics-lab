import datetime as dt

import pytest

from issuer_opportunity_screener.insights import build_insights, movers_frame, scored_frames
from issuer_opportunity_screener.snapshots import load_snapshot, write_snapshot
from issuer_opportunity_screener.sources.base import (
    BrazilBenchmark,
    FetchResult,
    HistoryPoint,
    IssuerCredit,
    UniverseIssuer,
)

BRAZIL = BrazilBenchmark(cds_5y_bps=180.0, z_spread_bps=None, rating_sp="BB")


def make_snapshot(tmp_path, as_of, spreads: dict[str, float | None], name: str):
    universe = [
        UniverseIssuer(
            issuer=f"Issuer {ticker}", ticker=ticker, basket="Brazil",
            country="Brazil", sector="Energy", recognition_score=80.0,
        )
        for ticker in spreads
    ]
    issuers = []
    history = []
    for ticker, spread in spreads.items():
        if spread is None:
            continue
        issuers.append(
            IssuerCredit(
                ticker=ticker, cds_5y_bps=spread, cds_liquidity_score=100.0,
                cds_security=f"{ticker} CDS USD SR 5Y D14 Corp",
                ratings={"sp": "BBB"},
            )
        )
        # Varying closes, all below the current spread: a real 1y range rather
        # than a repeated value, which now reads as a stale quote.
        history.extend(
            HistoryPoint(ticker, as_of.date() - dt.timedelta(weeks=w), spread * (0.60 + 0.01 * (w % 12)), "cds")
            for w in range(1, 21)
        )
    result = FetchResult(as_of=as_of, source="fixture", issuers=issuers, history=history, brazil=BRAZIL)
    return load_snapshot(write_snapshot(tmp_path / name, universe, result))


@pytest.fixture()
def two_snapshots(tmp_path):
    then = make_snapshot(
        tmp_path, dt.datetime(2026, 7, 9, 12, 0),
        {"TIGHT": 400.0, "WIDE": 200.0, "FLIP": 150.0, "GONE": 250.0},
        "then",
    )
    now = make_snapshot(
        tmp_path, dt.datetime(2026, 7, 16, 12, 0),
        {"TIGHT": 300.0, "WIDE": 260.0, "FLIP": 185.0, "GONE": None, "FRESH": 320.0},
        "now",
    )
    return now, then


def test_movers_frame_deltas_and_status(two_snapshots):
    now, then = two_snapshots
    frame_now, frame_then, _, _ = scored_frames(now, then)
    movers = movers_frame(frame_now, frame_then)
    by_ticker = movers.set_index("ticker")

    assert by_ticker.loc["TIGHT"].delta_bps == pytest.approx(-100.0)
    assert by_ticker.loc["WIDE"].delta_bps == pytest.approx(60.0)
    assert by_ticker.loc["FRESH"].status == "new"
    assert by_ticker.loc["GONE"].status == "dropped"


def test_insight_callouts(two_snapshots):
    now, then = two_snapshots
    frame_now, frame_then, _, _ = scored_frames(now, then)
    movers = movers_frame(frame_now, frame_then)
    insights = build_insights(movers, now, "2026-07-09")
    kinds = {i.kind for i in insights}
    messages = " | ".join(i.message for i in insights)

    assert "tightener" in kinds and "TIGHT" in messages
    assert "widener" in kinds and "WIDE" in messages
    assert "now_viable" in kinds and "FLIP" in messages  # 150 -> 185 crosses Brazil at 180
    assert "new_name" in kinds and "FRESH" in messages
    assert "dropped" in kinds and "GONE" in messages
    # every current spread sits above its synthetic 1y history (0.7x), so the
    # own-history callout fires too
    assert "own_history_high" in kinds


def test_insights_empty_when_nothing_moves(tmp_path):
    a = make_snapshot(tmp_path, dt.datetime(2026, 7, 9, 12, 0), {"SAME": 250.0}, "a")
    b = make_snapshot(tmp_path, dt.datetime(2026, 7, 16, 12, 0), {"SAME": 250.0}, "b")
    frame_now, frame_then, _, _ = scored_frames(b, a)
    movers = movers_frame(frame_now, frame_then)
    insights = build_insights(movers, b, "2026-07-09")
    assert not [i for i in insights if i.kind in {"tightener", "widener", "now_viable", "lost_viability", "new_name", "dropped"}]
