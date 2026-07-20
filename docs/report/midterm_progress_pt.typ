#set page(margin: (x: 2.2cm, y: 2.2cm))
#set text(font: "Libertinus Serif", size: 10.5pt, lang: "pt")
#set par(justify: true)
#show heading.where(level: 1): set text(size: 15pt)
#show heading.where(level: 2): it => block(above: 1.4em, below: 0.8em)[
  #set text(size: 12pt)
  #it.body
  #v(-0.6em)
  #line(length: 100%, stroke: 0.5pt + luma(160))
]

= Issuer Opportunity Screener: Relatório Intermediário de Progresso

_Projeto de verão, COE Credit Trading. Período coberto: 09/07/2026 a 20/07/2026 (fim da semana 2 de 4)._

== Objetivo e visão geral do status

O projeto constrói um framework inicial de screening para identificar nomes corporativos que possam ser candidatos atrativos para emissão de notas (COEs) para investidores brasileiros, com base em spreads de mercado, informações de crédito e sinais complementares de equity. A premissa comercial, alinhada com a mesa em 13/07/2026: o investidor brasileiro tem pouco apetite por nomes negociando muito abaixo do Brasil, então todo spread é ancorado no benchmark Brasil e o screen favorece nomes reconhecíveis com carrego real.

#table(
  columns: (1fr, auto),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Frente de trabalho*], [*Status*],
  [Definição e governança do universo], [Concluída (125 nomes, editável pela mesa)],
  [Pipeline de dados e snapshots], [Concluído, validado com dados sintéticos e live parcial],
  [Metodologia de screening e scoring], [Concluída e documentada],
  [Dashboard], [Concluído],
  [Rodada completa com dados live], [Bloqueada por entitlement Bloomberg (chamado aberto)],
  [Relatório final e apresentação à mesa], [Esqueleto redigido, resultados aguardando dados],
)

O framework está totalmente operacional de ponta a ponta. O único bloqueio aberto é externo: uma revisão de entitlement da Bloomberg que trava requisições de dados de bonds em lote pela Desktop API. Dois caminhos de mitigação já estão construídos (detalhados em Limitações).

== O que já foi entregue

*Dataset consolidado e pipeline.* Snapshots versionados e append-only (parquet mais manifest) com uma linha por emissor cobrindo: CDS 5Y (CDS primeiro, fallback para z-spread de bond), um bond representativo sênior unsecured em USD (3 a 10 anos, z-spread, preço, vencimento, cupom), ratings independentes de provedor (Moody's, S&P, Fitch, DBRS, KBRA, composite Bloomberg), overlay de equity (momentum 3m/12m, saldo de recomendações de analistas), campos qualitativos da mesa (baskets, reconhecimento, ratings internos) e um ano de histórico semanal de spread por nome.

*Metodologia de screening, documentada.* Score composto de cinco blocos com pesos 35/20/20/10/15 (atratividade de spread, qualidade de crédito, liquidez, overlay de equity, reconhecimento), tiers A/B/C e a regra de viabilidade da mesa: spread igual ou acima do Brasil, ou até 20 bps abaixo com rating estritamente mais forte. A regra já trata os edge cases interessantes: um nome negociando 18 bps abaixo do Brasil com rating A-, por exemplo, é corretamente mantido como alternativa de maior qualidade. Toda classificação carrega uma justificativa em linguagem simples, e todo sinal é replicável no terminal: o dashboard mostra a aritmética exata e os títulos e campos usados.

*Benchmark Brasil.* CDS soberano live com fallback de lookup, descoberta do bond benchmark em USD e ratings soberanos independentes de provedor.

*Dashboard.* Aplicação Streamlit com screen ranqueado, mapa de mercado, comparação por basket, log de edge cases, detalhe por nome com decomposição completa do score e histórico de spread vs Brasil, movers entre snapshots com callouts baseados em regras (aperto, abertura, viradas de viabilidade, mudanças de tier), visão de qualidade de dados e exportação do relatório de snapshot em um clique. Temas claro e escuro.

*Ciclo de vida do universo.* CSV do universo editável pela mesa com overrides de handles Bloomberg por nome, formulário de inclusão de nomes no dashboard e mecanismo de quarentena que remove nomes sem score com motivos documentados, mantendo-os restauráveis.

*Qualidade de engenharia.* Arquitetura em camadas unidirecional (universo, fontes, pipeline, snapshots, scoring, app), mais de 100 testes automatizados e uma fonte fixture determinística que permite rodar e demonstrar o sistema inteiro em qualquer máquina, sem Terminal.

== Limitações e bloqueios

- *Entitlement Bloomberg (bloqueio principal, externo).* Requisições em lote de referência e preço de bonds pela Desktop API estão travadas pela Bloomberg (responseError LIMIT / WORKFLOW_REVIEW_NEEDED). Há chamado aberto com o representante Bloomberg. Mitigações já implementadas: a superfície de requisições foi minimizada (campos estáticos para candidatos, preço apenas para o único bond selecionado por emissor) e foi construída uma rota alternativa via export BQuant, que roda o screening de bonds no servidor sob entitlements diferentes e alimenta exatamente o mesmo pipeline. A rota BQuant ainda precisa de uma rodada de validação na máquina com Terminal.
- *Mapeamento de handles.* Os tickers do universo são tickers de família de crédito em melhor esforço; listagens fora dos EUA e convenções de CDS precisam de overrides confirmados pela mesa. A cobertura melhora conforme esses campos são preenchidos.
- *Um bond por emissor.* Formato de curva e características específicas de emissão (callables, sinking funds, descontos profundos) estão fora de escopo. Seleções suspeitas (z-spread acima de 1000 bps ou preço abaixo de 50, outliers tipo DISH) são sinalizadas para revisão separada, não ranqueadas silenciosamente.
- *Comparabilidade.* Os spreads são comparados dentro de um escopo fixo sênior unsecured USD de 3 a 10 anos; ajustes mais finos de maturidade, setor e liquidez são um refinamento candidato, ainda não implementado. Bonds fora de USD são marcados como apenas indicativos.
- *Score de reconhecimento é subjetivo.* Definido pela mesa, em escala documentada de 0 a 100; um proxy medido (calor de mídia) foi conscientemente adiado.
- *Lacunas de rating.* Quando nenhum provedor externo resolve, a viabilidade usa o rating interno da mesa como fallback e rotula o resultado como provisório.

== O que falta (semanas 3 e 4)

+ Destravar os dados completos: validar a rota de export BQuant no Terminal e/ou encerrar a revisão de workflow da Bloomberg; depois rodar o universo completo de 125 nomes e gravar o primeiro snapshot completo.
+ Rodada de resultados: gerar o relatório de snapshot, revisar outliers e preencher a seção de resultados do relatório final (cobertura, distribuição de tiers, principais nomes com justificativa, edge cases, narrativa de movers).
+ Rodada da mesa no arquivo do universo: ratings internos, overrides de handles para nomes fora dos EUA, confirmação da inclusão de Sr Non-Preferred e da preferência de moeda.
+ Categorização dos resultados para apresentação: spread alto / risco alto, candidatos equilibrados e edge cases de alta qualidade, em vez de uma lista única ranqueada.
+ Consolidação do relatório final, organização do código para handover e apresentação à mesa.

Em relação ao roadmap de quatro semanas, o projeto está no prazo: as metas das semanas 1 e 2 (ambiente, universo, dataset, limpeza, lógica básica de screening) estão completas, e material da semana 3 (documentação da metodologia, dashboard) foi entregue adiantado. O principal risco de cronograma é o timing externo do entitlement, que a rota BQuant existe para absorver.
