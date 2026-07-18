= Issuer Opportunity Screener: Final Report

_COE Credit Trading summer project, 2026. Status: DRAFT (results sections to be filled after full data access)._

== Objective

Develop an initial screening framework to identify corporate names that may be
attractive candidates for note issuance (COEs) for Brazilian investors, based
on market spreads, credit information, and complementary equity signals. The
commercial premise, set with the desk on 2026-07-13: Brazilian investors have
little appetite for names trading far through Brazil, so the screen anchors
every spread against the Brazil benchmark and favors recognizable names with
real carry.

== Deliverables produced

- Consolidated dataset: versioned, append-only snapshots (parquet + manifest)
  with one row per issuer covering 5Y CDS, a representative senior unsecured
  USD bond (z-spread, price, maturity, coupon), provider-agnostic ratings,
  equity overlay (3m/12m momentum, analyst recommendation balance),
  qualitative fields (baskets, recognition, internal ratings), and 1y weekly
  spread history per name.
- Screening methodology: documented composite score
  (`docs/methodology/screening_criteria_v1.typ`), five blocks weighted
  35/20/20/10/15, tiers A/B/C, and the desk viability rule (spread at or
  above Brazil, or within 20 bps with a strictly stronger rating). Every
  signal is replicable on the terminal: the dashboard shows the exact
  arithmetic and the exact securities and fields used.
- Dashboard: Streamlit application with a ranked screen, market map, basket
  comparison, edge-case log, single-name detail with full score breakdown and
  spread history vs Brazil, movers between snapshots with rule-based
  callouts, data-quality and universe-administration views, and a one-click
  snapshot report export.
- Universe lifecycle: desk-editable universe CSV (125 names at time of
  writing) with per-name Bloomberg handle overrides, an add-a-name form in
  the dashboard, and a quarantine mechanism that removes unscored names with
  documented reasons while keeping them restorable.

== Methodology summary

+ Universe: curated baskets (Brazil, Latin America, global sectors) selected
  for recognition among Brazilian investors and for liquid credit data;
  extended with names chosen specifically for liquid single-name CDS.
+ Data collection: CDS-first (5Y point, exact tenor, D14 doc clause); one
  representative senior unsecured USD bond per issuer (3-10y, closest to 5y,
  largest outstanding) with pricing fetched only for the selected bond;
  ratings merged provider-agnostically from bond, CDS, and equity (Moody's,
  S&P, Fitch, DBRS, KBRA, Bloomberg composite).
+ Scoring: composite of spread attractiveness (level, own-history percentile,
  vs 1y average, vs 1y 75th percentile, vs basket median), credit quality
  (external and desk internal ratings), liquidity proxies, equity overlay,
  and recognition. Weights renormalize when a block has no data.
+ Viability: the commercial screen vs Brazil, including the edge case for
  stronger-rated names within 20 bps, evaluated against Brazil's live CDS,
  benchmark bond, and fetched rating.

== Results

_[TO FILL after the Bloomberg workflow review clears and a full snapshot
lands: coverage table, tier distribution, top names with rationale, edge-case
list, movers narrative. Generate via the snapshot report and paste the
figures here.]_

== Limitations

- *Bloomberg entitlements*: bulk bond reference/pricing requests over the
  Desktop API were gated by Bloomberg (responseError category LIMIT,
  subcategory WORKFLOW_REVIEW_NEEDED); a workflow-review ticket is open. The
  code minimizes the gated surface (static fields for candidates, pricing for
  the single selected bond), but bond coverage depends on the approval.
- *Handle mapping*: universe tickers are best-effort credit-family tickers;
  non-US listings and CDS conventions require desk-confirmed overrides
  (`equity_ticker`, `cds_ticker` columns). Coverage improves as these fill.
- *One bond per issuer*: the screen prices a single representative senior
  unsecured USD bond; curve shape and issue-specific features (callables,
  sinking funds, deep discounts) are out of scope. Suspicious selections
  (z-spread above 1000 bps or price below 50) are flagged, not filtered.
- *Cross-currency comparisons*: when only non-USD bonds exist, z-spreads vs
  the Brazil USD benchmark are indicative only and flagged as such.
- *Recognition is subjective*: the household-name score is desk-set, not a
  measured proxy; media-heat signals were consciously deferred.
- *Ratings*: the composite uses the median of available providers; where no
  provider resolves, viability falls back to the desk internal rating and
  says so.
- *History depth*: 1y weekly history for the primary spread instrument only;
  rating histories and longer windows were not collected.

== Suggested next steps

+ Close the Bloomberg workflow review and re-run the full universe; then fill
  the Results section from the generated snapshot report.
+ Desk pass over the universe file: internal ratings, handle overrides, and
  confirmation of the Sr Non-Preferred and currency-preference decisions.
+ Scheduled refreshes (daily snapshot) to make the movers view and rank
  stability meaningful; add a small backtest over accumulated snapshots.
+ Optional enrichments in priority order: media-heat or news proxies for the
  recognition block, rule-based sales narratives per name, hosted deployment
  for the desk, multi-bond curves per issuer.

== Where everything lives

- Code and tests: repository root (`src/issuer_opportunity_screener`,
  `tests`), 100+ tests, run with `poetry run pytest`.
- Data: `data/universe.csv` (+ quarantine file), `data/snapshots/`.
- Docs: methodology, universe governance, weekly notes under `docs/`.
- Reports: generated per snapshot via the dashboard or
  `poetry run python -m issuer_opportunity_screener.reports`.
