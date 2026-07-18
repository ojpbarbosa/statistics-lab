"""Versioned, append-only parquet snapshot store."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from issuer_opportunity_screener.sources.base import FetchResult, UniverseIssuer

SNAPSHOT_FILE = "snapshot.parquet"
HISTORY_FILE = "history.parquet"
MANIFEST_FILE = "manifest.json"
COVERAGE_COLUMNS = ["cds_5y_bps", "bond_z_spread_bps", "bond_last_price", "rating_sp", "ratings_all", "equity_ticker"]


@dataclass
class Snapshot:
    directory: Path
    frame: pd.DataFrame
    history: pd.DataFrame
    manifest: dict


def _build_frame(universe: list[UniverseIssuer], result: FetchResult) -> pd.DataFrame:
    credit_by_ticker = {c.ticker: c for c in result.issuers}
    rows = []
    for u in universe:
        row: dict = {
            "issuer": u.issuer,
            "ticker": u.ticker,
            "basket": u.basket,
            "country": u.country,
            "sector": u.sector,
            "recognition_score": u.recognition_score,
            "internal_rating": u.internal_rating,
            "cds_5y_bps": None,
            "cds_liquidity_score": None,
            "cds_security": None,
            "bond_security": None,
            "bond_z_spread_bps": None,
            "bond_last_price": None,
            "bond_maturity": None,
            "bond_coupon": None,
            "rating_moody": None,
            "rating_sp": None,
            "rating_fitch": None,
            "ratings_all": None,
            "equity_ticker": None,
            "px_chg_3m_pct": None,
            "px_chg_12m_pct": None,
            "rec_balance": None,
            "quality_notes": "",
        }
        credit = credit_by_ticker.get(u.ticker)
        if credit is not None:
            row.update(
                cds_5y_bps=credit.cds_5y_bps,
                cds_liquidity_score=credit.cds_liquidity_score,
                cds_security=credit.cds_security,
                bond_security=credit.bond.security,
                bond_z_spread_bps=credit.bond.z_spread_bps,
                bond_last_price=credit.bond.last_price,
                bond_maturity=credit.bond.maturity,
                bond_coupon=credit.bond.coupon,
                rating_moody=credit.rating_moody,
                rating_sp=credit.rating_sp,
                rating_fitch=credit.rating_fitch,
                ratings_all=json.dumps(credit.ratings) if credit.ratings else None,
                equity_ticker=credit.equity.equity_ticker,
                px_chg_3m_pct=credit.equity.price_change_3m_pct,
                px_chg_12m_pct=credit.equity.price_change_12m_pct,
                rec_balance=credit.equity.recommendation_balance,
                quality_notes="; ".join(credit.quality_notes),
            )
        rows.append(row)
    return pd.DataFrame(rows)


def write_snapshot(root: Path, universe: list[UniverseIssuer], result: FetchResult) -> Path:
    directory = Path(root) / result.as_of.strftime("%Y-%m-%dT%H%M%S")
    directory.mkdir(parents=True, exist_ok=False)

    frame = _build_frame(universe, result)
    frame.to_parquet(directory / SNAPSHOT_FILE, index=False)

    history = pd.DataFrame(
        [{"ticker": h.ticker, "date": h.date, "spread_bps": h.spread_bps, "instrument": h.instrument} for h in result.history],
        columns=["ticker", "date", "spread_bps", "instrument"],
    )
    history.to_parquet(directory / HISTORY_FILE, index=False)

    manifest = {
        "as_of": result.as_of.isoformat(),
        "source": result.source,
        "issuer_count": len(universe),
        "fetched_count": len(result.issuers),
        "failures": result.failures,
        "partial": bool(result.failures),
        "brazil": asdict(result.brazil),
        "coverage": {col: round(float(frame[col].notna().mean()), 4) for col in COVERAGE_COLUMNS},
    }
    (directory / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return directory


def list_snapshots(root: Path) -> list[Path]:
    root = Path(root)
    if not root.exists():
        return []
    return sorted(d for d in root.iterdir() if d.is_dir() and (d / MANIFEST_FILE).exists())


def latest(root: Path) -> Path | None:
    snaps = list_snapshots(root)
    return snaps[-1] if snaps else None


def load_snapshot(directory: Path) -> Snapshot:
    directory = Path(directory)
    return Snapshot(
        directory=directory,
        frame=pd.read_parquet(directory / SNAPSHOT_FILE),
        history=pd.read_parquet(directory / HISTORY_FILE),
        manifest=json.loads((directory / MANIFEST_FILE).read_text(encoding="utf-8")),
    )
