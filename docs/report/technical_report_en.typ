#set page(
  paper: "a4",
  margin: (x: 2.1cm, y: 2.3cm),
  numbering: "1",
  header: context {
    if counter(page).get().first() > 1 [
      #set text(size: 8pt, style: "italic", fill: luma(90))
      XP :: Issuer Opportunity Screener
      #h(1fr) Technical Report: Features, Weights, and Data Quality
      #v(-0.6em)
      #line(length: 100%, stroke: 0.4pt + luma(180))
    ]
  },
)
#set text(font: "New Computer Modern", size: 10pt, lang: "en")
#set par(justify: true, leading: 0.62em)
#set heading(numbering: "1.1")
#show heading.where(level: 1): it => {
  v(0.9em, weak: true)
  block(text(size: 13pt, weight: "bold", it))
  v(0.25em, weak: true)
}
#show heading.where(level: 2): it => {
  v(0.6em, weak: true)
  block(text(size: 11pt, weight: "bold", it))
  v(0.15em, weak: true)
}
#show table.cell.where(y: 0): strong
#set table(stroke: 0.4pt + luma(190), inset: 6pt)

#align(center)[
  #text(size: 9pt, fill: luma(80))[XP :: Issuer Opportunity Screener]
  #v(0.3em)
  #text(size: 17pt, weight: "bold")[Technical Report]
  #v(0.2em)
  #text(size: 12pt)[Features, Weights, and Data Quality]
  #v(0.5em)
  #text(size: 10pt)[João Pedro Ferreira Barbosa #h(1em) · #h(1em) 22 July 2026]
]
#v(0.8em)
#line(length: 100%, stroke: 0.6pt)
#v(0.5em)

_Summer project. Period covered: 2026-07-09 to 2026-07-22. This document is the
complete technical record of what was built, how each piece works, and why each
choice was made. It goes deepest on the two areas flagged as the decisive ones:
data quality and feature selection (exact definition of each feature, how many
features there are, and their weights)._

= What the system is

The Issuer Opportunity Screener ranks corporate issuers as candidates for
structured note (COE) issuance aimed at Brazilian investors. The commercial
premise, agreed with the desk on 2026-07-13: Brazilian investors have little
appetite for names trading far through Brazil, so every spread is anchored
against the Brazil sovereign benchmark, and the screen favours recognisable
names with real carry.

The system takes a desk-editable universe of 125 issuers, pulls credit market
data for each, writes an immutable snapshot, scores every name on a documented
composite, and presents the result as a ranked screen with a plain-language
rationale for every number.

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Layer*], [*Responsibility*],
  [`universe.py`], [Load and validate `data/universe.csv`, the desk's own inputs],
  [`sources/`], [One adapter per data route: Bloomberg, BQuant export, Hermes, fixture],
  [`pipeline.py`], [Orchestrate one pull: universe, fetch, write snapshot],
  [`snapshots.py`], [Append-only parquet snapshots plus a manifest],
  [`scoring.py`], [The composite, the viability rule, and the flags],
  [`validation.py`], [Stability, weight sensitivity, concentration, co-movement],
  [`insights.py`], [Movers between snapshots and rule-based callouts],
  [`reports.py`], [The weekly Markdown evidence artifact],
  [`app.py`], [Streamlit dashboard],
)

Dependencies run strictly one way, left to right. Nothing below `sources/`
touches Bloomberg, so the entire scoring and validation layer is testable
without a Terminal. There are 168 automated tests.

= Feature catalogue

This is the core of the methodology. There are *15 features* (called signals in
the code), grouped into *5 blocks*. Each feature maps a raw market observation
onto a 0 to 100 score. A feature with no data returns nothing rather than a
zero, which matters: zero is a statement about the credit, absence is a
statement about the data.

Every band below is a deliberate choice, and every one is a constant in
`scoring.py` that the desk can move.

== Block 1: Credit and Spread Attractiveness (weight 0.35, 5 features)

This block carries the most weight because spread is the reason the trade
exists. It asks the same question five ways: is this spread attractive in
absolute terms, against the name's own history, and against its peers.

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Feature*], [*Definition and band*],
  [`spread_level`],
  [$min(s / 6, 100)$ where $s$ is the primary spread in bps. Reaches 100 at 600
  bps and saturates there. *Why 600:* beyond roughly 600 bps the name stops
  being carry and starts being distress for this client base. A name at 900 bps
  is not three times more attractive than one at 300; it is usually not sellable
  at all. The saturation encodes that. This is the band most worth challenging
  with the desk.],

  [`history_percentile`],
  [Share of the last year's weekly closes at or below today's spread, times 100.
  Requires at least 12 weekly points, and is suppressed entirely when the
  history is stale (see 5.3). *Why:* answers "is this name wide for itself",
  which is the cleanest relative-value question available without a curve model.],

  [`vs_1y_ma`],
  [$"clamp"(50 dot s / mu)$ where $mu$ is the 1y mean. Scores 50 when the name
  trades at its own average and 100 at twice the average. *Why centred at 50:*
  trading at your own average is neither cheap nor rich, so it should sit in the
  middle of the scale rather than at an end.],

  [`vs_1y_p75`],
  [$"clamp"(100 dot s / p_75)$ where $p_75$ is the 1y 75th percentile. Reaches
  100 when the name trades at the wide end of its own year. *Why the 75th and
  not the maximum:* the maximum of a year of weekly closes is usually a single
  stress print, so anchoring on it would make every normal week look cheap.],

  [`vs_peer_median`],
  [$"clamp"(50 + 50 dot (s - m) / m)$ where $m$ is the median primary spread of
  the other names in the same basket. Scores 50 at the peer median and 100 at
  twice it. Requires at least 3 peers with a spread, otherwise it returns
  nothing. *Why the minimum:* a "median" computed from one other bond is not a
  median, and in thin baskets it was effectively a coin flip between two names.],
)

== Block 2: Credit Quality and Risk (weight 0.20, 3 features)

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Feature*], [*Definition and band*],
  [`external_rating`],
  [$100 - r dot 100 / 21$ where $r$ is the rating rank on a 22-level scale (AAA
  is 0, D is 21). One notch is worth 4.76 points. The rank is the median across
  every provider that resolved (Moody's, S&P, Fitch, DBRS, KBRA, Bloomberg
  composite), mapped onto the S&P scale. *Why linear:* a notch is a notch, and
  any convexity would be an unjustified opinion about default probability that
  the screen has no data to support.],

  [`internal_rating`],
  [Same formula applied to the desk's own internal rating from `universe.csv`.
  Present so desk judgment enters the score explicitly rather than as an
  override applied afterwards.],

  [`rating_trend`],
  [Positive outlook or watch scores 75, stable 50, negative 25, absent nothing.
  *Why modest:* an outlook is a forward opinion, not a fact, so it tilts the
  block rather than dominating it. This feature was specified in the original
  methodology and had never been implemented; the rating normaliser was actively
  discarding the watch markers it needs.],
)

== Block 3: Market Liquidity and Accessibility (weight 0.20, 3 features)

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Feature*], [*Definition and band*],
  [`cds_available`], [100 when a 5Y CDS quote resolved, 0 otherwise.],
  [`cds_liquidity`], [A quote-availability proxy, used as-is. Currently 100
  whenever a quote exists, which makes it a duplicate of `cds_available` in
  practice. This is the weakest feature in the model and is named as such in
  section 8.],
  [`bond_available`], [100 when an eligible senior unsecured bond was selected, 0 otherwise.],
)

This block is honest about being a proxy. It measures whether the instruments
are quotable at all, not how tight the bid-ask is or whether size can trade.

== Block 4: Equity Overlay (weight 0.10, 3 features)

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Feature*], [*Definition and band*],
  [`momentum_3m`], [$"clamp"(50 + Delta_(3m))$ where $Delta$ is the percentage
  price change. Flat scores 50; +50% saturates at 100. Centred on flat.],
  [`momentum_12m`], [$"clamp"(50 + Delta_(12m) / 2)$. The halving reflects that
  a year of price change is roughly twice as dispersed as a quarter, so the same
  band would otherwise saturate constantly.],
  [`recommendations`], [$"clamp"(50 + 50 dot b)$ where $b = ("buys" - "sells") /
  "total"$, which is bounded in $[-1, 1]$ and therefore maps exactly onto 0 to
  100 with no clipping.],
)

The whole block is dropped for unlisted issuers rather than scored as zero.

== Block 5: Recognition and Client Fit (weight 0.15, 1 feature)

`recognition` is the desk-set household-name score from `universe.csv`, on a
documented 0 to 100 scale, used as-is. It is the only purely judgmental input in
the model and it carries 15% of the weight. A measured proxy (media heat) was
consciously deferred. Section 8 proposes an independent second scoring pass to
make it defensible.

= From features to a ranking

Each block score is the *mean of its available features*. The composite is the
weighted mean of the block scores, *renormalised over the blocks that actually
produced a score*:

$ S = (sum_(b in A) w_b dot C_b) / (sum_(b in A) w_b) $

where $A$ is the set of blocks with data. Tiers: A at 70 and above, B at 50 and
above, C below.

*The renormalisation had a serious side effect, now fixed.* Dropping a block
does not penalise a name, it removes whatever that block would have said. For a
900 bps name with no rating, the Credit Quality block vanished and the composite
came out at *77.1 (Tier A)*. The identical name rated CCC+ scored *65.3 (Tier
B)*. The screen was systematically promoting exactly the profile you would least
want to hand a client: a very wide spread that nobody rates. An unrated name can
now no longer reach Tier A, and every row reports its `coverage`, the share of
block weight that actually scored.

= Are the weights load-bearing?

The weights 35/20/20/10/15 are desk judgment. The honest question is whether the
ranking is driven by the evidence or by that judgment. `validation.py` answers it
by re-scoring the whole universe under *12 named scenarios*: each of the five
block weights moved up and down by 10%, plus a spread-led and a quality-led
combined tilt. For each scenario it reports the rank correlation against the
documented weights and the share of the top 10 that survives.

On the current synthetic universe (125 names, 104 scored):

#table(
  columns: (1fr, auto),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Measure*], [*Result*],
  [Scenarios], [12],
  [Mean rank correlation vs documented weights], [0.997],
  [Worst rank correlation], [0.993 (quality-led tilt)],
  [Worst top-10 overlap], [90% (Credit and Spread Attractiveness down 10%)],
  [Names that moved in the worst case], [PEMEX in, FEMSA out],
)

Read plainly: under every scenario tested, at least 9 of the top 10 names are
the same, and the ranking correlation never falls below 0.99. On this data the
weights are a presentation choice, not the answer. The evidence is doing the
work.

*Two caveats stated up front.* First, this is synthetic data; the run must be
repeated on the live universe before the number is quoted as a result. Second,
and more important, *this tests the weights, not the bands*. The saturation
points in section 2 (600 bps, the 75th percentile, the halved 12-month
momentum) are untested in the same way. Band sensitivity is the single most
valuable next piece of validation and is named as such in section 8.

= Data quality

== Where the data comes from

#table(
  columns: (auto, 1.1fr, 1fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Route*], [*What it provides*], [*Status*],
  [Bloomberg Desktop API], [CDS, bonds, ratings, equity, history: everything],
  [Gated by an entitlement workflow review],
  [BQuant], [Server-side bond screen under different entitlements], [Built, validation run pending],
  [Hermes (XP internal)], [Bond EoD by ISIN, G-spread proxy anchored on Brazil], [Built, bonds only],
  [Markit], [Additional credit data], [Access requested],
  [Fixture], [Deterministic synthetic universe], [Used for tests and demos],
)

The Bloomberg gate (`responseError` LIMIT / `WORKFLOW_REVIEW_NEEDED`) is an
entitlement decision, not a code failure. The request surface was minimised in
response: static fields for all bond candidates, pricing fields only for the one
selected bond per issuer.

== Coverage is measured, not assumed

Every snapshot manifest records field-level coverage. On the current synthetic
run: CDS 66%, bond z-spread 83%, ratings 83%, equity 66%. Every name that fails
to score is listed with the reason, and every partially-covered name carries
`quality_notes` explaining what is missing.

== Defects found in live runs, and what each taught us

The following were found by running against real Bloomberg data and are the
reason several features look the way they do.

#table(
  columns: (1fr, 1.35fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Defect*], [*Fix and lesson*],
  [Bond price history polluting spread history (the Xerox +1668 bps case)],
  [A bond's `PX_LAST` is a price, not a spread. History now uses `Z_SPRD_MID`
  for bonds and `PX_LAST` only for CDS. Lesson: a field name that works for one
  instrument can be silently wrong for another.],

  [The instruments lookup returned the CDS curve into bond eligibility],
  [Securities are split before eligibility so a CDS contract can never be
  selected as a bond.],

  [Ratings were only requested on equities],
  [Ratings are now merged provider-agnostically across bond, then CDS, then
  equity, covering six providers.],

  [The viability edge case never fired without ratings],
  [Falls back to the desk's internal rating.],

  [Distressed or stale bond selections (the DISH profile)],
  [Z-spread above 1000 bps or price below 50 is flagged for review rather than
  silently ranked.],

  [Flat quote histories read as stable credits],
  [A history with fewer than 6 distinct weekly closes is now treated as an
  unrefreshed quote. The percentile, moving-average and 75th-percentile features
  are suppressed on it. Before this, a name nobody had quoted in months would be
  confidently announced as trading at the 100th percentile of its own range.],

  [Split ratings collapsed silently],
  [A 4-notch disagreement between providers was averaged into a rating nobody
  published. Now flagged, and the viability gate reads the weakest provider.],

  [The universe writer erased ISINs],
  [`UNIVERSE_FIELDS` omitted `isin`, so adding a name through the dashboard form
  silently dropped every ISIN in the file, which would have broken the Hermes
  route. Fixed and covered by a test.],
)

== The flag system

Eleven flags annotate a rank without changing it. They exist because a number
can be arithmetically correct and still mean something other than it appears.

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Flag*], [*Meaning*],
  [`unrated`], [No rating from any provider or the desk: the composite has no credit-quality block],
  [`split_rating`], [Providers disagree by 3 or more notches; viability reads the weakest],
  [`stale_history`], [Fewer than 6 distinct weekly closes: an unrefreshed quote, not a stable credit],
  [`thin_peers`], [Fewer than 3 basket peers with a spread, so no peer-median comparison],
  [`subordinated`], [Bond ranks below senior preferred: part of the spread is structural, not credit],
  [`long_tenor`], [Bond runs beyond 7 years against a 5Y CDS standard: part of the pickup is curve],
  [`sovereign_correlated`], [Brazil-domiciled or state-linked: viable versus Brazil is not diversification from Brazil],
  [`cheap_for_a_reason`], [At or beyond 450 bps with a negative outlook: wide because the credit is deteriorating],
  [`benchmark_mismatch`], [Bond z-spread measured against Brazil's CDS because no sovereign bond spread was available],
  [`benchmark_sensitive`], [The viability verdict flips depending on which Brazil leg is used],
  [`small_issue`], [Below USD 500mm outstanding: too small to support a note program],
)

= The viability rule

A name is viable when its spread is at or above Brazil, or within 20 bps through
Brazil with a strictly stronger rating. Three refinements make the comparison
honest.

*Conservative on splits.* The gate reads the weakest rating any provider
assigned, not the median. The median can invent a rating nobody published: S&P A
and Moody's B1 produce a median of BBB-, which clears the gate against Brazil's
BB, while the conservative read of B+ does not. A risk gate should read the
conservative side.

*Like-for-like benchmark.* An issuer priced off its 5Y CDS is compared against
Brazil's 5Y CDS; an issuer priced off a bond z-spread is compared against
Brazil's benchmark bond z-spread. Previously every issuer was compared against
the sovereign CDS regardless, so a bond-priced name was measured apples to
oranges. Names whose verdict flips between the two legs are flagged.

*Even-median tie-break.* With an even number of providers the median falls
between two notches. Python's banker's rounding made the tie-break direction
depend on position on the scale: A-/BBB+ resolved to A- (the stronger side)
while BBB+/BBB resolved to BBB (the weaker). It now always resolves to the
weaker side. A methodology decision was being made by a rounding mode.

= Validation, reproducibility, and movers

*Rank stability.* Spearman rank correlation of composites between two snapshots,
plus tier changes, viability flips, and the mean composite move. A screen that
reshuffles week to week is measuring noise.

*Concentration.* HHI and largest-bucket share of the shortlist by basket,
country, and sector, with warnings above HHI 0.30 or a 50% single bucket. The
screen ranks names one at a time, but the product is a basket: ten Tier A names
in one country is the same bet ten times. Current top 10: basket HHI 0.20,
country HHI 0.24 (largest Brazil at 30%), sector HHI 0.18.

*Co-movement.* Mean pairwise correlation of weekly spread changes across the
shortlist, currently 0.31 over 36 pairs. On changes rather than levels, which
would correlate on trend alone.

*Movers.* Viability flips are attributed between the issuer and the sovereign.
Brazil's own CDS routinely moves more than the 20 bps tolerance in a week, so a
name can flip with nothing having happened to the credit. The callout says which
one moved.

*Reproducibility.* Each snapshot manifest records the SHA-256 and row count of
the universe file that produced it. The universe is mutable and quarantine
removes names, so without this a snapshot cannot be reconstructed and any
backtest over the snapshot history would be survivorship-biased.

*Client economics.* `hedged_pickup_bps` subtracts a desk-set cross-currency
hedging cost from the pickup over Brazil, so the ranking can be read in the
economics of a BRL-hedged note. The cost is an input, not a market observation:
the screener has no cross-currency basis feed, and pretending otherwise would be
the wrong kind of precision.

= Known limitations and open decisions

These are stated plainly because they are the honest boundary of what the
current system supports.

+ *Band sensitivity is untested.* Section 4 validates the weights. The
  saturation bands in section 2 have had no equivalent treatment. This is the
  highest-value next piece of work.
+ *`cds_liquidity` is nearly vacuous.* It duplicates `cds_available` in
  practice. A real liquidity measure needs bid-ask or trade data.
+ *Recognition is unaudited judgment* carrying 15% of the weight. Two desk
  members scoring independently and reporting the disagreement would cost an
  hour and make it defensible.
+ *One bond per issuer.* Curve shape and issue-specific features (callables,
  sinking funds) are out of scope, and callable z-spreads are not comparable to
  bullets.
+ *No FX or cross-currency basis feed.* The hedging cost is a desk input.
+ *`state_linked` needs a desk pass* for the Latin America SOEs. Brazil-domiciled
  names are detected automatically from `country`.
+ *The Bloomberg entitlement remains the gating blocker* for full coverage.

= Engineering

168 automated tests, all passing. A deterministic fixture source runs the whole
system without a Terminal, and it deliberately generates the awkward cases:
missing CDS, unlisted equity, partial history, fetch failure, subordinated and
long-dated bonds, and a split rating with a negative watch.

Ahead of the next live run the Bloomberg adapter was hardened:

- The three request loops were unbounded `while True` over `nextEvent`, so a
  request that never received a RESPONSE would spin forever. A 125-name run
  would have hung silently with no way to tell which request died. They now give
  up after four silent 30-second waits.
- A dropped session is reconnected, up to three attempts, instead of failing
  every remaining issuer with the same error and wasting the run.
- Every numeric field read is coerced, so a field returning text or an array
  costs one value rather than the whole issuer.
- A history response carrying a `securityError` no longer raises.
- `IOS_MAX_ISSUERS=3` runs a preflight over the first few names before
  committing to the full universe. Recommended before every long run.

= Appendix A: constants

#table(
  columns: (auto, auto, 1fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Constant*], [*Value*], [*Meaning*],
  [Block weights], [35/20/20/10/15], [Spread, quality, liquidity, equity, recognition],
  [Tier cuts], [70 / 50], [A / B thresholds on the composite],
  [`VIABILITY_TOLERANCE_BPS`], [20], [How far through Brazil a stronger name may trade],
  [`SPLIT_RATING_NOTCHES`], [3], [Provider disagreement that counts as a split],
  [`MIN_HISTORY_POINTS`], [12], [Weekly points needed for a percentile],
  [`MIN_HISTORY_UNIQUE`], [6], [Distinct closes below which a quote reads as stale],
  [`MIN_PEERS`], [3], [Basket peers needed for a peer median],
  [`LONG_TENOR_YEARS`], [7], [Bond tenor beyond which curve, not credit],
  [`WIDE_SPREAD_BPS`], [450], [Wide enough that a negative outlook is a warning],
  [`MIN_ISSUE_SIZE_USD`], [500mm], [Issue size needed for a note program],
  [`MOVE_THRESHOLD_BPS`], [15], [Move that counts as a tightener or widener],
  [`OWN_HISTORY_HIGH_PCT`], [90], [Percentile that triggers the own-range callout],
)

= Appendix B: environment variables

`IOS_SOURCE` selects the data route (`bloomberg`, `bquant`, `hermes`,
`fixture`). `IOS_MAX_ISSUERS` limits a preflight run. `IOS_LOG_LEVEL=trace`
prints every candidate and field decision. `IOS_BOND_CURRENCIES` and
`IOS_TENOR_MIN_YEARS` / `IOS_TENOR_MAX_YEARS` set bond eligibility.
`IOS_HEDGE_COST_BPS` sets the cross-currency hedging cost. `IOS_HERMES_*`
configure the internal API route. `IOS_AUTO_QUARANTINE` moves unscored names out
of the universe and is deliberately off while data access is being unblocked.
