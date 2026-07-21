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

// ---------- 1 · Título ----------
#align(horizon)[
  #text(size: 38pt, weight: "bold", fill: accent)[Issuer Opportunity Screener]
  #v(0.1em)
  #text(size: 24pt)[Check-in de Meio de Percurso]
  #v(1.2em)
  #text(size: 15pt, fill: muted)[
    Projeto de verão, COE Credit Trading \
    21/07/2026 (fim da semana 2 de 4)
  ]
]
#pagebreak()

// ---------- 2 · Propósito ----------
#slide[Por que estou aqui hoje][
  #v(0.6em)
  #grid(columns: (1fr, 1fr, 1fr, 1fr), column-gutter: 12pt, rows: 108pt,
    card[Reportar][o que está construído e onde o projeto está],
    card[Validar][escolhas de framework e critérios, com vocês],
    card[Destravar][onde está o acesso a dados e as rotas alternativas],
    card[Alinhar][próximos passos e uma cadência mais rápida de feedback],
  )
  #v(1.4em)
  #align(center)[#text(size: 14pt, fill: muted)[Um alinhamento de meio de percurso, não a apresentação final: o objetivo é observabilidade e ciclos de desenvolvimento mais curtos.]]
]

// ---------- 3 · Status ----------
#slide[No prazo: o framework está operacional de ponta a ponta][
  #grid(columns: (1fr, 1fr, 1fr), column-gutter: 14pt,
    tile[125][nomes no universo de screening],
    tile[100+][testes automatizados, roda sem Terminal],
    tile[1][bloqueio aberto, externo (entitlement Bloomberg)],
  )
  #v(1.5em)
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

// ---------- 4 · Arquitetura ----------
#slide[Do universo ao dashboard, tudo construído e testado][
  #v(1.1em)
  #grid(columns: (1fr, auto, 1fr, auto, 1fr, auto, 1fr, auto, 1fr), column-gutter: 6pt,
    node[Universo][125 nomes, incluir / quarentenar / restaurar],
    arrow,
    node[Fontes][BLP · BQuant · Hermes · fixture],
    arrow,
    node[Snapshots][versionados, append-only],
    arrow,
    node[Scoring][5 blocos, tiers A/B/C],
    arrow,
    node[Dashboard][screen, movers, relatórios],
  )
  #v(1.5em)
  #align(center)[#text(size: 14pt, fill: muted)[Toda classificação carrega uma justificativa em linguagem simples, replicável no terminal.]]
]

// ---------- 5 · Integrações de dados ----------
#slide[Quatro fontes de dados em jogo, um gate externo][
  #v(0.4em)
  #grid(columns: (auto, 1fr, auto), column-gutter: 12pt, row-gutter: 1.2em, align: horizon,
    dot(crit), [*Bloomberg Desktop API* #h(1fr) #text(size: 13pt, fill: muted)[CDS, ratings, equity]],
    text(size: 13pt, fill: crit, weight: "bold")[bonds em lote travados; account manager contatado, sem resposta],

    dot(warn), [*BQuant* #h(1fr) #text(size: 13pt, fill: muted)[screening de bonds no servidor]],
    text(size: 13pt, fill: luma(30), weight: "bold")[rodada de validação pendente],

    dot(good), [*API interna Hermes* #h(1fr) #text(size: 13pt, fill: muted)[fita EoD de bonds por data]],
    text(size: 13pt, fill: good, weight: "bold")[bonds no ar; CDS no servidor em conversa com o responsável],

    dot(muted), [*Markit Partners* #h(1fr) #text(size: 13pt, fill: muted)[dados adicionais de crédito]],
    text(size: 13pt, fill: luma(30), weight: "bold")[acesso solicitado],
  )
  #v(1.2em)
  #align(center)[#text(size: 13pt, fill: muted)[Qualquer rota que chegar primeiro alimenta exatamente o mesmo snapshot, scoring e dashboard.]]
]

// ---------- 6 · Metodologia + porquês ----------
#slide[Como o screen decide, e por quê][
  #text(size: 13pt, fill: muted)[Viabilidade: spread vs o benchmark Brasil]
  #v(0.3em)
  #grid(columns: (2fr, 1fr, 3fr), column-gutter: 2pt,
    box(fill: crit, height: 32pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 13pt, weight: "bold")[× não viável]]],
    box(fill: warn, height: 32pt, width: 100%)[#align(center + horizon)[#text(fill: luma(30), size: 13pt, weight: "bold")[edge case]]],
    box(fill: good, height: 32pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 13pt, weight: "bold")[✓ viável]]],
  )
  #grid(columns: (2fr, 1fr, 3fr),
    align(right)[#text(size: 11pt, fill: muted)[-20 bps ]],
    align(right)[#text(size: 11pt, fill: muted)[0 ]],
    [],
  )
  #text(size: 12pt, fill: muted)[Ancorado no Brasil porque essa é a alternativa do cliente; o edge case mantém nomes de rating mais forte até 20 bps abaixo (ex.: Hyundai, -18 bps, A-).]
  #v(0.9em)
  #text(size: 13pt, fill: muted)[Pesos do score composto]
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
    align(center)[#text(size: 10.5pt)[Crédito]],
    align(center)[#text(size: 10.5pt)[Liquidez]],
    align(center)[#text(size: 10.5pt)[Equity]],
    align(center)[#text(size: 10.5pt)[Reconhecimento]],
  )
  #v(0.4em)
  #text(size: 12pt, fill: muted)[Os pesos refletem as prioridades da mesa: carrego primeiro, depois segurança, negociabilidade, leitura de mercado e fit com o cliente. Os tiers viram ação: A pronto para pitch (≥ 70), B watchlist (≥ 50), C descarte.]
]

// ---------- 7 · O que validar ----------
#slide[O que quero validar com vocês][
  #v(0.4em)
  #grid(columns: (1fr, 1fr), rows: (108pt, 108pt), column-gutter: 14pt, row-gutter: 14pt,
    card[Critérios][tolerância de 20 bps · inclusão de Sr Non-Preferred · preferência de moeda],
    card[Arquivo do universo][ratings internos · ISINs para o Hermes · overrides de handles Bloomberg],
    card[Dashboard][falta alguma visualização ou métrica para o fluxo de vocês?],
    card[Cadência][check-ins semanais curtos em vez de uma única grande entrega?],
  )
  #v(1.0em)
  #align(center)[#text(size: 14pt, fill: muted)[Feedback sobre o framework e os critérios move mais do que feedback sobre nomes individuais.]]
]

// ---------- 8 · Insight 1 ----------
#slide[Insight: o universo não deveria ser uma lista estática][
  #text(size: 12pt, fill: muted)[Hoje: ingestão totalmente manual]
  #v(0.3em)
  #grid(columns: (1fr, auto, 1fr, 2.2fr), column-gutter: 6pt,
    node(height: 54pt)[Mesa inclui nome a mão][um formulário por nome],
    arrow,
    node(height: 54pt)[Universo estático][os mesmos 125 nomes até alguém editar],
    [],
  )
  #v(0.9em)
  #text(size: 12pt, fill: muted)[Proposta: sugerido pela máquina, aprovado pela mesa]
  #v(0.3em)
  #grid(columns: (1.2fr, auto, 1fr, auto, 1fr, auto, 1fr), column-gutter: 6pt,
    node(height: 60pt, dashed: true)[Feeds][fita de bonds do Hermes · membros de índices · novas emissões],
    arrow,
    node(height: 60pt, dashed: true)[Pré-screen automático][spread vs Brasil, liquidez],
    arrow,
    node(height: 60pt, dashed: true)[Inbox de candidatos][sugestões ranqueadas],
    arrow,
    node(height: 60pt)[Mesa aprova][a palavra final continua humana],
  )
  #v(1.0em)
  #align(center)[#text(size: 13pt, fill: muted)[O Hermes já retorna a fita completa de bonds por data: comparar com o universo acompanhado gera candidatos com spreads já calculados. Nem manual, nem força bruta.]]
]

// ---------- 9 · Insight 2 ----------
#slide[Insight: de screener a copiloto de crédito][
  #v(0.4em)
  #grid(columns: (1fr, 1fr, 1fr), rows: 128pt, column-gutter: 14pt,
    card[Análise de crédito embutida][one-pager automático por nome: balanço, alavancagem, covenants, notícias; o analista valida em vez de montar],
    card[De screen a monitor][snapshots agendados mais alertas de viradas de viabilidade e movimentos fora do padrão; a mesa é avisada, não precisa olhar],
    card[Loop de aprendizado][feedback da mesa sobre nomes e backtests sobre snapshots acumulados calibram os pesos com evidência],
  )
  #v(1.2em)
  #align(center)[#text(size: 14pt, fill: muted)[Uma mesma lente por trás dos três: engenharia que remove trabalho manual entre o sinal e a decisão.]]
]

// ---------- 10 · Daqui pra frente ----------
#slide[Daqui pra frente: ciclos mais curtos][
  #v(0.2em)
  #grid(columns: (1fr, 1fr), column-gutter: 14pt,
    box(stroke: 1.2pt + accent, radius: 8pt, inset: 12pt, width: 100%)[
      #text(size: 15pt, weight: "bold", fill: accent)[Semana 3] \
      #v(0.3em)
      #set text(size: 13.5pt)
      - Primeiro snapshot completo (Hermes ou BQuant)
      - Resultados: tiers, principais nomes, edge cases, movers
      - Rodada da mesa no arquivo do universo
    ],
    box(stroke: 1.2pt + accent, radius: 8pt, inset: 12pt, width: 100%)[
      #text(size: 15pt, weight: "bold", fill: accent)[Semana 4] \
      #v(0.3em)
      #set text(size: 13.5pt)
      - Listas categorizadas de candidatos
      - Relatório final
      - Apresentação à mesa e handover
    ],
  )
  #v(1.1em)
  #grid(columns: (auto, 1fr), column-gutter: 14pt, row-gutter: 10pt, align: horizon,
    text(size: 12pt, fill: muted)[até agora],
    box(stroke: 1pt + muted, height: 22pt, width: 100%)[#align(center + horizon)[#text(size: 11pt, fill: muted)[um ciclo de quatro semanas, uma única grande entrega]]],
    text(size: 12pt, fill: muted)[daqui pra frente],
    grid(columns: (1fr, 1fr, 1fr, 1fr), column-gutter: 8pt,
      box(fill: accent, height: 22pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 11pt)[check-in]]],
      box(fill: accent, height: 22pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 11pt)[check-in]]],
      box(fill: accent, height: 22pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 11pt)[check-in]]],
      box(fill: accent, height: 22pt, width: 100%)[#align(center + horizon)[#text(fill: white, size: 11pt)[check-in]]],
    ),
  )
  #v(0.7em)
  #align(center)[#text(size: 14pt, fill: muted)[A fundação está pronta; daqui em diante, alvos pequenos e correções rápidas.]]
]
