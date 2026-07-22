"""Cross-snapshot movers and rule-based insight callouts.

Pure functions over scored snapshots: no Bloomberg, no disk writes. The
dashboard and the report generator both consume these.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from issuer_opportunity_screener.scoring import (
    IssuerScore,
    history_is_stale,
    screen_frame,
    score_snapshot,
)
from issuer_opportunity_screener.snapshots import Snapshot

MOVE_THRESHOLD_BPS = 15.0
NEAR_MISS_FLOOR_BPS = -40.0
OWN_HISTORY_HIGH_PCT = 90.0


@dataclass(frozen=True)
class Insight:
    kind: str  # tightener | widener | now_viable | lost_viability | new_name | dropped | tier_change | own_history_high | near_miss
    ticker: str
    message: str
    magnitude: float


def _primary_spread(frame: pd.DataFrame) -> pd.Series:
    return frame.cds_5y_bps.fillna(frame.bond_z_spread_bps)


def movers_frame(
    current: pd.DataFrame,
    baseline: pd.DataFrame,
    brazil_now: float | None = None,
    brazil_then: float | None = None,
) -> pd.DataFrame:
    """Per-ticker comparison of two screen frames (from screen_frame).

    Passing the two Brazil levels adds brazil_delta_bps, which is what separates
    a name that moved from a name that stood still while the benchmark moved."""
    now = current.assign(spread_now=_primary_spread(current))[
        ["issuer", "ticker", "basket", "spread_now", "spread_vs_brazil_bps", "viable", "composite", "tier"]
    ].rename(columns={"spread_vs_brazil_bps": "vs_brazil_now", "viable": "viable_now", "composite": "composite_now", "tier": "tier_now"})
    then = baseline.assign(spread_then=_primary_spread(baseline))[
        ["ticker", "spread_then", "spread_vs_brazil_bps", "viable", "composite", "tier"]
    ].rename(columns={"spread_vs_brazil_bps": "vs_brazil_then", "viable": "viable_then", "composite": "composite_then", "tier": "tier_then"})
    merged = now.merge(then, on="ticker", how="outer")
    merged["delta_bps"] = merged.spread_now - merged.spread_then
    if brazil_now is not None and brazil_then is not None:
        merged["brazil_delta_bps"] = float(brazil_now) - float(brazil_then)
    merged["status"] = "both"
    merged.loc[merged.spread_then.isna() & merged.spread_now.notna(), "status"] = "new"
    merged.loc[merged.spread_now.isna() & merged.spread_then.notna(), "status"] = "dropped"
    return merged.sort_values("delta_bps", ascending=False, na_position="last").reset_index(drop=True)


def own_history_percentile(snap: Snapshot, ticker: str, spread_bps: float) -> float | None:
    history = snap.history[snap.history.ticker == ticker].spread_bps.astype(float)
    if len(history) < 12 or history_is_stale(history.tolist()):
        return None
    return 100.0 * (history <= spread_bps).sum() / len(history)


def _flip_attribution(row) -> str:
    """Whether a viability flip was the name or the benchmark. Brazil's own CDS
    moves more than the 20 bps tolerance in a normal week."""
    brazil_delta = getattr(row, "brazil_delta_bps", None)
    issuer_delta = getattr(row, "delta_bps", None)
    if brazil_delta is None or issuer_delta is None or pd.isna(brazil_delta) or pd.isna(issuer_delta):
        return ""
    if abs(brazil_delta) > abs(issuer_delta):
        return (
            f", driven by Brazil moving {brazil_delta:+.0f} bps while the name itself "
            f"moved {issuer_delta:+.0f} bps"
        )
    return f" (the name moved {issuer_delta:+.0f} bps, Brazil {brazil_delta:+.0f} bps)"


def build_insights(
    movers: pd.DataFrame,
    current_snap: Snapshot,
    baseline_label: str,
    limit_per_kind: int = 5,
) -> list[Insight]:
    insights: list[Insight] = []
    both = movers[movers.status == "both"]

    significant = both[both.delta_bps.abs() >= MOVE_THRESHOLD_BPS].dropna(subset=["delta_bps"])
    for row in significant.sort_values("delta_bps").head(limit_per_kind).itertuples():
        insights.append(
            Insight(
                "tightener", row.ticker, magnitude=abs(row.delta_bps),
                message=(
                    f"{row.issuer} ({row.ticker}) tightened {abs(row.delta_bps):.0f} bps since {baseline_label} "
                    f"({row.spread_then:.0f} to {row.spread_now:.0f} bps)"
                ),
            )
        )
    for row in significant.sort_values("delta_bps", ascending=False).head(limit_per_kind).itertuples():
        insights.append(
            Insight(
                "widener", row.ticker, magnitude=abs(row.delta_bps),
                message=(
                    f"{row.issuer} ({row.ticker}) widened {row.delta_bps:.0f} bps since {baseline_label} "
                    f"({row.spread_then:.0f} to {row.spread_now:.0f} bps): potential entry point if the credit is intact"
                ),
            )
        )

    for row in both[(both.viable_now == True) & (both.viable_then == False)].itertuples():  # noqa: E712 (pandas boolean columns)
        insights.append(
            Insight(
                "now_viable", row.ticker, magnitude=float(row.vs_brazil_now or 0),
                message=(
                    f"{row.issuer} ({row.ticker}) became viable vs Brazil "
                    f"(now {row.vs_brazil_now:+.0f} bps){_flip_attribution(row)}"
                ),
            )
        )
    for row in both[(both.viable_now == False) & (both.viable_then == True)].itertuples():  # noqa: E712
        insights.append(
            Insight(
                "lost_viability", row.ticker, magnitude=float(row.vs_brazil_now or 0),
                message=(
                    f"{row.issuer} ({row.ticker}) lost viability vs Brazil "
                    f"(now {row.vs_brazil_now:+.0f} bps){_flip_attribution(row)}"
                ),
            )
        )

    for row in both[both.tier_now != both.tier_then].dropna(subset=["tier_now", "tier_then"]).itertuples():
        insights.append(
            Insight(
                "tier_change", row.ticker, magnitude=abs((row.composite_now or 0) - (row.composite_then or 0)),
                message=(
                    f"{row.issuer} ({row.ticker}) moved Tier {row.tier_then} to Tier {row.tier_now} "
                    f"(composite {row.composite_then:.1f} to {row.composite_now:.1f})"
                ),
            )
        )

    for row in movers[movers.status == "new"].itertuples():
        insights.append(
            Insight("new_name", row.ticker, magnitude=0.0, message=f"{row.issuer} ({row.ticker}) entered the screen")
        )
    for row in movers[movers.status == "dropped"].itertuples():
        insights.append(
            Insight("dropped", row.ticker, magnitude=0.0, message=f"{row.ticker} dropped out of the screen (no spread in the current snapshot)")
        )

    for row in both.dropna(subset=["spread_now"]).itertuples():
        pct = own_history_percentile(current_snap, row.ticker, float(row.spread_now))
        if pct is not None and pct >= OWN_HISTORY_HIGH_PCT:
            insights.append(
                Insight(
                    "own_history_high", row.ticker, magnitude=pct,
                    message=(
                        f"{row.issuer} ({row.ticker}) trades at the {pct:.0f}th percentile of its own 1y range "
                        f"({row.spread_now:.0f} bps): historically wide for the name"
                    ),
                )
            )

    near = both[(both.viable_now == False) & (both.vs_brazil_now < -20) & (both.vs_brazil_now >= NEAR_MISS_FLOOR_BPS)]  # noqa: E712
    for row in near.itertuples():
        insights.append(
            Insight(
                "near_miss", row.ticker, magnitude=float(row.vs_brazil_now),
                message=(
                    f"{row.issuer} ({row.ticker}) is {abs(row.vs_brazil_now) - 20:.0f} bps away from the "
                    f"edge-case tolerance ({row.vs_brazil_now:+.0f} bps vs Brazil)"
                ),
            )
        )
    return insights


def scored_frames(current: Snapshot, baseline: Snapshot) -> tuple[pd.DataFrame, pd.DataFrame, list[IssuerScore], list[IssuerScore]]:
    """Score both snapshots and return their screen frames plus scores."""
    scores_now = score_snapshot(current)
    scores_then = score_snapshot(baseline)
    return screen_frame(current, scores_now), screen_frame(baseline, scores_then), scores_now, scores_then
