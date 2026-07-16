"""Ingest a BQuant (BQL) export as a credit data source.

bql only runs inside Bloomberg's BQuant environment, so the flow is:
1. run `bquant/bquant_export.py` in a BQNT notebook (server-side BQL,
   different entitlements from the Desktop API);
2. download the export directory it writes;
3. point IOS_SOURCE=bquant (+ IOS_BQUANT_EXPORT=<dir>) at it and Refresh.

Expected files in the export directory:
- meta.json: {"as_of": ISO timestamp}
- issuers.csv: ticker, cds_5y_bps, cds_security, bond_security,
  bond_z_spread_bps, bond_last_price, bond_maturity (YYYY-MM-DD),
  bond_coupon, rating_moody, rating_sp, rating_fitch, rating_composite,
  equity_ticker, px_chg_3m_pct, px_chg_12m_pct, rec_balance
- history.csv: ticker, date (YYYY-MM-DD), spread_bps, instrument (cds|bond)
- brazil.csv: one row: cds_5y_bps, z_spread_bps, rating_sp, bond_security
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

from issuer_opportunity_screener.log import get_logger
from issuer_opportunity_screener.sources.base import (
    BondSnapshot,
    BrazilBenchmark,
    EquityOverlay,
    FetchResult,
    HistoryPoint,
    IssuerCredit,
    UniverseIssuer,
)

log = get_logger("bquant")

EXPORT_FILES = ("meta.json", "issuers.csv", "history.csv", "brazil.csv")


class BquantExportMissing(RuntimeError):
    """The export directory is absent or incomplete."""


def _opt_float(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _opt_str(value) -> str | None:
    value = (value or "").strip() if isinstance(value, str) else value
    return value or None


def _opt_date(value) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


class BquantExportSource:
    name = "bquant"

    def __init__(self, export_dir: Path):
        self.export_dir = Path(export_dir)

    def _require(self, filename: str) -> Path:
        path = self.export_dir / filename
        if not path.exists():
            raise BquantExportMissing(
                f"BQuant export incomplete: {path} not found. Run bquant/bquant_export.py "
                f"in a BQNT notebook and copy its output directory here."
            )
        return path

    def fetch(self, issuers: list[UniverseIssuer]) -> FetchResult:
        for filename in EXPORT_FILES:
            self._require(filename)
        meta = json.loads((self.export_dir / "meta.json").read_text(encoding="utf-8"))
        as_of = dt.datetime.fromisoformat(meta["as_of"])
        log.step(f"ingesting BQuant export from {self.export_dir} (as_of {meta['as_of']})")

        with open(self.export_dir / "issuers.csv", newline="", encoding="utf-8") as f:
            exported = {row["ticker"].strip(): row for row in csv.DictReader(f) if row.get("ticker")}

        credits: list[IssuerCredit] = []
        failures: dict[str, str] = {}
        for issuer in issuers:
            row = exported.get(issuer.ticker)
            if row is None:
                failures[issuer.ticker] = "not present in the BQuant export"
                continue
            ratings = {
                agency: value
                for agency, value in (
                    ("moody", _opt_str(row.get("rating_moody"))),
                    ("sp", _opt_str(row.get("rating_sp"))),
                    ("fitch", _opt_str(row.get("rating_fitch"))),
                    ("composite", _opt_str(row.get("rating_composite"))),
                )
                if value
            }
            credit = IssuerCredit(
                ticker=issuer.ticker,
                cds_5y_bps=_opt_float(row.get("cds_5y_bps")),
                cds_liquidity_score=100.0 if _opt_float(row.get("cds_5y_bps")) is not None else None,
                cds_security=_opt_str(row.get("cds_security")),
                bond=BondSnapshot(
                    security=_opt_str(row.get("bond_security")),
                    z_spread_bps=_opt_float(row.get("bond_z_spread_bps")),
                    last_price=_opt_float(row.get("bond_last_price")),
                    maturity=_opt_date(row.get("bond_maturity")),
                    coupon=_opt_float(row.get("bond_coupon")),
                ),
                rating_moody=ratings.get("moody"),
                rating_sp=ratings.get("sp"),
                rating_fitch=ratings.get("fitch"),
                ratings=ratings,
                equity=EquityOverlay(
                    equity_ticker=_opt_str(row.get("equity_ticker")),
                    price_change_3m_pct=_opt_float(row.get("px_chg_3m_pct")),
                    price_change_12m_pct=_opt_float(row.get("px_chg_12m_pct")),
                    recommendation_balance=_opt_float(row.get("rec_balance")),
                ),
            )
            if credit.cds_5y_bps is None:
                credit.quality_notes.append("no CDS quote in the BQuant export")
            if credit.bond.security is None:
                credit.quality_notes.append("no bond in the BQuant export")
            if not ratings:
                credit.quality_notes.append("no ratings in the BQuant export")
            credits.append(credit)

        history: list[HistoryPoint] = []
        wanted = {issuer.ticker for issuer in issuers}
        with open(self.export_dir / "history.csv", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ticker = (row.get("ticker") or "").strip()
                date = _opt_date(row.get("date"))
                spread = _opt_float(row.get("spread_bps"))
                if ticker in wanted and date is not None and spread is not None:
                    history.append(HistoryPoint(ticker, date, spread, (row.get("instrument") or "cds").strip()))

        with open(self.export_dir / "brazil.csv", newline="", encoding="utf-8") as f:
            brazil_rows = list(csv.DictReader(f))
        if brazil_rows and _opt_float(brazil_rows[0].get("cds_5y_bps")) is not None:
            brazil_row = brazil_rows[0]
            brazil = BrazilBenchmark(
                cds_5y_bps=float(brazil_row["cds_5y_bps"]),
                z_spread_bps=_opt_float(brazil_row.get("z_spread_bps")),
                rating_sp=_opt_str(brazil_row.get("rating_sp")) or "BB",
                bond_security=_opt_str(brazil_row.get("bond_security")),
                ratings={"sp": _opt_str(brazil_row.get("rating_sp"))} if _opt_str(brazil_row.get("rating_sp")) else {},
            )
        else:
            brazil = BrazilBenchmark(cds_5y_bps=180.0, z_spread_bps=None, rating_sp="BB")
            log.warn("brazil.csv missing or empty; using the 180 bps fallback benchmark")

        log.success(
            f"BQuant export ingested: {len(credits)}/{len(issuers)} issuers, "
            f"{len(history)} history points, {len(failures)} missing"
        )
        return FetchResult(
            as_of=as_of, source=self.name, issuers=credits,
            history=history, brazil=brazil, failures=failures,
        )
