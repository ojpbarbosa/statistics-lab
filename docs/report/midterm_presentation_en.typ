#let accent = rgb("#16385c")
#let muted = luma(110)
#let ink = luma(35)
// dataviz-validated categorical slots (light surface)
#let s1 = rgb("#2a78d6")
#let s2 = rgb("#008300")
#let s3 = rgb("#e87ba4")
#let s4 = rgb("#eda100")
#let s5 = rgb("#1baf7a")
// status palette
#let good = rgb("#0ca30c")
#let warn = rgb("#fab219")
#let crit = rgb("#d03b3b")

#set page(
  paper: "presentation-16-9",
  margin: (x: 2cm, top: 1.5cm, bottom: 1.3cm),
  footer: context [
    #set text(size: 10pt, fill: muted)
    Issuer Opportunity Screener #h(1fr) #counter(page).display("1 / 1", both: true)
  ],
)
#set text(font: ("Helvetica Neue", "Libertinus Serif"), size: 17pt, fill: ink)

#let slide(title, body) = {
  block[
    #text(size: 24pt, weight: "bold", fill: accent)[#title]
    #v(-0.55em)
    #line(length: 100%, stroke: 1.5pt + accent)
  ]
  v(0.8em)
  body
  pagebreak(weak: true)
}

#let tile(number, label) = box(
  fill: accent.lighten(94%), radius: 8pt, inset: (x: 10pt, y: 14pt), width: 100%,
)[
  #align(center)[
    #text(size: 42pt, weight: "bold", fill: accent)[#number] \
    #v(-0.4em)
    #text(size: 13pt, fill: muted)[#label]
  ]
]

#let card(title, body) = box(
  stroke: 1.2pt + accent, radius: 8pt, inset: 12pt, width: 100%, height: 100%,
)[
  #text(size: 15pt, weight: "bold", fill: accent)[#title] \
  #v(0.3em)
  #text(size: 12.5pt)[#body]
]

#let node(title, sub, height: 62pt, dashed: false) = box(
  stroke: (paint: accent, thickness: 1.2pt, dash: if dashed { "dashed" } else { "solid" }),
  radius: 6pt, inset: 8pt, width: 100%, height: height,
)[
  #align(center + horizon)[
    #text(size: 13.5pt, weight: "bold", fill: accent)[#title] \
    #text(size: 10pt, fill: muted)[#sub]
  ]
]

#let arrow = align(center + horizon)[#text(size: 18pt, fill: accent)[→]]

#let dot(color) = box(baseline: 2pt, circle(radius: 6pt, fill: color))

// ---------- 1 · Title ----------
#align(horizon)[
  #text(size: 38pt, weight: "bold", fill: accent)[Issuer Opportunity Screener]
  #v(0.1em)
  #text(size: 24pt)[Midterm Check-in]
  #v(1.2em)
  #text(size: 15pt, fill: muted)[
    COE Credit Trading summer project \
    2026-07-21 (end of week 2 of 4)
  ]
]
#pagebreak()

// ---------- 2 · Purpose ----------
#slide[Why I'm here today][
  #v(0.6em)
  #grid(columns: (1fr, 1fr, 1fr, 1fr), column-gutter: 12pt, rows: 108pt,
    card[Report][what's built and where the project stands],
    card[Validate][framework and criteria choices, with you],
    card[Unblock][where data access stands and the routes around it],
    card[Align][next steps, and a faster feedback cadence],
  )
  #v(1.4em)
  #align(center)[#text(size: 14pt, fill: muted)[A midterm alignment, not the final presentation: the goal is observability and shorter development cycles.]]
]

// ---------- 3 · Status ----------
#slide[On schedule: the framework is operational end to end][
  #grid(columns: (1fr, 1fr, 1fr), column-gutter: 14pt,
    tile[125][names in the screening universe],
    tile[100+][automated tests, runs without a Terminal],
    tile[1][open blocker, external (Bloomberg entitlement)],
  )
  #v(1.5em)
  #text(size: 12pt, fill: muted)[Four-week plan]
  #v(0.3em)
  #grid(columns: (1fr, 1fr, 1fr, 1fr), column-gutter: 3pt,
    box(fill: accent, height: 30pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 12pt, weight: "bold")[Week 1 ✓]]],
    box(fill: accent, height: 30pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 12pt, weight: "bold")[Week 2 ✓]]],
    box(stroke: 1pt + accent, height: 30pt, width: 100%)[#align(center + horizon)[#text(fill: accent, size: 12pt)[Week 3: results]]],
    box(stroke: 1pt + accent, height: 30pt, width: 100%)[#align(center + horizon)[#text(fill: accent, size: 12pt)[Week 4: delivery]]],
  )
  #box(width: 100%)[#h(50%)#text(size: 12pt, fill: crit, weight: "bold")[▲ today]]
]

// ---------- 4 · Architecture ----------
#slide[Everything from universe to dashboard is built and tested][
  #v(1.1em)
  #grid(columns: (1fr, auto, 1fr, auto, 1fr, auto, 1fr, auto, 1fr), column-gutter: 6pt,
    node[Universe][125 names, add / quarantine / restore],
    arrow,
    node[Sources][BLP · BQuant · Hermes · fixture],
    arrow,
    node[Snapshots][versioned, append-only],
    arrow,
    node[Scoring][5 blocks, tiers A/B/C],
    arrow,
    node[Dashboard][screen, movers, reports],
  )
  #v(1.5em)
  #align(center)[#text(size: 14pt, fill: muted)[Every classification carries a plain-language rationale, replicable on the terminal.]]
]

// ---------- 5 · Data integrations ----------
#slide[Four data sources in play, one external gate][
  #v(0.4em)
  #grid(columns: (auto, 1fr, auto), column-gutter: 12pt, row-gutter: 1.2em, align: horizon,
    dot(crit), [*Bloomberg Desktop API* #h(1fr) #text(size: 13pt, fill: muted)[CDS, ratings, equity]],
    text(size: 13pt, fill: crit, weight: "bold")[bond bulk gated; account manager contacted, no reply yet],

    dot(warn), [*BQuant* #h(1fr) #text(size: 13pt, fill: muted)[server-side bond screen]],
    text(size: 13pt, fill: luma(30), weight: "bold")[validation run pending],

    dot(good), [*Hermes internal API* #h(1fr) #text(size: 13pt, fill: muted)[bond EoD tape by date]],
    text(size: 13pt, fill: good, weight: "bold")[bonds live; CDS server-side under discussion with the owner],

    dot(muted), [*Markit Partners* #h(1fr) #text(size: 13pt, fill: muted)[additional credit data]],
    text(size: 13pt, fill: luma(30), weight: "bold")[access requested],
  )
  #v(1.2em)
  #align(center)[#text(size: 13pt, fill: muted)[Whichever route lands first feeds the exact same snapshot, scoring, and dashboard.]]
]

// ---------- 6 · Methodology + why ----------
#slide[How the screen decides, and why][
  #text(size: 13pt, fill: muted)[Viability: spread vs the Brazil benchmark]
  #v(0.3em)
  #grid(columns: (2fr, 1fr, 3fr), column-gutter: 2pt,
    box(fill: crit, height: 32pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 13pt, weight: "bold")[× not viable]]],
    box(fill: warn, height: 32pt, width: 100%)[#align(center + horizon)[#text(fill: luma(30), size: 13pt, weight: "bold")[edge case]]],
    box(fill: good, height: 32pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 13pt, weight: "bold")[✓ viable]]],
  )
  #grid(columns: (2fr, 1fr, 3fr),
    align(right)[#text(size: 11pt, fill: muted)[-20 bps ]],
    align(right)[#text(size: 11pt, fill: muted)[0 ]],
    [],
  )
  #text(size: 12pt, fill: muted)[Anchored on Brazil because that is the client's alternative; the edge case keeps stronger-rated names within 20 bps (e.g. Hyundai, -18 bps, A-).]
  #v(0.9em)
  #text(size: 13pt, fill: muted)[Composite score weights]
  #v(0.3em)
  #grid(columns: (35fr, 20fr, 20fr, 10fr, 15fr), column-gutter: 2pt,
    box(fill: s1, height: 28pt, width: 100%)[#align(center + horizon)[#text(fill: white, weight: "bold", size: 13pt)[35]]],
    box(fill: s2, height: 28pt, width: 100%)[#align(center + horizon)[#text(fill: white, weight: "bold", size: 13pt)[20]]],
    box(fill: s3, height: 28pt, width: 100%)[#align(center + horizon)[#text(fill: luma(30), weight: "bold", size: 13pt)[20]]],
    box(fill: s4, height: 28pt, width: 100%)[#align(center + horizon)[#text(fill: luma(30), weight: "bold", size: 13pt)[10]]],
    box(fill: s5, height: 28pt, width: 100%)[#align(center + horizon)[#text(fill: luma(30), weight: "bold", size: 13pt)[15]]],
  )
  #grid(columns: (35fr, 20fr, 20fr, 10fr, 15fr), column-gutter: 2pt,
    align(center)[#text(size: 10.5pt)[Spread]],
    align(center)[#text(size: 10.5pt)[Credit]],
    align(center)[#text(size: 10.5pt)[Liquidity]],
    align(center)[#text(size: 10.5pt)[Equity]],
    align(center)[#text(size: 10.5pt)[Recognition]],
  )
  #v(0.4em)
  #text(size: 12pt, fill: muted)[Weights mirror the desk's priorities: carry first, then safety, tradability, market read, client fit. Tiers turn scores into action: A pitch-ready (≥ 70), B watchlist (≥ 50), C pass.]
]

// ---------- 7 · Validation asks ----------
#slide[What I want to validate with you][
  #v(0.4em)
  #grid(columns: (1fr, 1fr), rows: (108pt, 108pt), column-gutter: 14pt, row-gutter: 14pt,
    card[Criteria][20 bps tolerance · Sr Non-Preferred inclusion · currency preference],
    card[Universe file][internal ratings · ISINs for Hermes · Bloomberg handle overrides],
    card[Dashboard][is any visualization or metric missing for your workflow?],
    card[Cadence][short weekly check-ins instead of one big handoff?],
  )
  #v(1.0em)
  #align(center)[#text(size: 14pt, fill: muted)[Feedback on the framework and criteria moves more than feedback on individual names.]]
]

// ---------- 8 · Insight 1 ----------
#slide[Insight: the universe shouldn't be a static list][
  #text(size: 12pt, fill: muted)[Today: fully manual ingestion]
  #v(0.3em)
  #grid(columns: (1fr, auto, 1fr, 2.2fr), column-gutter: 6pt,
    node(height: 54pt)[Desk adds a name by hand][one form per name],
    arrow,
    node(height: 54pt)[Static universe][same 125 names until someone edits],
    [],
  )
  #v(0.9em)
  #text(size: 12pt, fill: muted)[Proposed: machine-suggested, desk-approved]
  #v(0.3em)
  #grid(columns: (1.2fr, auto, 1fr, auto, 1fr, auto, 1fr), column-gutter: 6pt,
    node(height: 60pt, dashed: true)[Feeds][Hermes bond tape · index members · new issues],
    arrow,
    node(height: 60pt, dashed: true)[Auto pre-screen][spread vs Brazil, liquidity],
    arrow,
    node(height: 60pt, dashed: true)[Candidate inbox][ranked suggestions],
    arrow,
    node(height: 60pt)[Desk approves][final say stays human],
  )
  #v(1.0em)
  #align(center)[#text(size: 13pt, fill: muted)[Hermes already returns the full bond tape by date: diffing it against the tracked universe yields candidates with spreads pre-computed. Not manual, not brute force.]]
]

// ---------- 9 · Insight 2 ----------
#slide[Insight: from screener to credit copilot][
  #v(0.4em)
  #grid(columns: (1fr, 1fr, 1fr), rows: 128pt, column-gutter: 14pt,
    card[Built-in credit analysis][auto one-pager per name: balance sheet, leverage, covenants, news; the analyst validates instead of assembling],
    card[From screen to monitor][scheduled snapshots plus alerts on viability flips and outsized moves; the desk is told, not asked to look],
    card[Learning loop][desk feedback on names and backtests over accumulated snapshots tune the weights with evidence],
  )
  #v(1.2em)
  #align(center)[#text(size: 14pt, fill: muted)[One lens behind all three: engineering that removes manual work between signal and decision.]]
]

// ---------- 10 · Going forward ----------
#slide[Going forward: shorter loops][
  #v(0.2em)
  #grid(columns: (1fr, 1fr), column-gutter: 14pt,
    box(stroke: 1.2pt + accent, radius: 8pt, inset: 12pt, width: 100%)[
      #text(size: 15pt, weight: "bold", fill: accent)[Week 3] \
      #v(0.3em)
      #set text(size: 13.5pt)
      - First complete snapshot (Hermes or BQuant)
      - Results: tiers, top names, edge cases, movers
      - Desk pass on the universe file
    ],
    box(stroke: 1.2pt + accent, radius: 8pt, inset: 12pt, width: 100%)[
      #text(size: 15pt, weight: "bold", fill: accent)[Week 4] \
      #v(0.3em)
      #set text(size: 13.5pt)
      - Categorized candidate lists
      - Final report
      - Desk presentation and handover
    ],
  )
  #v(1.1em)
  #grid(columns: (auto, 1fr), column-gutter: 14pt, row-gutter: 10pt, align: horizon,
    text(size: 12pt, fill: muted)[until now],
    box(stroke: 1pt + muted, height: 22pt, width: 100%)[#align(center + horizon)[#text(size: 11pt, fill: muted)[one four-week cycle, one big handoff]]],
    text(size: 12pt, fill: muted)[from now],
    grid(columns: (1fr, 1fr, 1fr, 1fr), column-gutter: 8pt,
      box(fill: accent, height: 22pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 11pt)[check-in]]],
      box(fill: accent, height: 22pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 11pt)[check-in]]],
      box(fill: accent, height: 22pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 11pt)[check-in]]],
      box(fill: accent, height: 22pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 11pt)[check-in]]],
    ),
  )
  #v(0.7em)
  #align(center)[#text(size: 14pt, fill: muted)[The groundwork is done; from here, small targets and fast corrections.]]
]
