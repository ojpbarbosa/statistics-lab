= Team Validation - Initial Universe, Issuers, Baskets, and Bonds

== Objective
Validate with the desk whether the proposed issuer universe and basket structure are appropriate, and confirm the bond-level scope required for data extraction and screening.

== Desk Feedback Summary (2026-07-13)
- The initial global baskets appear skewed toward extremely high-grade names.
- Many of those names likely trade 70 to 100 bps through Brazil, which would make a COE linked to them unattractive for Brazilian investors.
- A practical first filter should compare issuer CDS spread or bond z-spread against Brazil.
- A provisional rule suggested by the desk is: `CDS spread / bond z-spread >= Brazil`, or `>= Brazil - 20 bps` when the issuer rating is stronger than Brazil.
- Brazil should remain in scope, and Latin America should be added.
- The current Brazil basket is unbalanced: some names are distressed, while others may lack offshore debt or trade too close to Brazil.
- When CDS is available and liquid, the desk prefers CDS over bonds.
- There is no strict bond-count limit per issuer at this stage.
- Default bond scope should prioritize senior unsecured USD bonds in the 3 to 10 year area with usable liquidity.
- BRL, EUR, and JPY hedges exist in the book but are exceptions rather than the base case.

== What Is Being Validated
- Universe logic and basket design
- Issuer selection quality
- Bond selection rules per issuer
- CDS linkage approach
- Practical usability for credit trading and sales discussions

== Current Inputs
- Issuer and basket proposal: `docs/universe/candidate_names.typ`
- Governance rules: `docs/universe/universe_governance.typ`

== Validation Questions for the Desk
#enum(
  [Do the current baskets reflect how the desk thinks about offshore product construction?],
  [Are any baskets missing or over-represented?],
  [Are the Brazil anchors appropriate for client familiarity?],
  [Do the global names match the target audience and sales narrative?],
  [Should any names be removed due to weak relevance or weak tradability?],
  [For each issuer, how many bonds should be in scope for v1?],
  [What maturity buckets should be prioritized?],
  [Which currencies should be included for v1?],
  [What seniority types are acceptable in v1?],
  [What are the minimum liquidity requirements for bond inclusion?],
  [How should CDS proxies be assigned when direct liquidity is weak?],
  [What approval gate is required before a name moves to deep dive?]
)

== Validation Outcome
- Basket logic is directionally useful, but the global list needs spread-based pruning.
- The universe should not over-index to household names that are too tight versus Brazil.
- Brazil remains relevant for client familiarity, but the basket must be rebalanced.
- Latin America should be added to the coverage map.
- Screening should be CDS-first whenever liquid CDS exists.
- Bond extraction should focus first on senior unsecured USD risk in the 3 to 10 year tenor range.

== Proposed Bond Universe Rules (Draft for Validation)
- Include only corporate issuers already approved in the issuer universe.
- Exclude sovereign issuers from the candidate list.
- Prioritize liquid benchmark bonds by issuer when CDS is not the preferred primary instrument.
- Prefer plain-vanilla structures for first-pass screening.
- Prefer issuers with available spread history and CDS references.
- Use spread versus Brazil as an initial commercial viability screen.
- Allow tighter-than-Brazil edge cases only when relative rating strength clearly compensates.
- Prioritize senior unsecured USD bonds with 3 to 10 year maturity and practical hedge liquidity.
