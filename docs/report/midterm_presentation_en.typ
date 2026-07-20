#let accent = rgb("#16385c")
#let muted = luma(110)

#set page(
  paper: "presentation-16-9",
  margin: (x: 2cm, top: 1.6cm, bottom: 1.4cm),
  footer: context [
    #set text(size: 11pt, fill: muted)
    Issuer Opportunity Screener #h(1fr) #counter(page).display("1 / 1", both: true)
  ],
)
#set text(font: ("Helvetica Neue", "Libertinus Serif"), size: 19pt)
#set list(marker: text(fill: accent)[--], spacing: 0.9em)
#set enum(spacing: 0.9em)

#let slide(title, body) = {
  block[
    #text(size: 27pt, weight: "bold", fill: accent)[#title]
    #v(-0.5em)
    #line(length: 100%, stroke: 1.5pt + accent)
  ]
  v(0.6em)
  body
  pagebreak(weak: true)
}

// Title slide
#align(horizon)[
  #text(size: 38pt, weight: "bold", fill: accent)[Issuer Opportunity Screener]
  #v(0.1em)
  #text(size: 24pt)[Midterm Progress]
  #v(1.2em)
  #text(size: 15pt, fill: muted)[
    COE Credit Trading summer project \
    2026-07-20 (end of week 2 of 4)
  ]
]
#pagebreak()

#slide[BLUF: bottom line up front][
  #v(0.4em)
  #block(fill: accent.lighten(92%), inset: 14pt, radius: 6pt, width: 100%)[
    *The screening framework is built and fully operational end to end, and the project is on schedule.*
  ]
  #v(0.6em)
  - The only open blocker is *external*: a Bloomberg entitlement review gating bulk bond data. Two mitigations are already built and one is pending a validation run.
  - Weeks 3 and 4: run the full 125-name universe, fill the results, and deliver the final report and desk presentation.
]

#slide[What has been delivered][
  - *Universe*: 125 curated names, desk-editable, with governance and a full lifecycle (add, quarantine with reasons, restore).
  - *Data pipeline*: versioned append-only snapshots; 5Y CDS first with bond z-spread fallback, one representative senior unsecured USD bond, provider-agnostic ratings, equity overlay, 1y weekly spread history.
  - *Methodology*: documented composite score and the desk viability rule vs Brazil, including the 20 bps edge case.
  - *Dashboard*: ranked screen, market map, movers between snapshots, edge-case log, data quality, one-click report export.
  - *Quality*: 100+ automated tests; a fixture source lets the whole system run and demo on any machine, no Terminal needed.
]

#slide[How the screen decides][
  #v(0.3em)
  *Viability vs the Brazil benchmark*
  #table(
    columns: (1fr, auto),
    stroke: 0.5pt + luma(200),
    inset: 9pt,
    [Spread at or above Brazil], [Viable],
    [Within 20 bps through Brazil, rating strictly stronger], [Viable (edge case)],
    [Otherwise], [Not viable],
  )
  #v(0.5em)
  *Composite score*: spread attractiveness 35, credit quality 20, liquidity 20, equity overlay 10, recognition 15. Tiers A / B / C.
  Every classification carries a plain-language rationale and is replicable on the terminal.
]

#slide[Blocker and limitations][
  - *Bloomberg entitlement (external)*: bulk bond requests gated by the Desktop API workflow review; ticket open with the rep.
  - *Mitigations built*: minimized request surface (pricing only for the selected bond per issuer) and a BQuant server-side export route feeding the same pipeline (validation run pending).
  - *Known limits*: one bond per issuer; extreme spreads flagged as outliers for separate review, not silently ranked; non-USD bonds indicative only; recognition score is desk-set; internal-rating fallback labeled provisional.
]

#slide[Next steps (weeks 3 and 4)][
  + Unblock full data: validate the BQuant route and/or close the workflow review, then land the first complete snapshot.
  + Results pass: coverage, tier distribution, top names with rationale, edge cases, movers narrative.
  + Desk pass on the universe: internal ratings, handle overrides, Sr Non-Preferred and currency confirmations.
  + Categorized results for presentation: high spread / high risk, balanced candidates, high-quality edge cases.
  + Final report, code handover, desk presentation.
]
