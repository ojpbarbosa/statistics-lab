from issuer_opportunity_screener.sources.fixture import FIXTURE_BRAZIL, FixtureSource
from issuer_opportunity_screener.universe import UniverseIssuer


def make_universe(n=12):
    return [
        UniverseIssuer(
            issuer=f"Issuer {i}",
            ticker=f"TICK{i}",
            basket="Brazil",
            country="Brazil",
            sector="Energy",
            recognition_score=80.0,
        )
        for i in range(n)
    ]


def test_deterministic():
    universe = make_universe()
    r1 = FixtureSource().fetch(universe)
    r2 = FixtureSource().fetch(universe)
    assert r1 == r2


def test_edge_case_roles():
    universe = make_universe(12)
    result = FixtureSource().fetch(universe)
    by_ticker = {c.ticker: c for c in result.issuers}

    assert result.source == "fixture"
    assert result.brazil == FIXTURE_BRAZIL

    # role 1: missing CDS but has a bond
    assert by_ticker["TICK1"].cds_5y_bps is None
    assert by_ticker["TICK1"].bond.z_spread_bps is not None
    assert any("cds" in n.lower() for n in by_ticker["TICK1"].quality_notes)

    # role 2: unlisted equity
    assert by_ticker["TICK2"].equity.equity_ticker is None

    # role 3: partial history (8 points vs 52 for normal names)
    hist3 = [h for h in result.history if h.ticker == "TICK3"]
    hist0 = [h for h in result.history if h.ticker == "TICK0"]
    assert len(hist3) == 8
    assert len(hist0) == 52

    # role 4: fetch failure — absent from issuers, present in failures
    assert "TICK4" not in by_ticker
    assert "TICK4" in result.failures

    # role 5: tighter than Brazil, strong rating
    assert by_ticker["TICK5"].cds_5y_bps < FIXTURE_BRAZIL.cds_5y_bps
    assert by_ticker["TICK5"].rating_sp == "BBB+"


def test_spreads_positive_and_history_matches_instrument():
    result = FixtureSource().fetch(make_universe(6))
    for credit in result.issuers:
        spread = credit.cds_5y_bps or credit.bond.z_spread_bps
        assert spread is not None and spread > 0
    instruments = {h.ticker: h.instrument for h in result.history}
    assert instruments["TICK1"] == "bond"
    assert instruments["TICK0"] == "cds"
