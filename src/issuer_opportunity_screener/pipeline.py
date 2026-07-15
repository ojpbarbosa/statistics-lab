"""Orchestrates one data pull: universe -> source.fetch -> snapshot dir."""
from __future__ import annotations

from pathlib import Path

from issuer_opportunity_screener.snapshots import write_snapshot
from issuer_opportunity_screener.sources.base import CreditDataSource
from issuer_opportunity_screener.universe import load_universe


def run_pipeline(universe_path: Path, source: CreditDataSource, snapshots_root: Path) -> Path:
    issuers = load_universe(universe_path)
    result = source.fetch(issuers)
    return write_snapshot(snapshots_root, issuers, result)
