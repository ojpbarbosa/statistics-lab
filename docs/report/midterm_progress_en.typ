#set page(margin: (x: 2.2cm, y: 2.2cm))
#set text(font: "Libertinus Serif", size: 10.5pt)
#set par(justify: true)
#show heading.where(level: 1): set text(size: 15pt)
#show heading.where(level: 2): it => block(above: 1.4em, below: 0.8em)[
  #set text(size: 12pt)
  #it.body
  #v(-0.6em)
  #line(length: 100%, stroke: 0.5pt + luma(160))
]

= Issuer Opportunity Screener: Midterm Progress Report

_COE Credit Trading summer project. Period covered: 2026-07-09 to 2026-07-20 (end of week 2 of 4)._

== Objective and status at a glance

The project builds an initial screening framework to identify corporate names that may be attractive candidates for note issuance (COEs) for Brazilian investors, based on market spreads, credit information, and complementary equity signals. The commercial premise, aligned with the desk on 2026-07-13: Brazilian investors have little appetite for names trading far through Brazil, so every spread is anchored against the Brazil benchmark and the screen favors recognizable names with real carry.

#table(
  columns: (1fr, auto),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Workstream*], [*Status*],
  [Universe definition and governance], [Done (125 names, desk-editable)],
  [Data pipeline and snapshots], [Done, validated on synthetic and partial live data],
  [Screening methodology and scoring], [Done and documented],
  [Dashboard], [Done],
  [Full live data run], [Blocked by Bloomberg entitlement (ticket open)],
  [Final report and desk presentation], [Skeleton drafted, results pending data],
)

The framework is fully operational end to end. The single open blocker is external: a Bloomberg entitlement review that gates bulk bond data over the Desktop API. Two mitigation paths are already built (detailed under Limitations).

== What has been delivered

*Consolidated dataset and pipeline.* Versioned, append-only snapshots (parquet plus manifest) with one row per issuer covering: 5Y CDS (CDS-first, bond z-spread fallback), one representative senior unsecured USD bond (3 to 10 years, z-spread, price, maturity, coupon), provider-agnostic ratings (Moody's, S&P, Fitch, DBRS, KBRA, Bloomberg composite), an equity overlay (3m/12m momentum, analyst recommendation balance), qualitative desk fields (baskets, recognition, internal ratings), and one year of weekly spread history per name.

*Screening methodology, documented.* A composite score of five blocks weighted 35/20/20/10/15 (spread attractiveness, credit quality, liquidity, equity overlay, recognition), tiers A/B/C, and the desk viability rule: spread at or above Brazil, or within 20 bps through Brazil with a strictly stronger rating. The rule already handles the interesting edge cases, for example a name trading 18 bps through Brazil with an A- rating is correctly kept as a higher-quality alternative. Every classification carries a plain-language rationale, and every signal is replicable on the terminal: the dashboard shows the exact arithmetic, securities, and fields used.

*Brazil benchmark.* Live sovereign CDS with lookup fallback, USD benchmark bond discovery, and provider-agnostic sovereign ratings.

*Dashboard.* Streamlit application with a ranked screen, market map, basket comparison, edge-case log, single-name detail with full score breakdown and spread history vs Brazil, movers between snapshots with rule-based callouts (tighteners, wideners, viability flips, tier moves), data-quality view, and one-click snapshot report export. Dual light/dark themes.

*Universe lifecycle.* Desk-editable universe CSV with per-name Bloomberg handle overrides, an add-a-name form in the dashboard, and a quarantine mechanism that removes unscored names with documented reasons while keeping them restorable.

*Engineering quality.* Layered one-directional architecture (universe, sources, pipeline, snapshots, scoring, app), 100+ automated tests, and a deterministic fixture source so the whole system runs and demos on any machine without a Terminal.

== Limitations and blockers

- *Bloomberg entitlement (main blocker, external).* Bulk bond reference and pricing requests over the Desktop API are gated by Bloomberg (responseError LIMIT / WORKFLOW_REVIEW_NEEDED). A workflow-review ticket is open with the Bloomberg representative. Mitigations already in place: the request surface was minimized (static fields for candidates, pricing only for the single selected bond per issuer), and an alternative BQuant export route was built, which runs the bond screen server-side under different entitlements and feeds the exact same pipeline. The BQuant route still needs a validation run on the Terminal machine.
- *Handle mapping.* Universe tickers are best-effort credit-family tickers; non-US listings and CDS conventions need desk-confirmed overrides. Coverage improves as these fill.
- *One bond per issuer.* Curve shape and issue-specific features (callables, sinking funds, deep discounts) are out of scope. Suspicious selections (z-spread above 1000 bps or price below 50, the DISH-type outliers) are flagged for separate review, not silently ranked.
- *Comparability.* Spreads are compared within a fixed 3 to 10 year senior unsecured USD scope; finer maturity, sector, and liquidity adjustments are a candidate refinement, not yet implemented. Non-USD bonds are marked indicative only.
- *Recognition score is subjective.* Desk-set, on a documented 0 to 100 scale; a measured proxy (media heat) was consciously deferred.
- *Ratings gaps.* Where no external provider resolves, viability falls back to the desk internal rating and labels the result as provisional.

== What is left (weeks 3 and 4)

+ Unblock full data: validate the BQuant export route on the Terminal and/or close the Bloomberg workflow review; then run the full 125-name universe and land the first complete snapshot.
+ Results pass: generate the snapshot report, review outliers, and fill the final report's results section (coverage, tier distribution, top names with rationale, edge cases, movers narrative).
+ Desk pass on the universe file: internal ratings, handle overrides for non-US names, confirmation of Sr Non-Preferred inclusion and currency preference.
+ Presentation-ready categorization of results: high spread / high risk, balanced candidates, and high-quality edge cases, instead of a single ranked list.
+ Final report consolidation, code handover organization, and the desk presentation.

Relative to the four-week roadmap, the project is on schedule: weeks 1 and 2 goals (environment, universe, dataset, cleaning, baseline screening logic) are complete, and week 3 material (methodology documentation, dashboard) was delivered early. The main schedule risk is external entitlement timing, which the BQuant route exists to absorb.
