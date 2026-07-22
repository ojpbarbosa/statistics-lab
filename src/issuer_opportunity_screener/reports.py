"""Snapshot report generator: the weekly evidence artifact, in Markdown.

Covers the screening summary, viability and edge cases, movers vs a baseline
snapshot when one exists, and the data-quality section the program brief asks
for. Usable from the dashboard (download button) or the CLI:

    poetry run python -m issuer_opportunity_screener.reports
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from issuer_opportunity_screener.insights import build_insights, movers_frame, scored_frames
from issuer_opportunity_screener.scoring import score_snapshot, screen_frame
from issuer_opportunity_screener.snapshots import Snapshot, list_snapshots, load_snapshot
from issuer_opportunity_screener.universe_admin import unscored_reasons
from issuer_opportunity_screener.validation import validation_report


def _md_table(frame: pd.DataFrame, columns: dict[str, str], float_format: str = "{:.1f}") -> str:
    header = "| " + " | ".join(columns.values()) + " |"
    divider = "|" + "|".join(["---"] * len(columns)) + "|"
    lines = [header, divider]
    for row in frame.itertuples():
        cells = []
        for key in columns:
            value = getattr(row, key, None)
            if value is None or (isinstance(value, float) and pd.isna(value)):
                cells.append("")
            elif isinstance(value, float):
                cells.append(float_format.format(value))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_report(snap: Snapshot, baseline: Snapshot | None = None) -> str:
    scores = score_snapshot(snap)
    frame = screen_frame(snap, scores)
    manifest = snap.manifest
    brazil = manifest["brazil"]

    parts: list[str] = []
    parts.append("# Issuer Opportunity Screener: snapshot report")
    parts.append(
        f"Snapshot `{manifest['as_of']}` (source: {manifest['source']}"
        + (", PARTIAL" if manifest.get("partial") else "")
        + f"). Universe {manifest['issuer_count']} names, {len(frame)} scored."
    )
    parts.append(
        f"Brazil benchmark: 5Y CDS {brazil['cds_5y_bps']:.0f} bps"
        + (f"; bond {brazil['bond_security']}" if brazil.get("bond_security") else "")
        + (f" (z-spread {brazil['z_spread_bps']:.0f} bps)" if brazil.get("z_spread_bps") is not None else "")
        + f"; rating {brazil.get('rating_sp', 'n/a')}"
        + (f" from {', '.join(brazil['ratings'])}" if brazil.get("ratings") else " (fallback)")
    )

    parts.append("## Screening summary")
    tier_counts = frame.tier.value_counts().to_dict()
    parts.append(
        f"Tier A: {tier_counts.get('A', 0)} | Tier B: {tier_counts.get('B', 0)} | "
        f"Tier C: {tier_counts.get('C', 0)} | viable vs Brazil: {int(frame.viable.sum())}"
    )
    top = frame.head(10)
    parts.append(
        _md_table(
            top,
            {
                "issuer": "Issuer", "ticker": "Ticker", "tier": "Tier", "composite": "Composite",
                "spread_vs_brazil_bps": "vs Brazil (bps)", "rating_composite": "Rating",
                "rating_source": "Providers",
            },
        )
    )

    parts.append("## Viability and edge cases")
    edge = frame[frame.viable & (frame.spread_vs_brazil_bps < 0)]
    if edge.empty:
        parts.append("No edge-case names (within 20 bps of Brazil on rating strength) in this snapshot.")
    else:
        parts.append(
            _md_table(
                edge,
                {
                    "issuer": "Issuer", "ticker": "Ticker", "rating_composite": "Rating",
                    "spread_vs_brazil_bps": "vs Brazil (bps)", "viability_note": "Why",
                },
            )
        )

    parts.append("## Flagged names")
    parts.append(
        "Warnings that change what a rank means: subordination, split ratings, "
        "stale quotes, sovereign correlation, benchmark basis, and tenor."
    )
    flagged = frame[frame["flag_codes"].astype(bool)]
    if flagged.empty:
        parts.append("No flags raised in this snapshot.")
    else:
        parts.append(
            _md_table(
                flagged.sort_values("composite", ascending=False),
                {
                    "issuer": "Issuer", "ticker": "Ticker", "tier": "Tier",
                    "flag_codes": "Flags", "flag_notes": "What it means",
                },
            )
        )

    if baseline is not None:
        frame_now, frame_then, _, _ = scored_frames(snap, baseline)
        movers = movers_frame(
            frame_now,
            frame_then,
            brazil_now=snap.manifest["brazil"]["cds_5y_bps"],
            brazil_then=baseline.manifest["brazil"]["cds_5y_bps"],
        )
        baseline_label = baseline.manifest["as_of"]
        parts.append(f"## Movers vs {baseline_label}")
        significant = movers[(movers.status == "both") & (movers.delta_bps.abs() >= 15)]
        if significant.empty:
            parts.append("No moves of 15 bps or more between the two snapshots.")
        else:
            parts.append(
                _md_table(
                    significant.head(15),
                    {
                        "issuer": "Issuer", "ticker": "Ticker", "spread_then": "Then (bps)",
                        "spread_now": "Now (bps)", "delta_bps": "Delta (bps)",
                        "vs_brazil_now": "vs Brazil now (bps)",
                    },
                )
            )
        callouts = build_insights(movers, snap, baseline_label)
        if callouts:
            parts.append("### Callouts")
            parts.extend(f"- {insight.message}" for insight in callouts[:20])

    parts.append("## Validation")
    parts.append(
        "Does the screen agree with itself, and is the ranking driven by the evidence "
        "or by the weighting choice? Method in `docs/methodology/screening_criteria_v1.typ`."
    )
    validation = validation_report(snap, baseline)

    sensitivity = validation["sensitivity"]
    if sensitivity["scenarios"]:
        worst = min(sensitivity["per_scenario"], key=lambda row: row["top_n_overlap"])
        correlation_text = (
            f"mean {sensitivity['mean_spearman']:.3f}, worst {sensitivity['min_spearman']:.3f}"
            if sensitivity["mean_spearman"] is not None
            else "not measurable (fewer than two scored names)"
        )
        parts.append(
            f"**Weight sensitivity.** {sensitivity['scenarios']} scenarios at "
            f"+/-{sensitivity['perturbation']:.0%} per block. Rank correlation vs the documented "
            f"weights: {correlation_text}. "
            f"Top-{sensitivity['top_n']} overlap: worst {sensitivity['min_top_n_overlap']:.0%} "
            f"under `{worst['label']}`"
            + (f" (in: {', '.join(worst['entered'])}; out: {', '.join(worst['left'])})"
               if worst["entered"] or worst["left"] else "")
            + "."
        )

    conc = validation["concentration"]
    if conc.get("names"):
        dimensions = ", ".join(
            f"{dimension} HHI {conc[dimension]['hhi']:.2f} (largest {conc[dimension]['largest']}, "
            f"{conc[dimension]['top_share']:.0%})"
            for dimension in ("basket", "country", "sector")
            if dimension in conc
        )
        parts.append(f"**Concentration** of the top {conc['top_n']}: {dimensions}.")
        parts.extend(f"- {warning}" for warning in conc["warnings"])

    correlation = validation["correlation"]
    if correlation["mean_pairwise"] is not None:
        parts.append(
            f"**Co-movement** of the shortlist: mean pairwise correlation of weekly spread "
            f"changes {correlation['mean_pairwise']:.2f} across {correlation['pairs']} pairs "
            f"(max {correlation['max_pairwise']:.2f}). Names that move together do not "
            f"diversify each other."
        )

    stability = validation["stability"]
    if stability and stability["names_in_both"] and stability["spearman"] is not None:
        parts.append(
            f"**Stability** vs the baseline snapshot: rank correlation "
            f"{stability['spearman']:.3f} across {stability['names_in_both']} names, "
            f"{stability['tier_changes']} tier change(s), {stability['viability_flips']} "
            f"viability flip(s), mean composite move "
            f"{stability['mean_abs_composite_move']:.1f} points."
        )

    parts.append("## Data quality")
    coverage = manifest.get("coverage", {})
    parts.append("| Field | Coverage |")
    parts.append("|---|---|")
    parts.extend(f"| {field} | {value:.0%} |" for field, value in coverage.items())
    failures = manifest.get("failures", {})
    if failures:
        parts.append(f"\n{len(failures)} fetch failure(s):")
        parts.extend(f"- `{ticker}`: {reason}" for ticker, reason in sorted(failures.items()))
    reasons = unscored_reasons(snap, scores)
    if reasons:
        parts.append(f"\n{len(reasons)} name(s) did not score:")
        parts.extend(f"- `{ticker}`: {reason}" for ticker, reason in sorted(reasons.items()))

    parts.append("## Method and caveats")
    parts.append(
        "Composite score per `docs/methodology/screening_criteria_v1.typ` "
        "(35/20/20/10/15 blocks, tiers A at 70 and B at 50); viability = spread at or above "
        "Brazil, or within 20 bps with a strictly stronger rating. Non-USD bond z-spreads vs the "
        "USD benchmark are indicative. One representative bond per issuer. See the final report "
        "for full limitations."
    )
    return "\n\n".join(parts) + "\n"


def main() -> None:
    data_root = Path(os.environ.get("IOS_DATA_DIR", "data"))
    snapshots = list_snapshots(data_root / "snapshots")
    if not snapshots:
        raise SystemExit("no snapshots found; run a refresh first")
    snap = load_snapshot(snapshots[-1])
    baseline = load_snapshot(snapshots[-2]) if len(snapshots) > 1 else None
    out_dir = Path("reports")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"snapshot_report_{snapshots[-1].name}.md"
    out_path.write_text(build_report(snap, baseline), encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
