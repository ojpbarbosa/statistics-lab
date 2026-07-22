"""Universe lifecycle: add names, quarantine unscored ones, restore them.

The universe stays a desk-owned CSV; every mutation validates the whole file
through load_universe before replacing it, and quarantined names move to a
sibling CSV with the reason and timestamp so nothing is silently lost.
"""
from __future__ import annotations

import csv
from pathlib import Path

from issuer_opportunity_screener.log import get_logger
from issuer_opportunity_screener.scoring import IssuerScore
from issuer_opportunity_screener.snapshots import Snapshot
from issuer_opportunity_screener.universe import load_universe

log = get_logger("universe")

# Every column load_universe reads. A column missing here is silently dropped
# from every row the next time the file is rewritten.
UNIVERSE_FIELDS = [
    "issuer", "ticker", "basket", "country", "sector",
    "recognition_score", "internal_rating", "equity_ticker", "cds_ticker",
    "isin", "state_linked",
]
QUARANTINE_FIELDS = UNIVERSE_FIELDS + ["quarantine_reason", "quarantined_at"]


def _read_rows(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_rows(path: Path, rows: list[dict], fields: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        # csv defaults to CRLF, which would rewrite every line of the file the
        # first time the desk adds a name through the form.
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") or "" for field in fields})


def _validated_replace(universe_path: Path, rows: list[dict]) -> None:
    """Write rows to a temp file, validate via load_universe, then replace."""
    universe_path = Path(universe_path)
    temp_path = universe_path.with_suffix(".tmp.csv")
    _write_rows(temp_path, rows, UNIVERSE_FIELDS)
    try:
        load_universe(temp_path)  # raises UniverseError with offending rows named
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    temp_path.replace(universe_path)


def append_issuer(universe_path: Path, new_row: dict) -> None:
    """Add one issuer; the whole file is re-validated before anything changes."""
    rows = _read_rows(universe_path)
    rows.append({field: str(new_row.get(field, "") or "").strip() for field in UNIVERSE_FIELDS})
    _validated_replace(universe_path, rows)
    log.info(f"added {new_row.get('ticker')} to {universe_path}")


def unscored_reasons(snap: Snapshot, scores: list[IssuerScore]) -> dict[str, str]:
    """ticker -> reason for every universe name the scoring skipped."""
    scored = {score.ticker for score in scores}
    failures = snap.manifest.get("failures", {})
    reasons: dict[str, str] = {}
    for row in snap.frame.itertuples():
        if row.ticker in scored:
            continue
        if row.ticker in failures:
            reasons[row.ticker] = f"fetch failed: {failures[row.ticker]}"
        elif isinstance(row.quality_notes, str) and row.quality_notes:
            reasons[row.ticker] = f"no spread resolved: {row.quality_notes[:300]}"
        else:
            reasons[row.ticker] = "no spread resolved (no CDS quote and no eligible bond)"
    return reasons


def quarantine_unscored(
    universe_path: Path,
    quarantine_path: Path,
    snap: Snapshot,
    scores: list[IssuerScore],
) -> list[str]:
    """Move every unscored name out of the universe into the quarantine file,
    with the reason and the snapshot timestamp. Returns the moved tickers."""
    reasons = unscored_reasons(snap, scores)
    if not reasons:
        return []
    rows = _read_rows(universe_path)
    keep = [row for row in rows if row.get("ticker") not in reasons]
    moved = [row for row in rows if row.get("ticker") in reasons]
    if not moved:
        return []
    quarantined = _read_rows(quarantine_path)
    already = {row.get("ticker") for row in quarantined}
    for row in moved:
        if row.get("ticker") in already:
            continue
        quarantined.append(
            {
                **row,
                "quarantine_reason": reasons[row["ticker"]],
                "quarantined_at": snap.manifest.get("as_of", ""),
            }
        )
    _validated_replace(universe_path, keep)
    _write_rows(quarantine_path, quarantined, QUARANTINE_FIELDS)
    tickers = [row["ticker"] for row in moved]
    log.warn(f"quarantined {len(tickers)} unscored name(s): {', '.join(sorted(tickers))}")
    return tickers


def restore_issuer(universe_path: Path, quarantine_path: Path, ticker: str) -> None:
    """Move one name back from quarantine into the universe."""
    quarantined = _read_rows(quarantine_path)
    match = [row for row in quarantined if row.get("ticker") == ticker]
    if not match:
        raise ValueError(f"{ticker} is not in the quarantine file")
    rows = _read_rows(universe_path)
    rows.append({field: match[0].get(field, "") for field in UNIVERSE_FIELDS})
    _validated_replace(universe_path, rows)
    _write_rows(quarantine_path, [row for row in quarantined if row.get("ticker") != ticker], QUARANTINE_FIELDS)
    log.info(f"restored {ticker} from quarantine")
