import datetime as dt

from issuer_opportunity_screener.sources.base import (
    BloombergUnavailable,
    BondSnapshot,
    BrazilBenchmark,
    EquityOverlay,
    FetchResult,
    HistoryPoint,
    IssuerCredit,
    UniverseIssuer,
)


def test_issuer_credit_defaults_are_empty_not_shared():
    a = IssuerCredit(ticker="AAA")
    b = IssuerCredit(ticker="BBB")
    a.quality_notes.append("note")
    assert b.quality_notes == []
    assert a.cds_5y_bps is None
    assert a.bond.z_spread_bps is None
    assert a.equity.equity_ticker is None


def test_fetch_result_shape():
    result = FetchResult(
        as_of=dt.datetime(2026, 7, 15, 12, 0),
        source="fixture",
        issuers=[IssuerCredit(ticker="AAA")],
        history=[HistoryPoint("AAA", dt.date(2026, 7, 1), 250.0, "cds")],
        brazil=BrazilBenchmark(cds_5y_bps=180.0, z_spread_bps=195.0, rating_sp="BB"),
    )
    assert result.failures == {}
    assert result.history[0].instrument == "cds"


def test_bloomberg_unavailable_is_runtime_error():
    assert issubclass(BloombergUnavailable, RuntimeError)


def test_universe_issuer_importable_from_both_modules():
    from issuer_opportunity_screener.universe import UniverseIssuer as FromUniverse

    assert FromUniverse is UniverseIssuer
