= Week 2 Notes

== Goals
- Get the rebuilt screener producing real data on the Terminal machine.
- Close the data-quality loop: evidence artifacts, not just plumbing.
- Make the universe a living object (add, quarantine, restore).

== Progress Log

=== 2026-07-15
- Rebuilt the application end to end (v2): layered package, versioned parquet
  snapshots, documented composite scoring, terminal-dark Streamlit dashboard.
- First live runs on the Terminal machine surfaced and fixed, in order:
  blpapi date-type crash, BOND_CHAIN yellow-key normalization, instruments
  lookup returning the CDS curve into bond eligibility, ratings only being
  requested on equities, bond price history polluting spread history
  (the Xerox +1668 bps case), missing rating providers, and the viability
  edge case never firing without ratings.
- Dashboard shipped with market map, basket comparison, edge-case log,
  replication-grade signal detail, dual themes, and leveled colored logging.

=== 2026-07-16
- Live run diagnosis: every bond reference request is gated by Bloomberg with
  responseError LIMIT / WORKFLOW_REVIEW_NEEDED. Ticket opened with the rep
  (nids in the run logs). Code now requests static fields for candidates and
  pricing only for the selected bond, and announces the gate in plain
  language.
- Brazil benchmark completed: live CDS with lookup fallback, sovereign USD
  benchmark bond discovery, provider-agnostic Brazil ratings.
- Added the exceptional-delivery layer: movers between snapshots with
  rule-based callouts (tighteners, wideners, viability flips, tier moves,
  own-history extremes, near-miss edge cases), snapshot report generator
  (Markdown, dashboard download + CLI), universe add form, quarantine with
  reasons and restore, auto-quarantine env flag (off until the ticket
  clears), final report skeleton with drafted limitations.

== Open Items
- Bloomberg workflow review: waiting on the rep (blocks bond coverage).
- Desk: fill internal ratings and handle overrides for non-US names; confirm
  Sr Non-Preferred inclusion and currency preference.
- After first full snapshot: generate the snapshot report, review outliers
  (distressed-bond flags), and fill the final report results section.

== Risks
- Bond coverage is entitlement-bound, not code-bound; timing is external.
- CDS coverage for names whose credit ticker differs from the universe ticker
  still depends on overrides or the lookup finding the right curve.
