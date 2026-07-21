#set text(font: "New Computer Modern")
#import "@preview/problemst:0.1.2": pset
#import "@preview/intextual:0.1.0": eqref, flushl, flushr, intertext, intertext-rule, tag
#import "@preview/frame-it:1.2.0": *
#import "@preview/ctheorems:1.1.3": *
#import "@preview/numbly:0.1.0": numbly
#import "@preview/quonom:0.1.0": manual-synthdiv, synthdiv

#let lemma = frame("Lemma", blue)
#let proof = thmproof("proof", "Proof")
#show: frame-style(styles.thmbox)
#show: intertext-rule

#show: pset.with(
  class: "XP :: Issuer Opportunity Screener",
  student: "João Pedro Ferreira Barbosa",
  title: "Midterm Progress",
)

_Summer project. Period covered: 2026-07-09 to 2026-07-21 (end of week 2 of 4)._

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

The framework is fully operational end to end. The single open blocker is external: a Bloomberg entitlement review that gates bulk bond data over the Desktop API. Three alternative data routes are already in motion (detailed under Limitations).

== What has been delivered

*Consolidated dataset and pipeline.* Versioned, append-only snapshots (parquet plus manifest) with one row per issuer covering: 5Y CDS (CDS-first, bond z-spread fallback), one representative senior unsecured USD bond (3 to 10 years, z-spread, price, maturity, coupon), provider-agnostic ratings (Moody's, S&P, Fitch, DBRS, KBRA, Bloomberg composite), an equity overlay (3m/12m momentum, analyst recommendation balance), qualitative desk fields (baskets, recognition, internal ratings), and one year of weekly spread history per name.

*Screening methodology, documented.* A composite score of five blocks weighted 35/20/20/10/15 (spread attractiveness, credit quality, liquidity, equity overlay, recognition), tiers A/B/C, and the desk viability rule: spread at or above Brazil, or within 20 bps through Brazil with a strictly stronger rating. The rule already handles the interesting edge cases, for example a name trading 18 bps through Brazil with an A- rating is correctly kept as a higher-quality alternative. Every classification carries a plain-language rationale, and every signal is replicable on the terminal: the dashboard shows the exact arithmetic, securities, and fields used.

*Brazil benchmark.* Live sovereign CDS with lookup fallback, USD benchmark bond discovery, and provider-agnostic sovereign ratings.

*Dashboard.* Streamlit application with a ranked screen, market map, basket comparison, edge-case log, single-name detail with full score breakdown and spread history vs Brazil, movers between snapshots with rule-based callouts (tighteners, wideners, viability flips, tier moves), data-quality view, and one-click snapshot report export. Dual light/dark themes.

*Universe lifecycle.* Desk-editable universe CSV with per-name Bloomberg handle overrides, an add-a-name form in the dashboard, and a quarantine mechanism that removes unscored names with documented reasons while keeping them restorable.

*Engineering quality.* Layered one-directional architecture (universe, sources, pipeline, snapshots, scoring, app), 100+ automated tests, and a deterministic fixture source so the whole system runs and demos on any machine without a Terminal.

== Limitations and blockers

- *Bloomberg entitlement (main blocker, external).* Bulk bond reference and pricing requests over the Desktop API are gated by Bloomberg (responseError LIMIT / WORKFLOW_REVIEW_NEEDED). The account manager was contacted and has not replied yet. Routes already in motion: the request surface was minimized (static fields for candidates, pricing only for the single selected bond per issuer); a BQuant export route runs the bond screen server-side under different entitlements (validation run pending); and the internal Hermes API now feeds bond EoD data by ISIN, with a server-side CDS endpoint under discussion with its owner. Markit Partners access was also requested for additional credit data.
- *Handle mapping.* Universe tickers are best-effort credit-family tickers; non-US listings, CDS conventions, and Hermes ISINs need desk-confirmed values. Coverage improves as these fill.
- *One bond per issuer.* Curve shape and issue-specific features (callables, sinking funds, deep discounts) are out of scope. Suspicious selections (z-spread above 1000 bps or price below 50, the DISH-type outliers) are flagged for separate review, not silently ranked.
- *Comparability.* Spreads are compared within a fixed 3 to 10 year senior unsecured USD scope; finer maturity, sector, and liquidity adjustments are a candidate refinement, not yet implemented. Non-USD bonds are marked indicative only, and Hermes-derived spreads are G-spread proxies labeled as such.
- *Recognition score is subjective.* Desk-set, on a documented 0 to 100 scale; a measured proxy (media heat) was consciously deferred.
- *Ratings gaps.* Where no external provider resolves, viability falls back to the desk internal rating and labels the result as provisional.

== What is left (weeks 3 and 4)

+ Unblock full data: validate the BQuant route on the Terminal and/or land the first complete Hermes-fed snapshot; then run the full 125-name universe.
+ Results pass: generate the snapshot report, review outliers, and fill the final report's results section (coverage, tier distribution, top names with rationale, edge cases, movers narrative).
+ Desk pass on the universe file: internal ratings, handle overrides and ISINs for non-US names, confirmation of Sr Non-Preferred inclusion and currency preference.
+ Presentation-ready categorization of results: high spread / high risk, balanced candidates, and high-quality edge cases, instead of a single ranked list.
+ Final report consolidation, code handover organization, and the desk presentation.

Relative to the four-week roadmap, the project is on schedule: weeks 1 and 2 goals (environment, universe, dataset, cleaning, baseline screening logic) are complete, and week 3 material (methodology documentation, dashboard) was delivered early. The main schedule risk is external entitlement timing, which the BQuant and Hermes routes exist to absorb.
