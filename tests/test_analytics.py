"""Validation, sensitivity, concentration, and execution feasibility.

These answer the questions the methodology's own Validation Plan asks and the
screen never did: is the ranking stable, do the weights matter, is the shortlist
actually diversified, and can the names be executed.
"""
import datetime as dt

import pytest

from test_edge_cases import build_snapshot


def make_names(n, spreads=None, basket="Global Financials", country="United States"):
    spreads = spreads or {}
    return [
        (
            {"issuer": f"Co {i}", "ticker": f"T{i}", "basket": basket, "country": country},
            {"ticker": f"T{i}", "cds_5y_bps": spreads.get(i, 200.0 + 10 * i), "ratings": {"sp": "BBB"}},
        )
        for i in range(n)
    ]


# --- Reproducibility -----------------------------------------------------------

def test_snapshot_records_which_universe_produced_it(tmp_path):
    """Without this, the universe file drifts and quarantine removes names, so a
    snapshot cannot be reconstructed and any backtest is survivorship-biased."""
    from issuer_opportunity_screener.snapshots import load_snapshot, write_snapshot
    from issuer_opportunity_screener.sources.base import (
        BrazilBenchmark, FetchResult, IssuerCredit, UniverseIssuer)

    universe_path = tmp_path / "universe.csv"
    universe_path.write_text(
        "issuer,ticker,basket,country,sector,recognition_score\nAcme,ACME,Brazil,Brazil,Energy,80\n",
        encoding="utf-8",
    )
    universe = [UniverseIssuer(issuer="Acme", ticker="ACME", basket="Brazil",
                               country="Brazil", sector="Energy", recognition_score=80.0)]
    result = FetchResult(
        as_of=dt.datetime(2026, 7, 15), source="fixture",
        issuers=[IssuerCredit(ticker="ACME", cds_5y_bps=300.0)], history=[],
        brazil=BrazilBenchmark(cds_5y_bps=180.0, z_spread_bps=195.0, rating_sp="BB"),
    )
    snap = load_snapshot(write_snapshot(tmp_path / "snaps", universe, result, universe_path=universe_path))
    recorded = snap.manifest["universe"]
    assert recorded["rows"] == 1
    assert len(recorded["sha256"]) == 64
    assert recorded["path"].endswith("universe.csv")


def test_universe_fingerprint_changes_when_the_file_changes(tmp_path):
    from issuer_opportunity_screener.snapshots import universe_fingerprint

    path = tmp_path / "u.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    before = universe_fingerprint(path)
    path.write_text("a,b\n1,3\n", encoding="utf-8")
    assert universe_fingerprint(path)["sha256"] != before["sha256"]


# --- Is the ranking stable? -----------------------------------------------------

def test_rank_stability_reports_agreement_between_two_snapshots(tmp_path):
    from issuer_opportunity_screener.scoring import score_snapshot, screen_frame
    from issuer_opportunity_screener.validation import rank_stability

    snap_a = build_snapshot(tmp_path / "a", make_names(6))
    snap_b = build_snapshot(tmp_path / "b", make_names(6))
    frame_a = screen_frame(snap_a, score_snapshot(snap_a))
    frame_b = screen_frame(snap_b, score_snapshot(snap_b))

    stability = rank_stability(frame_a, frame_b)
    assert stability["names_in_both"] == 6
    assert stability["spearman"] == pytest.approx(1.0)  # identical inputs
    assert stability["tier_changes"] == 0
    assert stability["viability_flips"] == 0


def test_rank_stability_detects_a_reshuffle(tmp_path):
    from issuer_opportunity_screener.scoring import score_snapshot, screen_frame
    from issuer_opportunity_screener.validation import rank_stability

    snap_a = build_snapshot(tmp_path / "a", make_names(6))
    # Reverse the spreads: the ranking should invert.
    snap_b = build_snapshot(tmp_path / "b", make_names(6, spreads={i: 200.0 + 10 * (5 - i) for i in range(6)}))
    frame_a = screen_frame(snap_a, score_snapshot(snap_a))
    frame_b = screen_frame(snap_b, score_snapshot(snap_b))

    assert rank_stability(frame_a, frame_b)["spearman"] < 0


# --- Do the weights matter? -----------------------------------------------------

def test_score_snapshot_accepts_alternative_weights(tmp_path):
    from issuer_opportunity_screener.scoring import WEIGHTS, score_snapshot

    snap = build_snapshot(tmp_path, make_names(4))
    base = {s.ticker: s.composite for s in score_snapshot(snap)}
    tilted = dict(WEIGHTS)
    tilted["Credit and Spread Attractiveness"] = 0.60
    shifted = {s.ticker: s.composite for s in score_snapshot(snap, weights=tilted)}
    assert base != shifted


def test_weight_sensitivity_reports_how_much_the_top_names_move(tmp_path):
    """Pedro's question: are the weights load-bearing? This answers it with the
    overlap of the top names and the rank correlation under perturbed weights."""
    from issuer_opportunity_screener.validation import weight_sensitivity

    snap = build_snapshot(tmp_path, make_names(8))
    report = weight_sensitivity(snap, perturbation=0.10, top_n=5)
    assert report["scenarios"] >= 10  # each block up and down, plus all-up/all-down
    assert 0.0 <= report["min_top_n_overlap"] <= 1.0
    assert report["min_spearman"] <= report["mean_spearman"] <= 1.0
    assert len(report["per_scenario"]) == report["scenarios"]
    worst = min(report["per_scenario"], key=lambda r: r["top_n_overlap"])
    assert "label" in worst and "weights" in worst


# --- Is the shortlist actually a basket? ----------------------------------------

def test_concentration_flags_a_single_country_shortlist(tmp_path):
    from issuer_opportunity_screener.scoring import score_snapshot, screen_frame
    from issuer_opportunity_screener.validation import concentration

    snap = build_snapshot(tmp_path, make_names(5, country="United States"))
    frame = screen_frame(snap, score_snapshot(snap))
    report = concentration(frame, top_n=5)
    assert report["country"]["hhi"] == pytest.approx(1.0)  # everything in one bucket
    assert report["country"]["top_share"] == pytest.approx(1.0)
    assert report["country"]["largest"] == "United States"
    assert any("country" in warning for warning in report["warnings"])


def test_concentration_is_content_with_a_spread_out_shortlist(tmp_path):
    from issuer_opportunity_screener.scoring import score_snapshot, screen_frame
    from issuer_opportunity_screener.validation import concentration

    countries = ["United States", "Brazil", "Mexico", "Germany", "Chile"]
    sectors = ["Banks", "Energy", "Retail", "Autos", "Mining"]
    names = [
        ({"issuer": f"Co {i}", "ticker": f"T{i}", "basket": f"Basket {i}",
          "country": countries[i], "sector": sectors[i]},
         {"ticker": f"T{i}", "cds_5y_bps": 200.0 + 10 * i, "ratings": {"sp": "BBB"}})
        for i in range(5)
    ]
    snap = build_snapshot(tmp_path, names)
    frame = screen_frame(snap, score_snapshot(snap))
    report = concentration(frame, top_n=5)
    assert report["country"]["hhi"] == pytest.approx(0.2)
    assert report["warnings"] == []


def test_spread_correlation_sees_names_that_move_together(tmp_path):
    from issuer_opportunity_screener.validation import spread_correlation

    weeks = 30
    # Same weekly changes, different levels. A constant series would have no
    # variance and an undefined correlation, so the moves have to vary.
    together = {
        "T0": [200.0 + 5 * i + 15 * ((i * 7) % 5) for i in range(weeks)],
        "T1": [300.0 + 5 * i + 15 * ((i * 7) % 5) for i in range(weeks)],
    }
    snap = build_snapshot(tmp_path, make_names(2), history_by_ticker=together)
    report = spread_correlation(snap, ["T0", "T1"])
    assert report["mean_pairwise"] == pytest.approx(1.0, abs=0.01)
    assert report["pairs"] == 1


def test_spread_correlation_handles_too_little_history(tmp_path):
    from issuer_opportunity_screener.validation import spread_correlation

    snap = build_snapshot(tmp_path, make_names(2))
    assert spread_correlation(snap, ["T0", "T1"])["mean_pairwise"] is None


# --- Can the names actually be executed? ----------------------------------------

def test_small_issue_size_is_flagged(tmp_path):
    from issuer_opportunity_screener.scoring import MIN_ISSUE_SIZE_USD, score_snapshot

    snap = build_snapshot(tmp_path, [
        ({"issuer": "Tiny Co", "ticker": "TINY"},
         {"ticker": "TINY", "ratings": {"sp": "BBB"},
          "bond": {"security": "TINY 5 2031 Corp", "z_spread_bps": 300.0,
                   "amount_outstanding": MIN_ISSUE_SIZE_USD / 2}}),
    ])
    score = score_snapshot(snap)[0]
    assert "small_issue" in {f.code for f in score.flags}


def test_report_carries_the_validation_section(tmp_path):
    from issuer_opportunity_screener.reports import build_report

    snap = build_snapshot(tmp_path, make_names(6))
    report = build_report(snap)
    assert "## Validation" in report
    assert "Weight sensitivity" in report
    assert "Concentration" in report
    # The worst scenario must be nameable, not just a number.
    assert "up 10%" in report or "tilt" in report


def test_hedged_pickup_subtracts_the_desk_hedging_cost(tmp_path):
    """The USD spread is not the client's economics: a BRL-hedged note pays the
    cross-currency cost. The cost is a desk input, not a market observation."""
    from issuer_opportunity_screener.scoring import hedged_pickup_bps

    assert hedged_pickup_bps(320.0, 180.0, hedge_cost_bps=60.0) == pytest.approx(80.0)
    assert hedged_pickup_bps(320.0, 180.0, hedge_cost_bps=0.0) == pytest.approx(140.0)
    assert hedged_pickup_bps(None, 180.0, hedge_cost_bps=60.0) is None
    assert hedged_pickup_bps(320.0, None, hedge_cost_bps=60.0) is None
