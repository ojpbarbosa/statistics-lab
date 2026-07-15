
= Week 1 Notes

== Goals
- Setup environment and project structure.
- Define initial universe of issuers.
- Start raw data collection pipeline planning.

== Progress Log
=== 2026-07-10
- Created project context file for Copilot in .github.
- Refined universe governance to include 100-name scope and added client-fit signals.
- Expanded candidate universe to 100 names across global baskets.
- Standardized rationale format for easier maintenance and faster expansion.
- Refined methodology with deep-dive trigger rules and workflow gates.
- Added the main Bloomberg raw-data application under `src/` with issuer-to-security match review plus equity, bond, and CDS discovery paths, and documented the connectivity blocker.
=== 2026-07-13
- Incorporated desk feedback into universe governance and validation documents.
- Added spread-versus-Brazil framing, CDS-first preference, and senior unsecured USD 3 to 10 year bond scope guidance.
- Flagged the current candidate list as a pre-feedback draft pending rebalance and Latin America additions.
- Added a Bloomberg screening mode to test candidate CDS spreads and bond z-spreads directly against Brazil benchmarks.
=== 2026-07-09
- Created project setup and initial repository structure.

== Open Items
- Confirm instrument-level bond list per issuer.
- Confirm exact Bloomberg fields for z-spreads, CDS spreads, and internal ratings.
- Confirm handling for non-listed names with credit relevance.

=== 2026-07-14 Data Quality Overhaul
- Added canonical Bloomberg security variants for embedded coupon fractions such as `6<1/2>` and normalized yellow-key suffixes.
- Added retry and provenance tracking for reference-data security failures instead of treating instrument discovery output as canonical.
- Excluded interpolated CDS tenors such as `5Y3M` and `1Y9M` from first-pass validation.
- Separated credit ratings from ESG ratings and retained all discovered agency/source values for later disagreement analysis.
- Added flexible rating sourcing across standard, secondary, national, DBRS, KBRA, Scope, JCR, and description-based rating values.
- Added structured validation, security-attempt, and refdata-quality outputs.
- Added current and historical spread summaries, peer spread comparisons, liquidity proxies, and equity overlay coverage fields to screen output.
- Added Brazil benchmark rating rediscovery and quality-gated manifests so partial runs are not reported as fully complete.

== Risks
- Data availability may vary by issuer and instrument.
- Household-name criterion is subjective and needs explicit rubric.

== Next Actions
- Gather top 500 names that fit within the stablished universe.
- Convert candidate names into issuer-ticker and bond-level mapping.
- Validate matching quality and finalize Bloomberg field dictionary.
- Start first raw pull and data quality checks.
- Run the revised raw-data and screen commands against Bloomberg and review `bloomberg_data_quality.csv` and `bloomberg_screen_validation.csv`.
- Quarantine mappings that still fail issuer identity validation and confirm canonical Bloomberg handles with the desk.
