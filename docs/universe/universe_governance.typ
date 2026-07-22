= Universe Governance

== Purpose
This document defines how the initial bond issuer universe is built and maintained.

== Guiding Principles
- Keep the universe explainable to the desk.
- Prioritize names with strong recognition among Brazilian, Brazilian-American, Hispanic, and Latin American investors in the US.
- Favor liquid, well-covered issuers with available credit market data.
- Prioritize names that can realistically generate attractive offshore COE economics versus Brazil.
- Keep scope practical for a 4-week delivery cycle.
- Build a broad but manageable list that can expand as coverage grows.

== Inclusion Rules 
- Issuer has clear household-name recognition in at least one target audience.
- Issuer has available bond spread history and CDS data on Bloomberg.
- Issuer has rating information available from relevant sources.
- Sector-level diversification is possible within the final list.
- Include major global names, with strong emphasis on Fortune 500 style names for US clients.
- Include Brazil and Latin America names when they are relevant for client familiarity and spread opportunity.
- Prefer issuers whose CDS spread or bond z-spread is at least comparable to Brazil.
- Allow edge cases when spread is up to 20 bps tighter than Brazil only if rating is stronger than Brazil and the relative value case is clear.

== Exclusion Rules
- Extremely high-grade names that are likely to price far through Brazil and produce unattractive investor carry.
- Insufficient spread history for meaningful comparison.
- Extremely illiquid instruments without practical execution relevance.
- Names with unclear investor recognition fit for the target audience.
- Sovereign issuers are out of scope for this corporate notes framework.

== Desk-Editable Columns
`data/universe.csv` carries the desk's own inputs alongside the identifiers:
`recognition_score`, `internal_rating`, `equity_ticker` and `cds_ticker`
handle overrides, `isin` for the ISIN-keyed sources, and `state_linked`.

`state_linked` marks state-owned and quasi-sovereign issuers (`yes` or blank).
These names carry sovereign support in their rating and move with their
sovereign, so "viable versus Brazil" does not make them a diversification away
from Brazil. Brazil-domiciled names are detected from `country` automatically;
`state_linked` is for the SOEs elsewhere in the Latin America basket and needs a
desk pass to fill.

== Universe Structure
The universe is split into baskets:
- Brazil Core Basket
- Latin America Basket
- Global AI and Tech Basket
- Global Consumer and Media Basket
- Global Industrial and Manufacturing Basket
- Global Energy and Materials Basket
- Global Financials Basket
- Global Healthcare Basket
- Global Transport and Aerospace Basket

== Target Size
- No fixed cap at this stage.
- The list is a screening universe, not a final recommendation list.

== Signals Tracked at Universe Level
- CDS spread versus Brazil
- Bond z-spread versus Brazil
- Spread level and spread dislocation versus own history
- Rating strength and trend
- Brand recognition in Brazil and target offshore audience
- Media heat / public attention proxy
- Country and sector diversification
- Sales pitch relevance (clear client narrative)

== Bond and CDS Scope Preference
- When liquid CDS exists, prefer CDS over cash bonds for screening and hedging relevance.
- There is no strict cap on bonds per issuer at this stage.
- Default bond scope should focus on senior unsecured USD bonds.
- Preferred maturity window is 3 to 10 years.
- Practical liquidity is required for hedge execution.
- BRL, EUR, and JPY hedges may be considered, but they are exceptions rather than the default scope.

== Desk Feedback Incorporated (2026-07-13)
- Many of the current global names appear too high grade and may trade roughly 70 to 100 bps through Brazil.
- In those cases, a COE linked to the name would likely price below 100% CDI and be unattractive for Brazilian investors.
- Brazil should remain in scope, and Latin America should also be included.
- The current Brazil basket is unbalanced, with distressed names mixed with names that may have no offshore debt or may trade too close to Brazil.
- The next universe revision should rebalance Brazil, add Latin America, and apply the spread screen before expanding coverage.

== Change Log Rules
Each material universe change must include:
- Date
- Change type (add, remove, reclassify)
- Rationale
- Data availability note

== Current Status
Draft v1 updated after desk feedback and pending rebalance of candidate names.
