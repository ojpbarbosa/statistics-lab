import datetime as dt
import json

import pytest

from issuer_opportunity_screener.sources.base import UniverseIssuer
from issuer_opportunity_screener.sources.hermes import (
    HermesClient,
    HermesSource,
    HermesUnavailable,
    clean_price,
    ytm_pct,
)

TODAY = dt.date(2026, 7, 21)
BRAZIL_ISIN = "US105756BV13"


def make_issuer(ticker: str, isin: str | None) -> UniverseIssuer:
    return UniverseIssuer(
        issuer=ticker.title(), ticker=ticker, basket="Brazil", country="Brazil",
        sector="Test", recognition_score=80.0, isin=isin,
    )


def bond_row(isin: str, date: str, clean: float, coupon: float, maturity: str, **extra) -> dict:
    row = {
        "id": 1, "symbol": isin, "isin": isin,
        "requestDate": f"{date}T00:00:00",
        "cleanMidPriceEoD": clean, "dirtyMidPriceEoD": 0, "intAcc": 0,
        "dirtyBid": 0, "dirtyAsk": 0,
        "coupon": coupon, "maturityDate": f"{maturity}T00:00:00",
        "nextCallDate": None, "status": None,
    }
    row.update(extra)
    return row


def make_source(rows: list[dict], **kwargs) -> tuple[HermesSource, list[tuple[str, dict]]]:
    calls: list[tuple[str, dict]] = []

    def fetcher(url: str, headers: dict) -> bytes:
        calls.append((url, headers))
        return json.dumps(rows).encode()

    client = HermesClient("https://hermes.example/", token="tok-123", fetcher=fetcher)
    defaults = dict(brazil_isin=BRAZIL_ISIN, brazil_spread_bps=180.0, lookback_days=5, today=TODAY)
    defaults.update(kwargs)
    return HermesSource(client, **defaults), calls


# Both bonds priced at par so ytm == coupon and the spread is exactly
# 180 + (6 - 5) * 100 = 280 bps.
PAR_ROWS = [
    bond_row(BRAZIL_ISIN, "2026-07-20", 100.0, 5.0, "2031-07-20"),
    bond_row(BRAZIL_ISIN, "2026-07-21", 100.0, 5.0, "2031-07-20"),
    bond_row("US88160RAG12", "2026-07-20", 100.0, 6.0, "2031-07-20"),
    bond_row("US88160RAG12", "2026-07-21", 100.0, 6.0, "2031-07-20"),
]


def test_ytm_recovers_coupon_at_par():
    assert ytm_pct(100.0, 6.0, dt.date(2031, 7, 21), TODAY) == pytest.approx(6.0, abs=1e-3)


def test_ytm_rejects_matured_and_unpriceable():
    assert ytm_pct(100.0, 6.0, TODAY, TODAY) is None
    assert ytm_pct(0.0, 6.0, dt.date(2031, 7, 21), TODAY) is None


def test_clean_price_prefers_clean_then_strips_accrued():
    assert clean_price({"cleanMidPriceEoD": 98.5}) == 98.5
    assert clean_price({"cleanMidPriceEoD": 0, "dirtyMidPriceEoD": 99.0, "intAcc": 1.5}) == 97.5
    assert clean_price({"cleanMidPriceEoD": 0, "dirtyMidPriceEoD": 0,
                        "dirtyBid": 98.0, "dirtyAsk": 100.0, "intAcc": 1.0}) == 98.0
    assert clean_price({"cleanMidPriceEoD": 0, "dirtyMidPriceEoD": 0, "dirtyBid": 0, "dirtyAsk": 0}) is None


def test_request_url_and_bearer_header():
    source, calls = make_source(PAR_ROWS)
    source.fetch([make_issuer("TSLA", "US88160RAG12")])
    (url, headers), = calls
    assert url == "https://hermes.example/v1/BBG/Bonds/2026-07-16/2026-07-21"
    assert headers["Authorization"] == "Bearer tok-123"


def test_spread_anchored_on_brazil_with_history():
    source, _ = make_source(PAR_ROWS)
    result = source.fetch([make_issuer("TSLA", "US88160RAG12")])

    assert result.source == "hermes"
    assert result.as_of.date() == TODAY
    (credit,) = result.issuers
    assert credit.bond.security == "US88160RAG12"
    assert credit.bond.z_spread_bps == pytest.approx(280.0, abs=1.0)
    assert credit.bond.coupon == 6.0
    assert credit.bond.maturity == dt.date(2031, 7, 20)
    assert any("G-spread proxy" in note for note in credit.quality_notes)

    assert [point.date for point in result.history] == [dt.date(2026, 7, 20), TODAY]
    assert all(point.instrument == "bond" for point in result.history)
    assert result.history[-1].spread_bps == pytest.approx(280.0, abs=1.0)

    assert result.brazil.cds_5y_bps == 180.0
    assert result.brazil.bond_security == BRAZIL_ISIN


def test_unmatched_and_unmapped_issuers_fail_with_reasons():
    source, _ = make_source(PAR_ROWS)
    result = source.fetch([
        make_issuer("TSLA", "US88160RAG12"),
        make_issuer("NOISIN", None),
        make_issuer("GONE", "XS0000000000"),
    ])
    assert "no isin" in result.failures["NOISIN"]
    assert "not in the Hermes window" in result.failures["GONE"]
    assert len(result.issuers) == 1


def test_unpriceable_bond_gets_note_not_spread():
    rows = PAR_ROWS + [bond_row("US00000XX000", "2026-07-21", 0.0, 4.0, "2030-01-01")]
    source, _ = make_source(rows)
    result = source.fetch([make_issuer("ZERO", "US00000XX000")])
    (credit,) = result.issuers
    assert credit.bond.z_spread_bps is None
    assert any("no usable EoD price" in note for note in credit.quality_notes)


def test_missing_brazil_benchmark_yields_no_spread():
    source, _ = make_source(PAR_ROWS, brazil_isin=None)
    result = source.fetch([make_issuer("TSLA", "US88160RAG12")])
    (credit,) = result.issuers
    assert credit.bond.z_spread_bps is None
    assert any("no Brazil benchmark" in note for note in credit.quality_notes)
    assert result.brazil.z_spread_bps is None


def test_http_error_becomes_hermes_unavailable():
    def failing_fetcher(url: str, headers: dict) -> bytes:
        raise json.JSONDecodeError("bad", "", 0)

    client = HermesClient("https://hermes.example", token="tok", fetcher=failing_fetcher)
    source = HermesSource(client, brazil_isin=None, today=TODAY)
    with pytest.raises(HermesUnavailable):
        source.fetch([make_issuer("TSLA", "US88160RAG12")])
