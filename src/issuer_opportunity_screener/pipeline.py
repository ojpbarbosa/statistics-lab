"""Orchestrates one data pull: universe -> source.fetch -> snapshot dir."""
from __future__ import annotations

import os
from pathlib import Path

from issuer_opportunity_screener.log import get_logger
from issuer_opportunity_screener.snapshots import load_snapshot, write_snapshot
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
    directory = write_snapshot(snapshots_root, issuers, result, universe_path=universe_path)
    log.success(f"snapshot written: {directory}")

    # Opt-in hygiene: move unscored names to the quarantine file so the next
    # snapshot only carries names that actually produce a spread. Keep this
    # OFF while data access is still being unblocked, or one gated run would
    # empty the universe.
    if os.environ.get("IOS_AUTO_QUARANTINE") == "1" and result.source == "bloomberg":
        from issuer_opportunity_screener.scoring import score_snapshot
        from issuer_opportunity_screener.universe_admin import quarantine_unscored

        snap = load_snapshot(directory)
        moved = quarantine_unscored(
            universe_path, Path(universe_path).with_name("universe_quarantine.csv"), snap, score_snapshot(snap)
        )
        if moved:
            log.warn(f"auto-quarantine removed {len(moved)} name(s) from the universe for the next run")
    return directory
