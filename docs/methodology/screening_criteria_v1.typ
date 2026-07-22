= Screening Criteria

== Objective
Provide a transparent ranking logic for potential note issuance candidates.

== Principles
- Scoring based on evidence from available market data.
- Practical relevance for desk discussion.

== Feature Blocks
=== 1) Credit and Spread Attractiveness
- Absolute spread level
- Spread percentile versus own history
- Spread differential versus peer median
- Current spread versus 1y moving average
- Current spread versus 1y 75th percentile

=== 2) Credit Quality and Risk
- Internal rating bucket
- External rating bucket
- Recent rating trend (stable, positive, negative)

=== 3) Market Liquidity and Accessibility
- CDS quote availability
- CDS liquidity proxy
- Bond liquidity proxy when available

=== 4) Equity Overlay (when feasible)
- Listed equity availability
- 3m and 12m price behavior
- Analyst recommendation balance

=== 5) Recognition and Client Fit
- Household-name score for target audience
- Sector diversification contribution
- Media heat score (Brazil and global)
- Sales narrative clarity score

== Scoring 
#table(
  columns: (3fr, 1fr, 1fr),
  [Block], [Weight], [Score Range],
  [Credit and Spread Attractiveness], [35%], [0-100],
  [Credit Quality and Risk], [20%], [0-100],
  [Market Liquidity and Accessibility], [20%], [0-100],
  [Equity Overlay], [10%], [0-100],
  [Recognition and Client Fit], [15%], [0-100]
)

Composite score:
$ S = 0.35 C_1 + 0.20 C_2 + 0.20 C_3 + 0.10 C_4 + 0.15 C_5 $

== Output Classes
- Tier A: high priority candidates
- Tier B: monitor and revisit
- Tier C: low priority for now

A name with no rating at all, from any agency or the desk's internal scale,
cannot reach Tier A. Block weights renormalize over the blocks that produced a
score, so a missing rating removes the credit-quality penalty instead of
applying it. Without this cap, the widest and least-covered names rank highest:
a 900 bps name with no rating scores 77 and lands in Tier A, while the same name
rated CCC+ scores 65 and lands in Tier B.

== Viability Rule
Viable when the spread is at or above Brazil, or within 20 bps through Brazil
with a strictly stronger rating. Three refinements make the comparison honest:

- *Conservative on splits.* The gate reads the weakest rating any provider
  assigned, not the median. The median invents a rating nobody published and can
  clear the gate on the strength of one optimistic provider. Providers more than
  3 notches apart are flagged as a split rating.
- *Like-for-like benchmark.* An issuer priced off its 5Y CDS is compared against
  Brazil's 5Y CDS; an issuer priced off a bond z-spread is compared against
  Brazil's benchmark bond z-spread. Where no sovereign bond spread is available,
  the bond-versus-CDS comparison is marked indicative. Names whose verdict flips
  between the two legs are flagged as benchmark sensitive.
- *Even median tie-break.* With an even number of providers the median falls
  between two notches; it resolves to the weaker side. Rounding to even would
  otherwise flip the tie-break direction depending on where the split sits on
  the rating scale.

== Flags
Warnings attached to a scored name. They never change the composite; they say
why a rank may mean something other than what it looks like.

#table(
  columns: (1fr, 2fr),
  [Flag], [Meaning],
  [unrated], [No rating from any provider or the desk, so the composite carries no credit-quality block],
  [split_rating], [Providers disagree by 3 or more notches; viability reads the weakest],
  [stale_history], [Fewer than 6 distinct weekly closes: an unrefreshed quote, not a stable credit. History percentile, moving average, and 75th-percentile signals are suppressed],
  [thin_peers], [Fewer than 3 basket peers with a spread, so no peer-median comparison],
  [subordinated], [Selected bond ranks below senior preferred (subordinated, junior, or Sr Non-Preferred): part of the spread is structural, not a credit view],
  [long_tenor], [Bond-priced name whose selected bond runs beyond 7 years against a 5Y CDS standard: part of the pickup is curve, not credit],
  [sovereign_correlated], [Brazil-domiciled or desk-marked state-linked: viable versus Brazil is not diversification away from Brazil],
  [cheap_for_a_reason], [At or beyond 450 bps with a negative outlook or watch: wide because the credit is deteriorating],
  [benchmark_mismatch], [Bond z-spread measured against Brazil's CDS because no sovereign bond spread was available],
  [benchmark_sensitive], [The viability verdict flips depending on which Brazil leg is used],
  [small_issue], [Selected bond has less than USD 500mm outstanding: too small to support a note program],
)

Rating outlook and watch markers are parsed separately from the rating itself
and feed a rating-trend signal in Block 2, the "recent rating trend" item.

== Movers
Viability flips are attributed between the issuer and the sovereign. Brazil's
own CDS routinely moves more than the 20 bps tolerance in a week, so a name can
flip without anything happening to the credit; the callout names which one moved.

== Operating Workflow
- Step 1: Universe filter
- Step 2: Score and rank
- Step 3: Deep-dive shortlist for due diligence
- Step 4: Credit analysis validation before inventory or client offer
- Step 5: Sales and credit trading review for basket construction

== Deep-Dive Trigger Rules
- Candidate in Tier A, or
- Candidate with strong recognition and unusual spread move, or
- Candidate requested by trading or sales for client demand

== Validation Plan
Implemented in `src/issuer_opportunity_screener/validation.py`, reported in the
snapshot report and the dashboard's Validation tab.

- *Rank stability.* Spearman rank correlation of composites between two
  snapshots, plus tier changes, viability flips, and the mean composite move. A
  screen that reshuffles week to week is measuring noise.
- *Weight sensitivity.* Twelve named scenarios: each of the five block weights
  moved up and down by a set perturbation (10% by default), plus a spread-led
  and a quality-led combined tilt. For each, the rank correlation against the
  documented weights and the share of the top N that survives, naming which
  issuers entered and left. High overlap means the weights are a presentation
  choice; low overlap means the weights, not the evidence, are the answer.
- *Concentration.* Herfindahl-Hirschman index and largest-bucket share of the
  shortlist by basket, country, and sector. The screen ranks names one at a
  time, but the product is a basket: ten Tier A names in one country is the same
  bet ten times. Warns above HHI 0.30 or a 50% single bucket.
- *Co-movement.* Mean pairwise correlation of weekly spread changes across the
  shortlist. On changes rather than levels, which would correlate on trend
  alone. Names that move together do not diversify each other.
- Challenge results with desk intuition.
- Review outliers manually before final ranking publication.

== Reproducibility
Each snapshot manifest records the SHA-256 and row count of the universe file
that produced it. The universe is mutable (the desk edits it, quarantine removes
names), so without this a snapshot cannot be reconstructed and any backtest over
the snapshot history is survivorship-biased.

== Client Economics
The USD spread is not the client's return. `hedged_pickup_bps` subtracts a
desk-set cross-currency hedging cost (`IOS_HEDGE_COST_BPS`) from the pickup over
Brazil, so the ranking can be read in the economics of a BRL-hedged note. The
cost is an input, not a market observation: the screener has no cross-currency
basis feed, and pretending otherwise would be the wrong kind of precision.
