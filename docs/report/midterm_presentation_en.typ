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
    #text(size: 25pt, weight: "bold", fill: accent)[#title]
    #v(-0.55em)
    #line(length: 100%, stroke: 1.5pt + accent)
  ]
  v(0.9em)
  body
  pagebreak(weak: true)
}

#let tile(number, label) = box(
  fill: accent.lighten(94%), radius: 8pt, inset: (x: 10pt, y: 14pt), width: 100%,
)[
  #align(center)[
    #text(size: 44pt, weight: "bold", fill: accent)[#number] \
    #v(-0.4em)
    #text(size: 13pt, fill: muted)[#label]
  ]
]

#let node(title, sub) = box(
  stroke: 1.2pt + accent, radius: 6pt, inset: 9pt, width: 100%, height: 62pt,
)[
  #align(center + horizon)[
    #text(size: 14pt, weight: "bold", fill: accent)[#title] \
    #text(size: 10.5pt, fill: muted)[#sub]
  ]
]

#let arrow = align(center + horizon)[#text(size: 20pt, fill: accent)[→]]

#let dot(color) = box(baseline: 2pt, circle(radius: 6pt, fill: color))

// ---------- Title ----------
#align(horizon)[
  #text(size: 38pt, weight: "bold", fill: accent)[Issuer Opportunity Screener]
  #v(0.1em)
  #text(size: 24pt)[Midterm Progress]
  #v(1.2em)
  #text(size: 15pt, fill: muted)[
    COE Credit Trading summer project \
    2026-07-21 (end of week 2 of 4)
  ]
]
#pagebreak()

// ---------- Slide 2: status ----------
#slide[On schedule: the framework is operational end to end][
  #grid(columns: (1fr, 1fr, 1fr), column-gutter: 14pt,
    tile[125][names in the screening universe],
    tile[100+][automated tests, runs without a Terminal],
    tile[1][open blocker, external (Bloomberg entitlement)],
  )
  #v(1.6em)
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

// ---------- Slide 3: architecture ----------
#slide[Everything from universe to dashboard is built and tested][
  #v(1.2em)
  #grid(columns: (1fr, auto, 1fr, auto, 1fr, auto, 1fr, auto, 1fr), column-gutter: 6pt,
    node[Universe][125 names, add / quarantine / restore],
    arrow,
    node[Sources][Bloomberg · BQuant · fixture],
    arrow,
    node[Snapshots][versioned, append-only],
    arrow,
    node[Scoring][5 blocks, tiers A/B/C],
    arrow,
    node[Dashboard][screen, movers, reports],
  )
  #v(1.6em)
  #align(center)[#text(size: 14pt, fill: muted)[Every classification carries a plain-language rationale, replicable on the terminal.]]
]

// ---------- Slide 4: methodology ----------
#slide[One interpretable rule plus a documented score][
  #text(size: 13pt, fill: muted)[Viability: spread vs the Brazil benchmark]
  #v(0.3em)
  #grid(columns: (2fr, 1fr, 3fr), column-gutter: 2pt,
    box(fill: crit, height: 34pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 13pt, weight: "bold")[× not viable]]],
    box(fill: warn, height: 34pt, width: 100%)[#align(center + horizon)[#text(fill: luma(30), size: 13pt, weight: "bold")[edge case]]],
    box(fill: good, height: 34pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 13pt, weight: "bold")[✓ viable]]],
  )
  #grid(columns: (2fr, 1fr, 3fr),
    align(right)[#text(size: 11pt, fill: muted)[-20 bps ]],
    align(right)[#text(size: 11pt, fill: muted)[0 ]],
    [],
  )
  #text(size: 12pt, fill: muted)[Edge case: within 20 bps through Brazil, kept only with a strictly stronger rating (e.g. Hyundai, -18 bps, A-).]
  #v(1.1em)
  #text(size: 13pt, fill: muted)[Composite score weights]
  #v(0.3em)
  #grid(columns: (35fr, 20fr, 20fr, 10fr, 15fr), column-gutter: 2pt,
    box(fill: s1, height: 30pt, width: 100%)[#align(center + horizon)[#text(fill: white, weight: "bold", size: 13pt)[35]]],
    box(fill: s2, height: 30pt, width: 100%)[#align(center + horizon)[#text(fill: white, weight: "bold", size: 13pt)[20]]],
    box(fill: s3, height: 30pt, width: 100%)[#align(center + horizon)[#text(fill: luma(30), weight: "bold", size: 13pt)[20]]],
    box(fill: s4, height: 30pt, width: 100%)[#align(center + horizon)[#text(fill: luma(30), weight: "bold", size: 13pt)[10]]],
    box(fill: s5, height: 30pt, width: 100%)[#align(center + horizon)[#text(fill: luma(30), weight: "bold", size: 13pt)[15]]],
  )
  #grid(columns: (35fr, 20fr, 20fr, 10fr, 15fr), column-gutter: 2pt,
    align(center)[#text(size: 10.5pt)[Spread]],
    align(center)[#text(size: 10.5pt)[Credit]],
    align(center)[#text(size: 10.5pt)[Liquidity]],
    align(center)[#text(size: 10.5pt)[Equity]],
    align(center)[#text(size: 10.5pt)[Recognition]],
  )
  #v(0.4em)
  #text(size: 12pt, fill: muted)[Tiers: A ≥ 70 · B ≥ 50 · C below]
]

// ---------- Slide 5: blocker ----------
#slide[One external blocker, four routes to the data][
  #v(0.6em)
  #grid(columns: (auto, 1fr, auto), column-gutter: 12pt, row-gutter: 1.25em, align: horizon,
    dot(crit), [*Bloomberg Desktop API* #h(1fr) #text(size: 13pt, fill: muted)[bulk bond requests]],
    text(size: 13pt, fill: crit, weight: "bold")[gated: workflow review, ticket open],

    dot(warn), [*BQuant export route* #h(1fr) #text(size: 13pt, fill: muted)[server-side, same pipeline]],
    text(size: 13pt, fill: luma(30), weight: "bold")[built, validation run pending],

    dot(good), [*Hermes internal API* #h(1fr) #text(size: 13pt, fill: muted)[historical bonds EoD, by date range]],
    text(size: 13pt, fill: good, weight: "bold")[bonds fetch in use; building CDS server-side],

    dot(muted), [*Markit Partners* #h(1fr) #text(size: 13pt, fill: muted)[additional credit data]],
    text(size: 13pt, fill: luma(30), weight: "bold")[access requested],
  )
  #v(1.4em)
  #align(center)[#text(size: 13pt, fill: muted)[Whichever route lands first feeds the exact same snapshot, scoring, and dashboard.]]
]

// ---------- Slide 6: next ----------
#slide[Weeks 3 and 4: data, results, delivery][
  #v(0.6em)
  #grid(columns: (1fr, 1fr), column-gutter: 16pt,
    box(stroke: 1.2pt + accent, radius: 8pt, inset: 14pt, width: 100%)[
      #text(size: 16pt, weight: "bold", fill: accent)[Week 3] \
      #v(0.5em)
      #set text(size: 14.5pt)
      - First complete snapshot (BQuant, Hermes, or cleared entitlement)
      - Results pass: tiers, top names, edge cases, movers
      - Desk pass on the universe file
    ],
    box(stroke: 1.2pt + accent, radius: 8pt, inset: 14pt, width: 100%)[
      #text(size: 16pt, weight: "bold", fill: accent)[Week 4] \
      #v(0.5em)
      #set text(size: 14.5pt)
      - Categorized candidate lists (high spread, balanced, quality edge cases)
      - Final report
      - Desk presentation and code handover
    ],
  )
]
