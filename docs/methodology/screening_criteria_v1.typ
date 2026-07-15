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
- Backtest stability over recent periods.
- Challenge results with desk intuition.
- Review outliers manually before final ranking publication.
