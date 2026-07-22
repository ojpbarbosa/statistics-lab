= Week 3 Notes

== Goals
- Harden the screening logic against the cases where a rank means something
  other than what it looks like.
- Keep every warning explainable to the desk in one line.

== Progress Log

=== 2026-07-22
- Audited the scoring path for edge cases beyond the through-Brazil tolerance
  rule. Two were already live in the code and changing results:
  - Block-weight renormalization rewarded a missing rating. A 900 bps name with
    no rating scored 77.1 (Tier A); the same name rated CCC+ scored 65.3
    (Tier B), because dropping the credit-quality block removed the penalty
    rather than applying it. An unrated name can no longer reach Tier A.
  - Split ratings collapsed to a median with banker's rounding, so the
    tie-break direction flipped with position on the scale: A-/BBB+ resolved to
    A- (stronger) while BBB+/BBB resolved to BBB (weaker). Even medians now
    resolve to the weaker side, and the viability gate reads the weakest
    provider rather than the median.
- Added eight further edge cases as flags that annotate rather than rescore:
  like-for-like Brazil benchmark (bond versus bond, CDS versus CDS) with
  benchmark-mismatch and benchmark-sensitive warnings, subordination detection
  from `PAYMENT_RANK`, long-tenor bonds against the 5Y CDS standard, stale
  history (fewer than 6 distinct closes) suppressing the percentile and moving
  average signals, thin baskets (fewer than 3 peers) dropping the peer median,
  sovereign correlation for Brazil-domiciled and state-linked names, and
  "cheap for a reason" for wide names on negative outlook.
- Rating outlook and watch markers are now parsed instead of stripped, and feed
  the rating-trend signal that Block 2 of the methodology always specified.
- Movers now attribute viability flips between the issuer and the sovereign:
  Brazil's own CDS moves more than the 20 bps tolerance in a normal week.
- Fixed a data-loss bug in the universe admin writer: `UNIVERSE_FIELDS` omitted
  `isin`, so adding a name through the dashboard form silently dropped every
  ISIN in the file. Added `isin` and `state_linked` columns to the universe.
- Fixed the fixture's synthetic history: a composite modulus collapsed many
  issuers to two or three distinct weekly closes, which the new staleness check
  correctly read as stale quotes (71 of 104 names). Now a prime modulus.
- Also fixed the CSV writer's CRLF default, which would have rewritten every
  line of the universe file the first time a name was added through the form.
- Test suite 130 to 148, all green.

=== 2026-07-22 (later)
- Closed the validation gap the methodology's own Validation Plan had left open,
  in `validation.py`: rank stability between snapshots, weight sensitivity
  across twelve named scenarios, shortlist concentration by basket, country and
  sector, and co-movement of weekly spread changes. Surfaced in the snapshot
  report and a new dashboard Validation tab.
- On the fixture universe the weights are not load-bearing: rank correlation
  0.993 to 0.997 under +/-10% per block, and the worst top-10 overlap is 90%
  (Credit and Spread Attractiveness down 10%, PEMEX in, FEMSA out). This needs
  re-running on real data before it is quoted as a result.
- Snapshot manifests now record the SHA-256 and row count of the universe file
  that produced them, so a snapshot is reconstructible and the eventual backtest
  is not survivorship-biased.
- Added execution feasibility: issue size is carried through from
  `AMT_OUTSTANDING` and names below USD 500mm are flagged, plus `hedged_pickup_bps`
  which subtracts a desk-set cross-currency hedging cost from the pickup over
  Brazil so the ranking can be read in the client's economics.
- Hardened the Bloomberg path ahead of the next live run: the three request
  loops were unbounded `while True` over `nextEvent`, so a request that never
  received a RESPONSE would hang the run silently; they now give up after four
  silent waits. A dropped session is reconnected (three attempts) instead of
  failing every remaining issuer with the same error. Every numeric field read
  is coerced, so a field returning text or an array costs one value rather than
  the whole issuer. `IOS_MAX_ISSUERS` runs a preflight over the first N names.
  A history response carrying a securityError no longer raises.

== Open Items
- Desk: fill `state_linked` for the Latin America SOEs (Brazil-domiciled names
  are detected automatically from `country`).
- Bloomberg workflow review: still the gating blocker for full bond coverage.
- Calibration of the flag thresholds (450 bps wide, 7y tenor, 6 distinct
  closes, 3 peers, 3 notches) against a real snapshot once data is unblocked.
