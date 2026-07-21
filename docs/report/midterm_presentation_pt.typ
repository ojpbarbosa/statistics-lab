#let accent = rgb("#16385c")
#let muted = luma(110)
#let ink = luma(35)
// slots categóricos validados pelo dataviz (superfície clara)
#let s1 = rgb("#2a78d6")
#let s2 = rgb("#008300")
#let s3 = rgb("#e87ba4")
#let s4 = rgb("#eda100")
#let s5 = rgb("#1baf7a")
// paleta de status
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
#set text(font: ("Helvetica Neue", "Libertinus Serif"), size: 17pt, fill: ink, lang: "pt")

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

// ---------- Título ----------
#align(horizon)[
  #text(size: 38pt, weight: "bold", fill: accent)[Issuer Opportunity Screener]
  #v(0.1em)
  #text(size: 24pt)[Progresso Intermediário]
  #v(1.2em)
  #text(size: 15pt, fill: muted)[
    Projeto de verão, COE Credit Trading \
    21/07/2026 (fim da semana 2 de 4)
  ]
]
#pagebreak()

// ---------- Slide 2: status ----------
#slide[No prazo: o framework está operacional de ponta a ponta][
  #grid(columns: (1fr, 1fr, 1fr), column-gutter: 14pt,
    tile[125][nomes no universo de screening],
    tile[100+][testes automatizados, roda sem Terminal],
    tile[1][bloqueio aberto, externo (entitlement Bloomberg)],
  )
  #v(1.6em)
  #text(size: 12pt, fill: muted)[Plano de quatro semanas]
  #v(0.3em)
  #grid(columns: (1fr, 1fr, 1fr, 1fr), column-gutter: 3pt,
    box(fill: accent, height: 30pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 12pt, weight: "bold")[Semana 1 ✓]]],
    box(fill: accent, height: 30pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 12pt, weight: "bold")[Semana 2 ✓]]],
    box(stroke: 1pt + accent, height: 30pt, width: 100%)[#align(center + horizon)[#text(fill: accent, size: 12pt)[Semana 3: resultados]]],
    box(stroke: 1pt + accent, height: 30pt, width: 100%)[#align(center + horizon)[#text(fill: accent, size: 12pt)[Semana 4: entrega]]],
  )
  #box(width: 100%)[#h(50%)#text(size: 12pt, fill: crit, weight: "bold")[▲ hoje]]
]

// ---------- Slide 3: arquitetura ----------
#slide[Do universo ao dashboard, tudo construído e testado][
  #v(1.2em)
  #grid(columns: (1fr, auto, 1fr, auto, 1fr, auto, 1fr, auto, 1fr), column-gutter: 6pt,
    node[Universo][125 nomes, incluir / quarentenar / restaurar],
    arrow,
    node[Fontes][Bloomberg · BQuant · fixture],
    arrow,
    node[Snapshots][versionados, append-only],
    arrow,
    node[Scoring][5 blocos, tiers A/B/C],
    arrow,
    node[Dashboard][screen, movers, relatórios],
  )
  #v(1.6em)
  #align(center)[#text(size: 14pt, fill: muted)[Toda classificação carrega uma justificativa em linguagem simples, replicável no terminal.]]
]

// ---------- Slide 4: metodologia ----------
#slide[Uma regra interpretável mais um score documentado][
  #text(size: 13pt, fill: muted)[Viabilidade: spread vs o benchmark Brasil]
  #v(0.3em)
  #grid(columns: (2fr, 1fr, 3fr), column-gutter: 2pt,
    box(fill: crit, height: 34pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 13pt, weight: "bold")[× não viável]]],
    box(fill: warn, height: 34pt, width: 100%)[#align(center + horizon)[#text(fill: luma(30), size: 13pt, weight: "bold")[edge case]]],
    box(fill: good, height: 34pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 13pt, weight: "bold")[✓ viável]]],
  )
  #grid(columns: (2fr, 1fr, 3fr),
    align(right)[#text(size: 11pt, fill: muted)[-20 bps ]],
    align(right)[#text(size: 11pt, fill: muted)[0 ]],
    [],
  )
  #text(size: 12pt, fill: muted)[Edge case: até 20 bps abaixo do Brasil, mantido apenas com rating estritamente mais forte (ex.: Hyundai, -18 bps, A-).]
  #v(1.1em)
  #text(size: 13pt, fill: muted)[Pesos do score composto]
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
    align(center)[#text(size: 10.5pt)[Crédito]],
    align(center)[#text(size: 10.5pt)[Liquidez]],
    align(center)[#text(size: 10.5pt)[Equity]],
    align(center)[#text(size: 10.5pt)[Reconhecimento]],
  )
  #v(0.4em)
  #text(size: 12pt, fill: muted)[Tiers: A ≥ 70 · B ≥ 50 · C abaixo]
]

// ---------- Slide 5: bloqueio ----------
#slide[Um bloqueio externo, quatro rotas até os dados][
  #v(0.6em)
  #grid(columns: (auto, 1fr, auto), column-gutter: 12pt, row-gutter: 1.25em, align: horizon,
    dot(crit), [*Bloomberg Desktop API* #h(1fr) #text(size: 13pt, fill: muted)[requisições de bonds em lote]],
    text(size: 13pt, fill: crit, weight: "bold")[travada: workflow review, chamado aberto],

    dot(warn), [*Rota de export BQuant* #h(1fr) #text(size: 13pt, fill: muted)[no servidor, mesmo pipeline]],
    text(size: 13pt, fill: luma(30), weight: "bold")[construída, validação pendente],

    dot(good), [*API interna Hermes* #h(1fr) #text(size: 13pt, fill: muted)[bonds históricos EoD, por intervalo de datas]],
    text(size: 13pt, fill: good, weight: "bold")[fetch de bonds em uso; CDS sendo construído no servidor],

    dot(muted), [*Markit Partners* #h(1fr) #text(size: 13pt, fill: muted)[dados adicionais de crédito]],
    text(size: 13pt, fill: luma(30), weight: "bold")[acesso solicitado],
  )
  #v(1.4em)
  #align(center)[#text(size: 13pt, fill: muted)[Qualquer rota que chegar primeiro alimenta exatamente o mesmo snapshot, scoring e dashboard.]]
]

// ---------- Slide 6: próximos passos ----------
#slide[Semanas 3 e 4: dados, resultados, entrega][
  #v(0.6em)
  #grid(columns: (1fr, 1fr), column-gutter: 16pt,
    box(stroke: 1.2pt + accent, radius: 8pt, inset: 14pt, width: 100%)[
      #text(size: 16pt, weight: "bold", fill: accent)[Semana 3] \
      #v(0.5em)
      #set text(size: 14.5pt)
      - Primeiro snapshot completo (BQuant, Hermes ou entitlement liberado)
      - Rodada de resultados: tiers, principais nomes, edge cases, movers
      - Rodada da mesa no arquivo do universo
    ],
    box(stroke: 1.2pt + accent, radius: 8pt, inset: 14pt, width: 100%)[
      #text(size: 16pt, weight: "bold", fill: accent)[Semana 4] \
      #v(0.5em)
      #set text(size: 14.5pt)
      - Listas categorizadas de candidatos (spread alto, equilibrados, edge cases de qualidade)
      - Relatório final
      - Apresentação à mesa e handover do código
    ],
  )
]
