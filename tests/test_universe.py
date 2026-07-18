from pathlib import Path

import pytest

from issuer_opportunity_screener.universe import (
    BASKETS,
    UniverseError,
    load_universe,
)

REPO_UNIVERSE = Path(__file__).resolve().parents[1] / "data" / "universe.csv"

VALID_HEADER = "issuer,ticker,basket,country,sector,recognition_score,internal_rating\n"


def write(tmp_path, body):
    p = tmp_path / "universe.csv"
    p.write_text(VALID_HEADER + body, encoding="utf-8")
    return p


def test_loads_repo_universe():
    issuers = load_universe(REPO_UNIVERSE)
    assert len(issuers) >= 80
    tickers = [i.ticker for i in issuers]
    assert len(tickers) == len(set(tickers))
    assert all(i.basket in BASKETS for i in issuers)
    tesla = next(i for i in issuers if i.ticker == "TSLA")
    assert tesla.issuer == "Tesla"
    assert tesla.recognition_score == 95.0
    assert tesla.internal_rating is None


def test_duplicate_ticker_rejected(tmp_path):
    p = write(tmp_path, "A,TSLA,Brazil,Brazil,Energy,50,\nB,TSLA,Brazil,Brazil,Energy,50,\n")
    with pytest.raises(UniverseError, match="duplicate ticker 'TSLA'"):
        load_universe(p)


def test_unknown_basket_rejected(tmp_path):
    p = write(tmp_path, "A,TSLA,Weird Basket,US,Energy,50,\n")
    with pytest.raises(UniverseError, match="unknown basket 'Weird Basket'"):
        load_universe(p)


def test_recognition_out_of_range_rejected(tmp_path):
    p = write(tmp_path, "A,TSLA,Brazil,Brazil,Energy,150,\n")
    with pytest.raises(UniverseError, match="recognition_score"):
        load_universe(p)


def test_empty_file_rejected(tmp_path):
    p = tmp_path / "universe.csv"
    p.write_text(VALID_HEADER, encoding="utf-8")
    with pytest.raises(UniverseError, match="empty"):
        load_universe(p)


def test_internal_rating_kept_when_present(tmp_path):
    p = write(tmp_path, "A,TSLA,Brazil,Brazil,Energy,50,BB+\n")
    assert load_universe(p)[0].internal_rating == "BB+"


def test_handle_overrides_default_to_none(tmp_path):
    p = write(tmp_path, "A,TSLA,Brazil,Brazil,Energy,50,\n")
    issuer = load_universe(p)[0]
    assert issuer.equity_ticker is None
    assert issuer.cds_ticker is None


def test_handle_overrides_kept_when_present(tmp_path):
    p = tmp_path / "universe.csv"
    p.write_text(
        "issuer,ticker,basket,country,sector,recognition_score,internal_rating,equity_ticker,cds_ticker\n"
        "AB InBev,ABIBB,Brazil,Brazil,Energy,50,,ABI BB Equity,ABIBB CDS EUR SR 5Y D14 Corp\n",
        encoding="utf-8",
    )
    issuer = load_universe(p)[0]
    assert issuer.equity_ticker == "ABI BB Equity"
    assert issuer.cds_ticker == "ABIBB CDS EUR SR 5Y D14 Corp"
