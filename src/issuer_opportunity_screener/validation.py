"""Validation of the screen itself, per the methodology's Validation Plan.

The composite is documented and replicable, but until this module existed
nothing checked whether it was *stable*, whether the weights were load-bearing,
or whether a shortlist was actually diversified. Four questions:

- rank_stability: does the ranking agree with itself between two snapshots?
- weight_sensitivity: would a different weighting produce a different answer?
- concentration: is the shortlist a basket, or the same bet ten times?
- spread_correlation: do the shortlisted names move together?

Pure functions over snapshots and screen frames: no Bloomberg, no disk writes.
"""
from __future__ import annotations

import pandas as pd

from issuer_opportunity_screener.scoring import WEIGHTS, score_snapshot, screen_frame
from issuer_opportunity_screener.snapshots import Snapshot

CONCENTRATION_HHI_LIMIT = 0.30  # above this, one bucket dominates the shortlist
CONCENTRATION_SHARE_LIMIT = 0.50
MIN_CORRELATION_POINTS = 12
CONCENTRATION_DIMENSIONS = ("basket", "country", "sector")


def spearman(a: pd.Series, b: pd.Series) -> float | None:
    """Rank correlation, computed as Pearson on ranks.

    pandas delegates method="spearman" to scipy, which this project does not
    depend on. The definition is the same and this keeps the dependency list to
    what the pipeline actually needs."""
    paired = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(paired) < 2:
        return None
    value = paired.a.rank().corr(paired.b.rank())
    return float(value) if pd.notna(value) else None


def rank_stability(current: pd.DataFrame, baseline: pd.DataFrame) -> dict:
    """Agreement between two screen frames.

    A screen that reshuffles week to week is measuring noise. Spearman is on
    composite scores, so it reads rank agreement rather than level agreement."""
    merged = current.merge(baseline, on="ticker", suffixes=("_now", "_then"))
    names = len(merged)
    if names == 0:
        return {
            "names_in_both": 0, "spearman": None, "tier_changes": None,
            "viability_flips": None, "mean_abs_composite_move": None,
        }
    rank_agreement = spearman(merged.composite_now, merged.composite_then)
    return {
        "names_in_both": names,
        "spearman": rank_agreement,
        "tier_changes": int((merged.tier_now != merged.tier_then).sum()),
        "viability_flips": int((merged.viable_now != merged.viable_then).sum()),
        "mean_abs_composite_move": float((merged.composite_now - merged.composite_then).abs().mean()),
    }


def _scenarios(perturbation: float) -> list[tuple[str, dict[str, float]]]:
    """One scenario per block moved up and down, plus two combined tilts.

    Deterministic and nameable on purpose: the desk should be able to read the
    worst case and know exactly which weighting produced it."""
    out: list[tuple[str, dict[str, float]]] = []
    for block in WEIGHTS:
        for direction, sign in (("up", 1.0), ("down", -1.0)):
            weights = dict(WEIGHTS)
            weights[block] = max(0.0, weights[block] * (1.0 + sign * perturbation))
            out.append((f"{block} {direction} {perturbation:.0%}", weights))

    spread_led = dict(WEIGHTS)
    spread_led["Credit and Spread Attractiveness"] *= 1.0 + perturbation
    spread_led["Credit Quality and Risk"] *= 1.0 - perturbation
    spread_led["Recognition and Client Fit"] *= 1.0 - perturbation
    out.append((f"spread-led tilt (+/-{perturbation:.0%})", spread_led))

    quality_led = dict(WEIGHTS)
    quality_led["Credit and Spread Attractiveness"] *= 1.0 - perturbation
    quality_led["Credit Quality and Risk"] *= 1.0 + perturbation
    quality_led["Recognition and Client Fit"] *= 1.0 + perturbation
    out.append((f"quality-led tilt (+/-{perturbation:.0%})", quality_led))
    return out


def weight_sensitivity(snap: Snapshot, perturbation: float = 0.10, top_n: int = 10) -> dict:
    """How much the ranking depends on the weights rather than the evidence.

    For each scenario: the rank correlation against the documented weights, and
    the share of the base top-N that survives. High overlap and high correlation
    mean the weights are a presentation choice; low means they are the answer."""
    base = score_snapshot(snap)
    if not base:
        return {"scenarios": 0, "per_scenario": [], "mean_spearman": None,
                "min_spearman": None, "min_top_n_overlap": None, "top_n": top_n,
                "perturbation": perturbation}

    base_series = pd.Series({s.ticker: s.composite for s in base})
    base_top = list(base_series.sort_values(ascending=False).head(top_n).index)

    per_scenario = []
    for label, weights in _scenarios(perturbation):
        scores = score_snapshot(snap, weights=weights)
        series = pd.Series({s.ticker: s.composite for s in scores}).reindex(base_series.index)
        rank_agreement = spearman(base_series, series)
        top = list(series.sort_values(ascending=False).head(top_n).index)
        overlap = len(set(top) & set(base_top)) / max(1, len(base_top))
        per_scenario.append({
            "label": label,
            "weights": {block: round(value, 4) for block, value in weights.items()},
            "spearman": rank_agreement,
            "top_n_overlap": overlap,
            "entered": sorted(set(top) - set(base_top)),
            "left": sorted(set(base_top) - set(top)),
        })

    correlations = [row["spearman"] for row in per_scenario if row["spearman"] is not None]
    overlaps = [row["top_n_overlap"] for row in per_scenario]
    return {
        "scenarios": len(per_scenario),
        "per_scenario": per_scenario,
        "top_n": top_n,
        "perturbation": perturbation,
        "mean_spearman": sum(correlations) / len(correlations) if correlations else None,
        "min_spearman": min(correlations) if correlations else None,
        "min_top_n_overlap": min(overlaps) if overlaps else None,
    }


def _bucket_stats(values: pd.Series) -> dict:
    shares = values.value_counts(normalize=True)
    return {
        "hhi": float((shares**2).sum()),
        "top_share": float(shares.iloc[0]),
        "largest": str(shares.index[0]),
        "buckets": int(len(shares)),
        "shares": {str(k): float(v) for k, v in shares.items()},
    }


def concentration(frame: pd.DataFrame, top_n: int = 10) -> dict:
    """Concentration of the shortlist by basket, country, and sector.

    The screen ranks names one at a time, but the product is a basket. Ten Tier A
    names all in one country is the same bet ten times. HHI of 1.0 is a single
    bucket; 1/n is perfectly even."""
    shortlist = frame.head(top_n)
    report: dict = {"top_n": top_n, "names": len(shortlist), "warnings": []}
    if shortlist.empty:
        return report
    for dimension in CONCENTRATION_DIMENSIONS:
        if dimension not in shortlist.columns:
            continue
        values = shortlist[dimension].dropna().astype(str)
        if values.empty:
            continue
        stats = _bucket_stats(values)
        report[dimension] = stats
        if stats["hhi"] > CONCENTRATION_HHI_LIMIT or stats["top_share"] > CONCENTRATION_SHARE_LIMIT:
            report["warnings"].append(
                f"{dimension} concentration: {stats['top_share']:.0%} of the top {len(shortlist)} "
                f"in {stats['largest']!r} (HHI {stats['hhi']:.2f})"
            )
    return report


def spread_correlation(
    snap: Snapshot,
    tickers: list[str],
    min_points: int = MIN_CORRELATION_POINTS,
) -> dict:
    """Mean pairwise correlation of weekly spread changes across the shortlist.

    Levels trend and would correlate on trend alone, so this is on changes. Names
    that move together do not diversify each other however different they look."""
    empty = {"mean_pairwise": None, "pairs": 0, "names": 0, "matrix": None}
    history = snap.history[snap.history.ticker.isin(tickers)]
    if history.empty:
        return empty
    wide = history.pivot_table(index="date", columns="ticker", values="spread_bps").sort_index()
    changes = wide.diff()
    usable = [column for column in changes.columns if changes[column].count() >= min_points]
    if len(usable) < 2:
        return empty
    matrix = changes[usable].corr()
    values = [
        matrix.iloc[i, j]
        for i in range(len(usable))
        for j in range(i + 1, len(usable))
        if pd.notna(matrix.iloc[i, j])
    ]
    if not values:
        return empty
    return {
        "mean_pairwise": float(sum(values) / len(values)),
        "max_pairwise": float(max(values)),
        "pairs": len(values),
        "names": len(usable),
        "matrix": matrix,
    }


def validation_report(snap: Snapshot, baseline: Snapshot | None = None, top_n: int = 10) -> dict:
    """Everything the Validation Plan asks for, in one call."""
    scores = score_snapshot(snap)
    frame = screen_frame(snap, scores)
    report = {
        "concentration": concentration(frame, top_n=top_n),
        "sensitivity": weight_sensitivity(snap, top_n=top_n),
        "correlation": spread_correlation(snap, list(frame.head(top_n).ticker)),
        "stability": None,
    }
    if baseline is not None:
        baseline_frame = screen_frame(baseline, score_snapshot(baseline))
        report["stability"] = rank_stability(frame, baseline_frame)
    return report
