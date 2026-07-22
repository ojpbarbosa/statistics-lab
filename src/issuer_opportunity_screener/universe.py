"""Load and validate the issuer universe from data/universe.csv."""
from __future__ import annotations

import csv
from pathlib import Path

from issuer_opportunity_screener.sources.base import UniverseIssuer

BASKETS = {
    "Global Communications and Digital Platforms",
    "Global Consumer and Leisure",
    "Global Industrials, Autos, and Aerospace",
    "Global Energy and Materials",
    "Global Financials",
    "Global Healthcare and Pharma",
    "Latin America",
    "Brazil",
}


class UniverseError(ValueError):
    """The universe file is malformed; message names the offending rows."""


def load_universe(path: Path) -> list[UniverseIssuer]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise UniverseError(f"{path}: universe file is empty")
    issuers: list[UniverseIssuer] = []
    errors: list[str] = []
    seen: set[str] = set()
    for lineno, row in enumerate(rows, start=2):
        ticker = (row.get("ticker") or "").strip()
        if not ticker:
            errors.append(f"line {lineno}: missing ticker")
            continue
        if ticker in seen:
            errors.append(f"line {lineno}: duplicate ticker {ticker!r}")
            continue
        seen.add(ticker)
        basket = (row.get("basket") or "").strip()
        if basket not in BASKETS:
            errors.append(f"line {lineno}: unknown basket {basket!r}")
            continue
        try:
            recognition = float(row.get("recognition_score") or "")
        except ValueError:
            errors.append(f"line {lineno}: recognition_score must be a number")
            continue
        if not 0.0 <= recognition <= 100.0:
            errors.append(f"line {lineno}: recognition_score must be within 0-100")
            continue
        issuers.append(
            UniverseIssuer(
                issuer=(row.get("issuer") or "").strip(),
                ticker=ticker,
                basket=basket,
                country=(row.get("country") or "").strip(),
                sector=(row.get("sector") or "").strip(),
                recognition_score=recognition,
                internal_rating=(row.get("internal_rating") or "").strip() or None,
                equity_ticker=(row.get("equity_ticker") or "").strip() or None,
                cds_ticker=(row.get("cds_ticker") or "").strip() or None,
                isin=(row.get("isin") or "").strip() or None,
                state_linked=(row.get("state_linked") or "").strip().lower() in {"yes", "true", "y", "1"},
            )
        )
    if errors:
        raise UniverseError(f"{path}: " + "; ".join(errors))
    return issuers
