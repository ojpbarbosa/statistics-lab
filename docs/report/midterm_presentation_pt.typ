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
#set text(font: ("Helvetica Neue", "Libertinus Serif"), size: 19pt, lang: "pt")
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

// Slide de título
#align(horizon)[
  #text(size: 38pt, weight: "bold", fill: accent)[Issuer Opportunity Screener]
  #v(0.1em)
  #text(size: 24pt)[Progresso Intermediário]
  #v(1.2em)
  #text(size: 15pt, fill: muted)[
    Projeto de verão, COE Credit Trading \
    20/07/2026 (fim da semana 2 de 4)
  ]
]
#pagebreak()

#slide[BLUF: a conclusão primeiro][
  #v(0.4em)
  #block(fill: accent.lighten(92%), inset: 14pt, radius: 6pt, width: 100%)[
    *O framework de screening está construído e totalmente operacional de ponta a ponta, e o projeto está no prazo.*
  ]
  #v(0.6em)
  - O único bloqueio aberto é *externo*: uma revisão de entitlement da Bloomberg que trava dados de bonds em lote. Duas mitigações já estão construídas e uma aguarda rodada de validação.
  - Semanas 3 e 4: rodar o universo completo de 125 nomes, preencher os resultados e entregar o relatório final e a apresentação à mesa.
]

#slide[O que já foi entregue][
  - *Universo*: 125 nomes curados, editável pela mesa, com governança e ciclo de vida completo (inclusão, quarentena com motivos, restauração).
  - *Pipeline de dados*: snapshots versionados e append-only; CDS 5Y primeiro com fallback para z-spread de bond, um bond representativo sênior unsecured em USD, ratings independentes de provedor, overlay de equity, histórico semanal de 1 ano.
  - *Metodologia*: score composto documentado e a regra de viabilidade da mesa vs Brasil, incluindo o edge case de 20 bps.
  - *Dashboard*: screen ranqueado, mapa de mercado, movers entre snapshots, log de edge cases, qualidade de dados, exportação de relatório em um clique.
  - *Qualidade*: mais de 100 testes automatizados; uma fonte fixture permite rodar e demonstrar tudo em qualquer máquina, sem Terminal.
]

#slide[Como o screen decide][
  #v(0.3em)
  *Viabilidade vs o benchmark Brasil*
  #table(
    columns: (1fr, auto),
    stroke: 0.5pt + luma(200),
    inset: 9pt,
    [Spread igual ou acima do Brasil], [Viável],
    [Até 20 bps abaixo do Brasil, rating estritamente mais forte], [Viável (edge case)],
    [Caso contrário], [Não viável],
  )
  #v(0.5em)
  *Score composto*: atratividade de spread 35, qualidade de crédito 20, liquidez 20, overlay de equity 10, reconhecimento 15. Tiers A / B / C.
  Toda classificação carrega uma justificativa em linguagem simples e é replicável no terminal.
]

#slide[Bloqueio e limitações][
  - *Entitlement Bloomberg (externo)*: requisições de bonds em lote travadas pela revisão de workflow da Desktop API; chamado aberto com o representante.
  - *Mitigações construídas*: superfície de requisições minimizada (preço apenas para o bond selecionado por emissor) e rota de export BQuant no servidor alimentando o mesmo pipeline (validação pendente).
  - *Limites conhecidos*: um bond por emissor; spreads extremos sinalizados como outliers para revisão separada, não ranqueados silenciosamente; bonds fora de USD apenas indicativos; score de reconhecimento definido pela mesa; fallback de rating interno rotulado como provisório.
]

#slide[Próximos passos (semanas 3 e 4)][
  + Destravar os dados completos: validar a rota BQuant e/ou encerrar a revisão de workflow, depois gravar o primeiro snapshot completo.
  + Rodada de resultados: cobertura, distribuição de tiers, principais nomes com justificativa, edge cases, narrativa de movers.
  + Rodada da mesa no universo: ratings internos, overrides de handles, confirmações de Sr Non-Preferred e moeda.
  + Resultados categorizados para apresentação: spread alto / risco alto, candidatos equilibrados, edge cases de alta qualidade.
  + Relatório final, handover do código, apresentação à mesa.
]
