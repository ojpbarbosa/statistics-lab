"""BQuant-side exporter for the Issuer Opportunity Screener.

Run this INSIDE a BQuant notebook (BQNT <GO> on the Terminal): bql only
exists there. It queries server-side (different entitlements from the
Desktop API, so the DAPI workflow-review gate does not apply), and writes
an export directory you download and drop into the app's
data/bquant_export/ folder (or wherever IOS_BQUANT_EXPORT points).

Usage in a BQNT notebook cell:

    %run bquant_export.py            # after uploading this file and universe.csv

or paste the whole file into a cell. Upload data/universe.csv next to it
first (Jupyter's upload button), and download the resulting
bquant_export/ directory when it finishes.

NOTE: BQL item names below are best-effort and marked where they may need
adjustment; if one errors, check the BQL editor's autocomplete (or DOCS
BQL) for the current name and adjust in one place.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

import bql  # only importable inside BQuant

UNIVERSE_CSV = Path("universe.csv")
OUT_DIR = Path("bquant_export")
HISTORY_WEEKS = 52
TENOR_MIN_YEARS, TENOR_MAX_YEARS = 3.0, 10.0

bq = bql.Service()


def read_universe() -> list[dict]:
    with open(UNIVERSE_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def single_value(response) -> dict:
    """bql response -> {security: value} for a one-item request."""
    frame = response[0].df()
    return dict(zip(frame.index, frame.iloc[:, -1]))


def issuer_bond(ticker: str) -> dict | None:
    """Best senior unsecured USD bond in the tenor window, closest to 5y.

    Universe: bonds of the issuer's credit family. `bondsuniv` /
    `bq.univ.bonds` naming can differ by BQL version; adjust if needed.
    """
    universe = bq.univ.bonds(f"{ticker} Corp")  # ADJUST if your BQL wants an equity/figi seed
    fields = {
        "crncy": bq.data.crncy(),
        "payment_rank": bq.data.payment_rank(),
        "maturity": bq.data.maturity(),
        "amt_out": bq.data.amt_outstanding(),
        "z": bq.data.spread(spread_type="Z"),  # ADJUST: some versions expose zspread()
        "px": bq.data.px_last(),
        "cpn": bq.data.cpn(),
    }
    try:
        response = bq.execute(bql.Request(universe, fields))
    except Exception as exc:  # noqa: BLE001: one issuer must not stop the export
        print(f"{ticker}: bond query failed: {exc}")
        return None
    frames = {item.name: item.df() for item in response}
    merged = None
    for name, frame in frames.items():
        column = frame.rename(columns={frame.columns[-1]: name})[[name]]
        merged = column if merged is None else merged.join(column, how="outer")
    if merged is None or merged.empty:
        return None

    today = dt.date.today()
    best, best_key = None, None
    for security, row in merged.iterrows():
        rank = str(row.get("payment_rank") or "").lower()
        senior = "unsecured" in rank or "preferred" in rank
        if str(row.get("crncy")) != "USD" or not senior:
            continue
        maturity = row.get("maturity")
        maturity = maturity.date() if hasattr(maturity, "date") else maturity
        if maturity is None:
            continue
        years = (maturity - today).days / 365.25
        if not TENOR_MIN_YEARS <= years <= TENOR_MAX_YEARS:
            continue
        key = (abs(years - 5.0), -(row.get("amt_out") or 0.0))
        if best_key is None or key < best_key:
            best_key = key
            best = {
                "bond_security": str(security),
                "bond_z_spread_bps": row.get("z"),
                "bond_last_price": row.get("px"),
                "bond_maturity": maturity.isoformat(),
                "bond_coupon": row.get("cpn"),
            }
    return best


def cds_quote(security: str) -> float | None:
    try:
        response = bq.execute(bql.Request(security, {"px": bq.data.px_last()}))
        value = single_value(response).get(security)
        return float(value) if value is not None else None
    except Exception:  # noqa: BLE001
        return None


def cds_5y(ticker: str) -> tuple[str | None, float | None]:
    security = f"{ticker} CDS USD SR 5Y D14 Corp"
    value = cds_quote(security)
    return (security, value) if value is not None else (None, None)


def spread_history(security: str) -> list[tuple[str, float]]:
    try:
        item = bq.data.px_last(dates=bq.func.range("-1y", "0d"), frq="W")
        response = bq.execute(bql.Request(security, {"px": item}))
        frame = response[0].df()
        return [
            (str(row["DATE"])[:10], float(row["px"]))
            for _, row in frame.reset_index().iterrows()
            if row.get("px") is not None
        ]
    except Exception:  # noqa: BLE001
        return []


def ratings(security: str) -> dict:
    items = {
        "rating_moody": bq.data.rating_moody(),  # ADJUST: alt names rating('MOODY') etc.
        "rating_sp": bq.data.rating_sp(),
        "rating_fitch": bq.data.rating_fitch(),
        "rating_composite": bq.data.rating_bloomberg_composite(),
    }
    out: dict = {}
    for name, item in items.items():
        try:
            response = bq.execute(bql.Request(security, {name: item}))
            value = single_value(response).get(security)
            if value:
                out[name] = str(value)
        except Exception:  # noqa: BLE001
            continue
    return out


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    universe = read_universe()
    issuer_rows, history_rows = [], []

    for i, entry in enumerate(universe, start=1):
        ticker = entry["ticker"].strip()
        print(f"({i}/{len(universe)}) {ticker}")
        if entry.get("cds_ticker"):
            cds_security = entry["cds_ticker"].strip()
            cds_value = cds_quote(cds_security)
        else:
            cds_security, cds_value = cds_5y(ticker)
        bond = issuer_bond(ticker) or {}
        rating_source_security = bond.get("bond_security") or cds_security or f"{ticker} Corp"
        rating_values = ratings(rating_source_security)

        issuer_rows.append(
            {
                "ticker": ticker,
                "cds_5y_bps": cds_value,
                "cds_security": cds_security,
                **{key: bond.get(key) for key in ("bond_security", "bond_z_spread_bps", "bond_last_price", "bond_maturity", "bond_coupon")},
                **rating_values,
                "equity_ticker": entry.get("equity_ticker") or f"{ticker} US Equity",
                "px_chg_3m_pct": None,  # optional: bq.data.chg_pct(period='3m') on the equity
                "px_chg_12m_pct": None,
                "rec_balance": None,
            }
        )
        spread_security = cds_security or bond.get("bond_security")
        if spread_security:
            instrument = "cds" if cds_security else "bond"
            for date, value in spread_history(spread_security):
                history_rows.append({"ticker": ticker, "date": date, "spread_bps": value, "instrument": instrument})

    brazil_security = "BRAZIL CDS USD SR 5Y D14 Corp"
    _, brazil_cds = cds_5y("BRAZIL")
    brazil_ratings = ratings(brazil_security)
    with open(OUT_DIR / "brazil.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["cds_5y_bps", "z_spread_bps", "rating_sp", "bond_security"])
        writer.writeheader()
        writer.writerow(
            {
                "cds_5y_bps": brazil_cds,
                "z_spread_bps": None,
                "rating_sp": brazil_ratings.get("rating_sp"),
                "bond_security": None,
            }
        )

    issuer_fields = list(issuer_rows[0].keys()) if issuer_rows else []
    with open(OUT_DIR / "issuers.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=issuer_fields)
        writer.writeheader()
        writer.writerows(issuer_rows)
    with open(OUT_DIR / "history.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ticker", "date", "spread_bps", "instrument"])
        writer.writeheader()
        writer.writerows(history_rows)
    (OUT_DIR / "meta.json").write_text(
        json.dumps({"as_of": dt.datetime.now().isoformat(timespec="seconds")}), encoding="utf-8"
    )
    print(f"export complete: {OUT_DIR}/ (download this directory)")


if __name__ == "__main__":
    main()
