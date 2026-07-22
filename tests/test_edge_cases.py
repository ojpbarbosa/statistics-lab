"""Edge cases the desk cares about beyond the through-Brazil tolerance rule.

One test per behavior, each named for the credit situation it protects against.
"""
import datetime as dt

import pytest

from issuer_opportunity_screener.scoring import (
    LONG_TENOR_YEARS,
    MIN_PEERS,
    SPLIT_RATING_NOTCHES,
    brazil_reference,
    conservative_rating_rank_any,
    composite_rating_rank_any,
    history_is_stale,
    is_subordinated,
    peer_median_score,
    rating_dispersion_notches,
    rating_outlook,
    years_to_maturity,
)


# --- Split ratings ------------------------------------------------------------

def test_two_provider_split_breaks_toward_the_weaker_rating():
    """Banker's rounding used to flip the tie-break direction depending on where
    the split sat on the scale. A credit gate should always read conservatively."""
    # A- (6) and BBB+ (7): median 6.5 must resolve to BBB+, the weaker side.
    assert composite_rating_rank_any({"sp": "A-", "moody": "Baa1"}) == 7
    # BBB+ (7) and BBB (8): median 7.5 must also resolve to the weaker side.
    assert composite_rating_rank_any({"sp": "BBB+", "moody": "Baa2"}) == 8


def test_conservative_rank_is_the_worst_rating_not_the_median():
    ratings = {"sp": "A", "moody": "Ba1"}  # A (5) vs BB+ (10)
    assert conservative_rating_rank_any(ratings) == 10
    assert conservative_rating_rank_any({}) is None


def test_rating_dispersion_counts_notches_between_providers():
    assert rating_dispersion_notches({"sp": "A", "moody": "Ba1"}) == 5
    assert rating_dispersion_notches({"sp": "BBB", "moody": "Baa2"}) == 0
    assert rating_dispersion_notches({"sp": "BBB"}) == 0
    assert rating_dispersion_notches({}) is None
    assert SPLIT_RATING_NOTCHES == 3


# --- Outlook and watch, which normalize_rating deliberately strips ------------

def test_rating_outlook_survives_normalization():
    assert rating_outlook("BBB- *-") == "negative"
    assert rating_outlook("BBB (negative)") == "negative"
    assert rating_outlook("BBB *+") == "positive"
    assert rating_outlook("BBB (positive outlook)") == "positive"
    assert rating_outlook("BBB (stable)") == "stable"
    assert rating_outlook("BBB") is None
    assert rating_outlook(None) is None


# --- Stale history faking a percentile ----------------------------------------

def test_flat_history_is_stale_not_stable():
    assert history_is_stale([200.0] * 52) is True
    assert history_is_stale([200.0, 200.0, 201.0] * 8) is True  # 2 unique values
    assert history_is_stale([float(x) for x in range(100, 160)]) is False
    assert history_is_stale([]) is True


# --- Thin baskets --------------------------------------------------------------

def test_peer_median_needs_a_real_peer_group():
    assert MIN_PEERS >= 3
    assert peer_median_score(300.0, 200.0, peer_count=MIN_PEERS) == 75.0
    assert peer_median_score(300.0, 200.0, peer_count=1) is None


# --- Curve, not credit ---------------------------------------------------------

def test_years_to_maturity_flags_long_bonds_against_the_5y_cds_standard():
    as_of = dt.datetime(2026, 7, 15)
    assert years_to_maturity(dt.date(2036, 7, 15), as_of) == pytest.approx(10.0, abs=0.02)
    assert years_to_maturity(None, as_of) is None
    assert LONG_TENOR_YEARS == 7.0


# --- Subordination in financials -----------------------------------------------

def test_subordination_is_detected_from_payment_rank():
    assert is_subordinated("Sr Unsecured") is False
    assert is_subordinated("1st lien") is False
    assert is_subordinated("Subordinated") is True
    assert is_subordinated("Jr Subordinated") is True
    assert is_subordinated("Sr Non-Preferred") is True
    assert is_subordinated(None) is False


# --- Bond spread benchmarked against a CDS level --------------------------------

def test_brazil_reference_matches_the_issuer_instrument():
    level, basis, like_for_like = brazil_reference("cds", 180.0, 195.0)
    assert (level, basis, like_for_like) == (180.0, "5Y CDS vs Brazil 5Y CDS", True)

    level, basis, like_for_like = brazil_reference("bond", 180.0, 195.0)
    assert level == 195.0 and like_for_like is True and "bond" in basis

    # No sovereign bond spread: fall back to CDS, but say it is not like-for-like.
    level, basis, like_for_like = brazil_reference("bond", 180.0, None)
    assert level == 180.0 and like_for_like is False and "indicative" in basis


# --- Plumbing the two fields the flags need ------------------------------------

def test_selected_bond_carries_its_payment_rank():
    from issuer_opportunity_screener.sources.bloomberg import credit_from_fields

    credit = credit_from_fields(
        "SANTAN",
        {"cds_5y_bps": 120.0},
        {"security": "SANTAN 5 2032 Corp", "payment_rank": "Sr Non-Preferred", "z_spread_bps": 210.0},
    )
    assert credit.bond.payment_rank == "Sr Non-Preferred"


def test_universe_reads_the_desk_state_linked_flag(tmp_path):
    from issuer_opportunity_screener.universe import load_universe

    csv_path = tmp_path / "universe.csv"
    csv_path.write_text(
        "issuer,ticker,basket,country,sector,recognition_score,state_linked\n"
        "Petrobras,PETBRA,Brazil,Brazil,Energy,90,yes\n"
        "Tesla,TSLA,Brazil,United States,Autos,95,\n",
        encoding="utf-8",
    )
    petbra, tsla = load_universe(csv_path)
    assert petbra.state_linked is True
    assert tsla.state_linked is False


def test_adding_a_name_preserves_isin_and_state_linked_on_existing_rows(tmp_path):
    """The admin writer rewrites the whole file from a fixed field list, so any
    column missing from that list is silently dropped from every existing row."""
    from issuer_opportunity_screener.universe_admin import append_issuer

    csv_path = tmp_path / "universe.csv"
    csv_path.write_text(
        "issuer,ticker,basket,country,sector,recognition_score,internal_rating,"
        "equity_ticker,cds_ticker,isin,state_linked\n"
        "Petrobras,PETBRA,Brazil,Brazil,Energy,90,BB,PETR4 BZ Equity,,US71654QCB18,yes\n",
        encoding="utf-8",
    )
    append_issuer(csv_path, {
        "issuer": "Vale", "ticker": "VALEBZ", "basket": "Brazil",
        "country": "Brazil", "sector": "Mining", "recognition_score": "88",
    })
    rows = csv_path.read_text(encoding="utf-8")
    assert "US71654QCB18" in rows
    assert "yes" in rows


def test_snapshot_frame_exposes_seniority_and_state_linkage(tmp_path):
    from issuer_opportunity_screener.snapshots import load_snapshot, write_snapshot
    from issuer_opportunity_screener.sources.base import (
        BondSnapshot, BrazilBenchmark, FetchResult, IssuerCredit, UniverseIssuer)

    universe = [
        UniverseIssuer(
            issuer="Petrobras", ticker="PETBRA", basket="Brazil", country="Brazil",
            sector="Energy", recognition_score=90.0, state_linked=True,
        )
    ]
    result = FetchResult(
        as_of=dt.datetime(2026, 7, 15),
        source="fixture",
        issuers=[
            IssuerCredit(
                ticker="PETBRA",
                bond=BondSnapshot(security="PETBRA 6 2033 Corp", payment_rank="Subordinated"),
            )
        ],
        history=[],
        brazil=BrazilBenchmark(cds_5y_bps=180.0, z_spread_bps=195.0, rating_sp="BB"),
    )
    snap = load_snapshot(write_snapshot(tmp_path, universe, result))
    assert snap.frame.bond_payment_rank.iloc[0] == "Subordinated"
    assert bool(snap.frame.state_linked.iloc[0]) is True


# --- Integration: the flags and gates on a scored snapshot ----------------------

AS_OF = dt.datetime(2026, 7, 15)


def build_snapshot(tmp_path, names, brazil_z_spread_bps=195.0, history_by_ticker=None):
    """names: list of (UniverseIssuer kwargs, IssuerCredit kwargs) pairs."""
    from issuer_opportunity_screener.snapshots import load_snapshot, write_snapshot
    from issuer_opportunity_screener.sources.base import (
        BondSnapshot, BrazilBenchmark, FetchResult, HistoryPoint, IssuerCredit, UniverseIssuer)

    universe, credits = [], []
    for u_kwargs, c_kwargs in names:
        defaults = dict(
            basket="Global Financials", country="United States",
            sector="Banks", recognition_score=70.0,
        )
        universe.append(UniverseIssuer(**{**defaults, **u_kwargs}))
        c_kwargs = dict(c_kwargs)
        if isinstance(c_kwargs.get("bond"), dict):
            c_kwargs["bond"] = BondSnapshot(**c_kwargs["bond"])
        credits.append(IssuerCredit(**c_kwargs))

    history = [
        HistoryPoint(ticker=ticker, date=AS_OF.date() - dt.timedelta(weeks=n), spread_bps=value, instrument="cds")
        for ticker, values in (history_by_ticker or {}).items()
        for n, value in enumerate(values)
    ]
    result = FetchResult(
        as_of=AS_OF, source="fixture", issuers=credits, history=history,
        brazil=BrazilBenchmark(cds_5y_bps=180.0, z_spread_bps=brazil_z_spread_bps, rating_sp="BB"),
    )
    return load_snapshot(write_snapshot(tmp_path, universe, result))


def score_one(tmp_path, u_kwargs, c_kwargs, **kwargs):
    from issuer_opportunity_screener.scoring import score_snapshot

    snap = build_snapshot(tmp_path, [(u_kwargs, c_kwargs)], **kwargs)
    return snap, score_snapshot(snap)[0]


def codes(score):
    return {f.code for f in score.flags}


def test_unrated_wide_name_cannot_reach_tier_a(tmp_path):
    """The renormalization used to reward a missing rating: dropping the credit
    block removed the only thing that would have punished a 900 bps spread."""
    _, score = score_one(
        tmp_path,
        {"issuer": "No Ratings Co", "ticker": "NORATE", "recognition_score": 60.0},
        {"ticker": "NORATE", "cds_5y_bps": 900.0},
    )
    assert "unrated" in codes(score)
    assert score.tier != "A"


def test_coverage_reports_how_much_weight_actually_scored(tmp_path):
    _, score = score_one(
        tmp_path,
        {"issuer": "No Ratings Co", "ticker": "NORATE"},
        {"ticker": "NORATE", "cds_5y_bps": 300.0},
    )
    # No ratings (block 2) and no equity (block 4): 0.35 + 0.20 + 0.15 of the weight.
    assert score.coverage == pytest.approx(0.70)


def test_viability_uses_the_conservative_rating_on_a_split(tmp_path):
    """S&P A and Moody's B1 median to BBB-, which beats Brazil's BB and would
    pass the through-Brazil edge case. The weakest read, B+, must not."""
    _, score = score_one(
        tmp_path,
        {"issuer": "Split Rated SA", "ticker": "SPLIT"},
        {"ticker": "SPLIT", "cds_5y_bps": 165.0, "ratings": {"sp": "A", "moody": "B1"}},
    )
    assert score.viable is False
    assert "split_rating" in codes(score)
    assert score.rating_dispersion == 8


def test_bond_only_name_is_benchmarked_against_the_brazil_bond_spread(tmp_path):
    """A bond z-spread compared against the sovereign CDS is apples to oranges."""
    _, score = score_one(
        tmp_path,
        {"issuer": "Bond Only Co", "ticker": "BONDCO"},
        {"ticker": "BONDCO", "bond": {"security": "BONDCO 5 2031 Corp", "z_spread_bps": 190.0}},
    )
    assert score.spread_vs_brazil_bps == pytest.approx(-5.0)  # 190 vs Brazil bond 195, not CDS 180
    assert "bond z-spread vs Brazil bond z-spread" in score.benchmark_basis


def test_bond_only_name_without_a_sovereign_bond_is_marked_indicative(tmp_path):
    _, score = score_one(
        tmp_path,
        {"issuer": "Bond Only Co", "ticker": "BONDCO"},
        {"ticker": "BONDCO", "bond": {"security": "BONDCO 5 2031 Corp", "z_spread_bps": 190.0}},
        brazil_z_spread_bps=None,
    )
    assert "benchmark_mismatch" in codes(score)
    assert "indicative" in score.benchmark_basis


def test_flag_when_the_viability_verdict_depends_on_which_brazil_leg_is_used(tmp_path):
    """190 clears Brazil's 180 CDS but sits through its 195 bond spread, and the
    rating is no stronger than Brazil's, so the tolerance rule cannot rescue it."""
    _, score = score_one(
        tmp_path,
        {"issuer": "Bond Only Co", "ticker": "BONDCO"},
        {"ticker": "BONDCO", "bond": {"security": "BONDCO 5 2031 Corp", "z_spread_bps": 190.0},
         "ratings": {"sp": "BB"}},
    )
    assert "benchmark_sensitive" in codes(score)


def test_stale_history_does_not_produce_a_percentile(tmp_path):
    snap, score = score_one(
        tmp_path,
        {"issuer": "Stale Quote Co", "ticker": "STALE"},
        {"ticker": "STALE", "cds_5y_bps": 300.0, "ratings": {"sp": "BB"}},
        history_by_ticker={"STALE": [300.0] * 52},
    )
    block = next(b for b in score.blocks if b.name == "Credit and Spread Attractiveness")
    percentile = next(s for s in block.signals if s.name == "history_percentile")
    assert percentile.score is None
    assert "stale_history" in codes(score)


def test_thin_basket_drops_the_peer_median_signal(tmp_path):
    snap = build_snapshot(
        tmp_path,
        [
            ({"issuer": "A Co", "ticker": "ACO"}, {"ticker": "ACO", "cds_5y_bps": 300.0}),
            ({"issuer": "B Co", "ticker": "BCO"}, {"ticker": "BCO", "cds_5y_bps": 200.0}),
        ],
    )
    from issuer_opportunity_screener.scoring import score_snapshot

    score = score_snapshot(snap)[0]
    block = next(b for b in score.blocks if b.name == "Credit and Spread Attractiveness")
    peer = next(s for s in block.signals if s.name == "vs_peer_median")
    assert peer.score is None  # one peer is not a peer group
    assert "thin_peers" in codes(score)


def test_subordinated_bond_is_flagged_not_read_as_cheap(tmp_path):
    _, score = score_one(
        tmp_path,
        {"issuer": "Banco SA", "ticker": "BANCO"},
        {"ticker": "BANCO", "cds_5y_bps": 300.0, "ratings": {"sp": "BBB"},
         "bond": {"security": "BANCO 7 2033 Corp", "payment_rank": "Sr Non-Preferred"}},
    )
    assert "subordinated" in codes(score)


def test_long_tenor_bond_is_flagged_as_curve_not_credit(tmp_path):
    _, score = score_one(
        tmp_path,
        {"issuer": "Long Co", "ticker": "LONGCO"},
        {"ticker": "LONGCO", "ratings": {"sp": "BBB"},
         "bond": {"security": "LONGCO 5 2036 Corp", "z_spread_bps": 300.0,
                  "maturity": dt.date(2036, 7, 15)}},
    )
    assert "long_tenor" in codes(score)


def test_domestic_and_state_linked_names_are_flagged_sovereign_correlated(tmp_path):
    _, domestic = score_one(
        tmp_path / "a",
        {"issuer": "Brazil Corp", "ticker": "BRCO", "country": "Brazil", "basket": "Brazil"},
        {"ticker": "BRCO", "cds_5y_bps": 300.0, "ratings": {"sp": "BBB"}},
    )
    assert "sovereign_correlated" in codes(domestic)

    _, soe = score_one(
        tmp_path / "b",
        {"issuer": "Pemex", "ticker": "PEMEX", "country": "Mexico", "state_linked": True},
        {"ticker": "PEMEX", "cds_5y_bps": 300.0, "ratings": {"sp": "BBB"}},
    )
    assert "sovereign_correlated" in codes(soe)


def test_screen_frame_carries_the_flags_to_the_desk(tmp_path):
    from issuer_opportunity_screener.scoring import score_snapshot, screen_frame

    snap = build_snapshot(
        tmp_path,
        [({"issuer": "No Ratings Co", "ticker": "NORATE"}, {"ticker": "NORATE", "cds_5y_bps": 900.0})],
    )
    frame = screen_frame(snap, score_snapshot(snap))
    row = frame.iloc[0]
    assert "unrated" in row.flag_codes
    assert "credit-quality block is absent" in row.flag_notes
    assert row.coverage == pytest.approx(0.70)
    assert row.benchmark_basis == "5Y CDS vs Brazil 5Y CDS"


def test_report_has_a_section_for_flagged_names(tmp_path):
    from issuer_opportunity_screener.reports import build_report

    snap = build_snapshot(
        tmp_path,
        [({"issuer": "Banco SA", "ticker": "BANCO"},
          {"ticker": "BANCO", "cds_5y_bps": 300.0, "ratings": {"sp": "BBB"},
           "bond": {"security": "BANCO 7 2033 Corp", "payment_rank": "Sr Non-Preferred"}})],
    )
    report = build_report(snap)
    assert "## Flagged names" in report
    assert "subordinated" in report and "Banco SA" in report


def test_stale_history_suppresses_the_own_history_extreme_callout(tmp_path):
    from issuer_opportunity_screener.insights import own_history_percentile

    snap = build_snapshot(
        tmp_path,
        [({"issuer": "Stale Quote Co", "ticker": "STALE"}, {"ticker": "STALE", "cds_5y_bps": 300.0})],
        history_by_ticker={"STALE": [300.0] * 52},
    )
    # Without the staleness guard this reads as the 100th percentile of its own range.
    assert own_history_percentile(snap, "STALE", 300.0) is None


def test_viability_flip_is_attributed_to_the_sovereign_when_brazil_moved(tmp_path):
    """Brazil's own CDS moves 20 to 30 bps a week against a 20 bps tolerance, so a
    name can flip without anything happening to the credit."""
    import pandas as pd

    from issuer_opportunity_screener.insights import build_insights, movers_frame

    snap = build_snapshot(
        tmp_path,
        [({"issuer": "Steady Co", "ticker": "STEADY"}, {"ticker": "STEADY", "cds_5y_bps": 175.0})],
    )
    columns = ["issuer", "ticker", "basket", "cds_5y_bps", "bond_z_spread_bps",
               "spread_vs_brazil_bps", "viable", "composite", "tier"]
    now = pd.DataFrame([["Steady Co", "STEADY", "Global Financials", 175.0, None,
                         -5.0, True, 60.0, "B"]], columns=columns)
    then = pd.DataFrame([["Steady Co", "STEADY", "Global Financials", 173.0, None,
                          -37.0, False, 60.0, "B"]], columns=columns)

    movers = movers_frame(now, then, brazil_now=180.0, brazil_then=210.0)
    assert movers.brazil_delta_bps.iloc[0] == pytest.approx(-30.0)

    messages = [i.message for i in build_insights(movers, snap, "2026-07-08") if i.kind == "now_viable"]
    assert len(messages) == 1
    assert "Brazil" in messages[0] and "30" in messages[0]


def test_wide_spread_with_a_negative_outlook_is_cheap_for_a_reason(tmp_path):
    _, score = score_one(
        tmp_path,
        {"issuer": "Falling Angel", "ticker": "FALL"},
        {"ticker": "FALL", "cds_5y_bps": 600.0, "ratings": {"sp": "BBB- *-"}},
    )
    assert "cheap_for_a_reason" in codes(score)
    block = next(b for b in score.blocks if b.name == "Credit Quality and Risk")
    trend = next(s for s in block.signals if s.name == "rating_trend")
    assert trend.score is not None and trend.score < 50.0
