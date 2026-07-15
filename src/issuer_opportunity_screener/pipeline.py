"""Orchestrates one data pull: universe -> source.fetch -> snapshot dir."""
from __future__ import annotations

from pathlib import Path

from issuer_opportunity_screener.log import get_logger
from issuer_opportunity_screener.snapshots import write_snapshot
from issuer_opportunity_screener.sources.base import CreditDataSource
from issuer_opportunity_screener.universe import load_universe

log = get_logger("pipeline")


def run_pipeline(universe_path: Path, source: CreditDataSource, snapshots_root: Path) -> Path:
    log.step(f"loading universe from {universe_path}")
    issuers = load_universe(universe_path)
    log.info(f"{len(issuers)} issuers in universe; fetching via source '{source.name}'")
    result = source.fetch(issuers)
    if result.failures:
        log.warn(f"{len(result.failures)} issuer(s) failed: {', '.join(sorted(result.failures))}")
    directory = write_snapshot(snapshots_root, issuers, result)
    log.success(f"snapshot written: {directory}")
    return directory
