#set page(
  paper: "a4",
  margin: (x: 2.1cm, y: 2.3cm),
  numbering: "1",
  header: context {
    if counter(page).get().first() > 1 [
      #set text(size: 8pt, style: "italic", fill: luma(90))
      XP :: Issuer Opportunity Screener
      #h(1fr) Relatório Técnico: Features, Pesos e Qualidade de Dados
      #v(-0.6em)
      #line(length: 100%, stroke: 0.4pt + luma(180))
    ]
  },
)
#set text(font: "New Computer Modern", size: 10pt, lang: "pt")
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
  #text(size: 17pt, weight: "bold")[Relatório Técnico]
  #v(0.2em)
  #text(size: 12pt)[Features, Pesos e Qualidade de Dados]
  #v(0.5em)
  #text(size: 10pt)[João Pedro Ferreira Barbosa #h(1em) · #h(1em) 22 de julho de 2026]
]
#v(0.8em)
#line(length: 100%, stroke: 0.6pt)
#v(0.5em)

_Projeto de verão. Período coberto: 09/07/2026 a 22/07/2026. Este documento é o
registro técnico completo do que foi construído, como cada peça funciona e por
que cada escolha foi feita. Ele se aprofunda especialmente nas duas áreas
apontadas como decisivas: qualidade de dados e escolha de features (definição
exata de cada feature, quantas features existem e seus respectivos pesos)._

= O que é o sistema

O Issuer Opportunity Screener ranqueia emissores corporativos como candidatos à
emissão de notas estruturadas (COEs) voltadas ao investidor brasileiro. A
premissa comercial, alinhada com a mesa em 13/07/2026: o investidor brasileiro
tem pouco apetite por nomes que negociam muito abaixo do Brasil, então todo
spread é ancorado no benchmark soberano brasileiro e a régua favorece nomes
reconhecíveis com carrego real.

O sistema parte de um universo editável pela mesa com 125 emissores, busca dados
de mercado de crédito para cada um, grava um snapshot imutável, pontua cada nome
com um composto documentado e apresenta o resultado como uma tela ranqueada com
justificativa em linguagem natural para cada número.

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Camada*], [*Responsabilidade*],
  [`universe.py`], [Carrega e valida `data/universe.csv`, os inputs da própria mesa],
  [`sources/`], [Um adaptador por rota de dados: Bloomberg, BQuant, Hermes, fixture],
  [`pipeline.py`], [Orquestra uma coleta: universo, busca, gravação do snapshot],
  [`snapshots.py`], [Snapshots parquet append-only mais um manifesto],
  [`scoring.py`], [O composto, a regra de viabilidade e as flags],
  [`validation.py`], [Estabilidade, sensibilidade a pesos, concentração, co-movimento],
  [`insights.py`], [Movimentações entre snapshots e callouts por regra],
  [`reports.py`], [O artefato de evidência semanal em Markdown],
  [`app.py`], [Dashboard em Streamlit],
)

As dependências fluem estritamente em uma direção, da esquerda para a direita.
Nada abaixo de `sources/` toca a Bloomberg, então toda a camada de scoring e
validação é testável sem um Terminal. São 168 testes automatizados.

= Catálogo de features

Este é o núcleo da metodologia. São *15 features* (chamadas de sinais no código),
agrupadas em *5 blocos*. Cada feature mapeia uma observação bruta de mercado para
uma nota de 0 a 100. Uma feature sem dado retorna vazio, não zero, e isso
importa: zero é uma afirmação sobre o crédito, ausência é uma afirmação sobre o
dado.

Cada banda abaixo é uma escolha deliberada, e todas são constantes em
`scoring.py` que a mesa pode mover.

== Bloco 1: Atratividade de Crédito e Spread (peso 0,35, 5 features)

Este bloco carrega o maior peso porque o spread é a razão de o trade existir.
Ele faz a mesma pergunta de cinco formas: esse spread é atrativo em termos
absolutos, contra a própria história do nome e contra seus pares.

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Feature*], [*Definição e banda*],
  [`spread_level`],
  [$min(s / 6, 100)$, onde $s$ é o spread primário em bps. Atinge 100 em 600 bps
  e satura ali. *Por que 600:* acima de aproximadamente 600 bps o nome deixa de
  ser carrego e passa a ser distress para essa base de clientes. Um nome a 900
  bps não é três vezes mais atrativo que um a 300; em geral ele simplesmente não
  é vendável. A saturação codifica isso. Esta é a banda que mais merece ser
  desafiada pela mesa.],

  [`history_percentile`],
  [Percentual dos fechamentos semanais do último ano iguais ou abaixo do spread
  de hoje, vezes 100. Exige ao menos 12 pontos semanais e é suprimida por
  completo quando a história está estagnada (ver 5.3). *Por quê:* responde "esse
  nome está largo em relação a ele mesmo", que é a pergunta de valor relativo
  mais limpa disponível sem um modelo de curva.],

  [`vs_1y_ma`],
  [$"clamp"(50 dot s / mu)$, onde $mu$ é a média de 1 ano. Marca 50 quando o
  nome negocia na própria média e 100 no dobro dela. *Por que centrada em 50:*
  negociar na própria média não é nem barato nem caro, então deve ficar no meio
  da escala e não em um extremo.],

  [`vs_1y_p75`],
  [$"clamp"(100 dot s / p_75)$, onde $p_75$ é o percentil 75 de 1 ano. Atinge
  100 quando o nome negocia na ponta larga do próprio ano. *Por que o percentil
  75 e não o máximo:* o máximo de um ano de fechamentos semanais costuma ser um
  único print de estresse, então ancorar nele faria toda semana normal parecer
  barata.],

  [`vs_peer_median`],
  [$"clamp"(50 + 50 dot (s - m) / m)$, onde $m$ é a mediana do spread primário
  dos outros nomes da mesma cesta. Marca 50 na mediana dos pares e 100 no dobro
  dela. Exige ao menos 3 pares com spread; caso contrário retorna vazio. *Por
  que o mínimo:* uma "mediana" calculada a partir de um único outro papel não é
  uma mediana, e em cestas rarefeitas isso era efetivamente cara ou coroa entre
  dois nomes.],
)

== Bloco 2: Qualidade de Crédito e Risco (peso 0,20, 3 features)

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Feature*], [*Definição e banda*],
  [`external_rating`],
  [$100 - r dot 100 / 21$, onde $r$ é a posição do rating numa escala de 22
  níveis (AAA é 0, D é 21). Um notch vale 4,76 pontos. A posição é a mediana
  entre todos os provedores que resolveram (Moody's, S&P, Fitch, DBRS, KBRA,
  composto Bloomberg), mapeados para a escala S&P. *Por que linear:* um notch é
  um notch, e qualquer convexidade seria uma opinião injustificada sobre
  probabilidade de default que a régua não tem dado para sustentar.],

  [`internal_rating`],
  [Mesma fórmula aplicada ao rating interno da mesa em `universe.csv`. Existe
  para que o julgamento da mesa entre no score explicitamente, e não como um
  override aplicado depois.],

  [`rating_trend`],
  [Perspectiva ou watch positivo marca 75, estável 50, negativo 25, ausente
  vazio. *Por que modesto:* uma perspectiva é uma opinião prospectiva, não um
  fato, então ela inclina o bloco em vez de dominá-lo. Esta feature estava
  especificada na metodologia original e nunca havia sido implementada; o
  normalizador de rating estava justamente descartando os marcadores de watch
  de que ela precisa.],
)

== Bloco 3: Liquidez e Acessibilidade de Mercado (peso 0,20, 3 features)

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Feature*], [*Definição e banda*],
  [`cds_available`], [100 quando um CDS 5Y resolveu, 0 caso contrário.],
  [`cds_liquidity`], [Um proxy de disponibilidade de cotação, usado como está.
  Hoje vale 100 sempre que existe cotação, o que na prática o torna uma
  duplicata de `cds_available`. É a feature mais fraca do modelo e está nomeada
  como tal na seção 8.],
  [`bond_available`], [100 quando um bond sênior unsecured elegível foi selecionado, 0 caso contrário.],
)

Este bloco é honesto quanto a ser um proxy. Ele mede se os instrumentos são
cotáveis, não quão apertado está o bid-ask nem se há tamanho para negociar.

== Bloco 4: Overlay de Equity (peso 0,10, 3 features)

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Feature*], [*Definição e banda*],
  [`momentum_3m`], [$"clamp"(50 + Delta_(3m))$, onde $Delta$ é a variação
  percentual de preço. Estável marca 50; +50% satura em 100. Centrada no zero de
  variação.],
  [`momentum_12m`], [$"clamp"(50 + Delta_(12m) / 2)$. A divisão por dois reflete
  que um ano de variação de preço é cerca de duas vezes mais disperso que um
  trimestre, então a mesma banda saturaria constantemente.],
  [`recommendations`], [$"clamp"(50 + 50 dot b)$, onde $b = ("compras" -
  "vendas") / "total"$, limitado a $[-1, 1]$ e portanto mapeado exatamente em 0
  a 100 sem corte.],
)

O bloco inteiro é descartado para emissores sem ação listada, em vez de
pontuado como zero.

== Bloco 5: Reconhecimento e Aderência ao Cliente (peso 0,15, 1 feature)

`recognition` é a nota de reconhecimento definida pela mesa em `universe.csv`,
numa escala documentada de 0 a 100, usada como está. É o único input puramente
julgamental do modelo e carrega 15% do peso. Um proxy medido (media heat) foi
conscientemente adiado. A seção 8 propõe uma segunda rodada de pontuação
independente para torná-lo defensável.

= Das features ao ranking

A nota de cada bloco é a *média das features disponíveis*. O composto é a média
ponderada das notas dos blocos, *renormalizada sobre os blocos que de fato
produziram nota*:

$ S = (sum_(b in A) w_b dot C_b) / (sum_(b in A) w_b) $

onde $A$ é o conjunto de blocos com dado. Tiers: A a partir de 70, B a partir de
50, C abaixo disso.

*A renormalização tinha um efeito colateral sério, agora corrigido.* Derrubar um
bloco não penaliza o nome, apenas remove o que aquele bloco teria dito. Para um
nome a 900 bps sem rating, o bloco de Qualidade de Crédito desaparecia e o
composto saía em *77,1 (Tier A)*. O mesmo nome com rating CCC+ marcava *65,3
(Tier B)*. A régua estava promovendo sistematicamente justamente o perfil que
menos se quer entregar a um cliente: um spread muito largo que ninguém avalia.
Um nome sem rating não pode mais alcançar Tier A, e toda linha reporta seu
`coverage`, a fração do peso dos blocos que efetivamente pontuou.

= Os pesos são determinantes?

Os pesos 35/20/20/10/15 são julgamento da mesa. A pergunta honesta é se o
ranking é dirigido pela evidência ou por esse julgamento. O `validation.py`
responde repontuando todo o universo sob *12 cenários nomeados*: cada um dos
cinco pesos de bloco movido para cima e para baixo em 10%, mais uma inclinação
combinada pró-spread e outra pró-qualidade. Para cada cenário ele reporta a
correlação de ranking contra os pesos documentados e a fração do top 10 que
sobrevive.

No universo sintético atual (125 nomes, 104 pontuados):

#table(
  columns: (1fr, auto),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Medida*], [*Resultado*],
  [Cenários], [12],
  [Correlação média de ranking vs pesos documentados], [0,997],
  [Pior correlação de ranking], [0,993 (inclinação pró-qualidade)],
  [Pior sobreposição do top 10], [90% (Atratividade de Crédito e Spread \u{2212}10%)],
  [Nomes que se moveram no pior caso], [PEMEX entra, FEMSA sai],
)

Em linguagem direta: em todos os cenários testados, ao menos 9 dos 10 primeiros
nomes são os mesmos, e a correlação de ranking nunca cai abaixo de 0,99. Nesses
dados, os pesos são uma escolha de apresentação, não a resposta. Quem faz o
trabalho é a evidência.

*Duas ressalvas ditas de antemão.* Primeiro, isso é dado sintético; a rodada
precisa ser repetida no universo real antes de o número ser citado como
resultado. Segundo, e mais importante, *isso testa os pesos, não as bandas*. Os
pontos de saturação da seção 2 (600 bps, o percentil 75, o momentum de 12 meses
dividido por dois) não passaram por tratamento equivalente. Sensibilidade a
bandas é a próxima peça de validação de maior valor e está nomeada como tal na
seção 8.

= Qualidade de dados

== De onde vêm os dados

#table(
  columns: (auto, 1.1fr, 1fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Rota*], [*O que fornece*], [*Situação*],
  [Bloomberg Desktop API], [CDS, bonds, ratings, equity, histórico: tudo],
  [Bloqueada por revisão de entitlement],
  [BQuant], [Screen de bonds server-side sob entitlements diferentes], [Pronta, rodada de validação pendente],
  [Hermes (interna XP)], [Bond EoD por ISIN, proxy de G-spread ancorado no Brasil], [Pronta, apenas bonds],
  [Markit], [Dados adicionais de crédito], [Acesso solicitado],
  [Fixture], [Universo sintético determinístico], [Usada em testes e demos],
)

O bloqueio da Bloomberg (`responseError` LIMIT / `WORKFLOW_REVIEW_NEEDED`) é uma
decisão de entitlement, não uma falha de código. A superfície de requisição foi
minimizada em resposta: campos estáticos para todos os candidatos a bond, campos
de pricing apenas para o único bond selecionado por emissor.

== Cobertura é medida, não presumida

Todo manifesto de snapshot registra cobertura por campo. Na rodada sintética
atual: CDS 66%, z-spread de bond 83%, ratings 83%, equity 66%. Todo nome que
falha em pontuar é listado com o motivo, e todo nome parcialmente coberto carrega
`quality_notes` explicando o que falta.

== Defeitos encontrados em rodadas reais, e o que cada um ensinou

Os itens abaixo foram encontrados rodando contra dados reais da Bloomberg e são a
razão de várias features terem a forma que têm.

#table(
  columns: (1fr, 1.35fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Defeito*], [*Correção e lição*],
  [Histórico de preço de bond poluindo o histórico de spread (o caso Xerox +1668 bps)],
  [O `PX_LAST` de um bond é preço, não spread. O histórico agora usa `Z_SPRD_MID`
  para bonds e `PX_LAST` apenas para CDS. Lição: um nome de campo que funciona
  para um instrumento pode estar silenciosamente errado para outro.],

  [A busca de instrumentos trazia a curva de CDS para dentro da elegibilidade de bonds],
  [Os papéis são separados antes da elegibilidade, então um contrato de CDS nunca
  pode ser selecionado como bond.],

  [Ratings só eram requisitados em ações],
  [Ratings agora são consolidados de forma agnóstica a provedor entre bond,
  depois CDS, depois ação, cobrindo seis provedores.],

  [O caso de borda da viabilidade nunca disparava sem ratings],
  [Passa a usar o rating interno da mesa como fallback.],

  [Seleções de bond em distress ou desatualizadas (o perfil DISH)],
  [Z-spread acima de 1000 bps ou preço abaixo de 50 é sinalizado para revisão em
  vez de ranqueado silenciosamente.],

  [Históricos de cotação parados lidos como créditos estáveis],
  [Um histórico com menos de 6 fechamentos semanais distintos passa a ser tratado
  como cotação não atualizada. As features de percentil, média móvel e percentil
  75 são suprimidas sobre ele. Antes disso, um nome que ninguém cotava havia
  meses seria anunciado com confiança como negociando no percentil 100 da própria
  faixa.],

  [Ratings divergentes colapsavam silenciosamente],
  [Uma discordância de 4 notches entre provedores era mediada para um rating que
  ninguém publicou. Agora é sinalizada, e o portão de viabilidade lê o provedor
  mais conservador.],

  [O escritor do universo apagava ISINs],
  [`UNIVERSE_FIELDS` omitia `isin`, então adicionar um nome pelo formulário do
  dashboard apagava silenciosamente todos os ISINs do arquivo, o que teria
  quebrado a rota Hermes. Corrigido e coberto por teste.],
)

== O sistema de flags

Onze flags anotam um ranking sem alterá-lo. Elas existem porque um número pode
estar aritmeticamente correto e ainda assim significar outra coisa.

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Flag*], [*Significado*],
  [`unrated`], [Sem rating de qualquer provedor ou da mesa: o composto não tem bloco de qualidade de crédito],
  [`split_rating`], [Provedores discordam em 3 notches ou mais; a viabilidade lê o mais fraco],
  [`stale_history`], [Menos de 6 fechamentos semanais distintos: cotação parada, não crédito estável],
  [`thin_peers`], [Menos de 3 pares na cesta com spread, logo sem comparação de mediana],
  [`subordinated`], [Bond abaixo de sênior preferencial: parte do spread é estrutural, não crédito],
  [`long_tenor`], [Bond além de 7 anos contra um padrão de CDS 5Y: parte do ganho é curva],
  [`sovereign_correlated`], [Domiciliado no Brasil ou ligado ao Estado: viável versus Brasil não é diversificação do Brasil],
  [`cheap_for_a_reason`], [Em 450 bps ou mais com perspectiva negativa: largo porque o crédito está deteriorando],
  [`benchmark_mismatch`], [Z-spread de bond medido contra o CDS do Brasil por falta de spread de bond soberano],
  [`benchmark_sensitive`], [O veredito de viabilidade inverte conforme a perna do Brasil usada],
  [`small_issue`], [Abaixo de USD 500mm em circulação: pequeno demais para sustentar um programa de notas],
)

= A regra de viabilidade

Um nome é viável quando seu spread está igual ou acima do Brasil, ou até 20 bps
abaixo do Brasil com rating estritamente mais forte. Três refinamentos tornam a
comparação honesta.

*Conservador em divergências.* O portão lê o rating mais fraco atribuído por
qualquer provedor, não a mediana. A mediana pode inventar um rating que ninguém
publicou: S&P A e Moody's B1 produzem mediana BBB-, que passa no portão contra o
BB do Brasil, enquanto a leitura conservadora B+ não passa. Um portão de risco
deve ler pelo lado conservador.

*Benchmark comparável.* Um emissor precificado pelo CDS 5Y é comparado ao CDS 5Y
do Brasil; um emissor precificado por z-spread de bond é comparado ao z-spread do
bond de referência do Brasil. Antes, todo emissor era comparado ao CDS soberano
independentemente disso, então um nome precificado por bond era medido em bases
diferentes. Nomes cujo veredito inverte entre as duas pernas são sinalizados.

*Desempate de mediana par.* Com um número par de provedores a mediana cai entre
dois notches. O arredondamento bancário do Python fazia a direção do desempate
depender da posição na escala: A-/BBB+ resolvia para A- (o lado mais forte),
enquanto BBB+/BBB resolvia para BBB (o mais fraco). Agora resolve sempre para o
lado mais fraco. Uma decisão de metodologia estava sendo tomada por um modo de
arredondamento.

= Validação, reprodutibilidade e movimentações

*Estabilidade de ranking.* Correlação de Spearman dos compostos entre dois
snapshots, mais mudanças de tier, inversões de viabilidade e o movimento médio do
composto. Uma régua que se embaralha semana a semana está medindo ruído.

*Concentração.* HHI e participação do maior balde na shortlist por cesta, país e
setor, com alertas acima de HHI 0,30 ou 50% em um único balde. A régua ranqueia
nomes um a um, mas o produto é uma cesta: dez nomes Tier A em um só país são a
mesma aposta dez vezes. Top 10 atual: HHI de cesta 0,20, HHI de país 0,24 (maior
é Brasil com 30%), HHI de setor 0,18.

*Co-movimento.* Correlação média par a par das variações semanais de spread na
shortlist, hoje 0,31 sobre 36 pares. Sobre variações e não níveis, que
correlacionariam apenas por tendência.

*Movimentações.* Inversões de viabilidade são atribuídas entre o emissor e o
soberano. O próprio CDS do Brasil rotineiramente se move mais que a tolerância de
20 bps em uma semana, então um nome pode inverter sem que nada tenha acontecido
ao crédito. O callout diz qual dos dois se moveu.

*Reprodutibilidade.* Cada manifesto de snapshot registra o SHA-256 e a contagem
de linhas do arquivo de universo que o produziu. O universo é mutável e a
quarentena remove nomes, então sem isso um snapshot não pode ser reconstruído e
qualquer backtest sobre o histórico teria viés de sobrevivência.

*Economia do cliente.* `hedged_pickup_bps` subtrai um custo de hedge cambial
definido pela mesa do ganho sobre o Brasil, para que o ranking possa ser lido na
economia de uma nota com hedge em BRL. O custo é um input, não uma observação de
mercado: a régua não tem feed de basis cambial, e fingir o contrário seria o tipo
errado de precisão.

= Limitações conhecidas e decisões em aberto

Estas são declaradas abertamente porque são a fronteira honesta do que o sistema
atual sustenta.

+ *Sensibilidade a bandas não foi testada.* A seção 4 valida os pesos. As bandas
  de saturação da seção 2 não passaram por tratamento equivalente. É o próximo
  trabalho de maior valor.
+ *`cds_liquidity` é quase vazia.* Na prática duplica `cds_available`. Uma medida
  real de liquidez precisa de bid-ask ou dados de negociação.
+ *Reconhecimento é julgamento não auditado* carregando 15% do peso. Dois
  integrantes da mesa pontuando de forma independente e reportando a discordância
  custaria uma hora e o tornaria defensável.
+ *Um bond por emissor.* Formato de curva e características específicas da
  emissão (callables, sinking funds) estão fora de escopo, e z-spreads de
  callables não são comparáveis aos de bullets.
+ *Sem feed de câmbio ou basis cambial.* O custo de hedge é um input da mesa.
+ *`state_linked` precisa de uma passada da mesa* para as estatais da América
  Latina. Nomes domiciliados no Brasil são detectados automaticamente por `country`.
+ *O entitlement da Bloomberg segue como bloqueio principal* para cobertura completa.

= Engenharia

168 testes automatizados, todos passando. Uma fonte fixture determinística roda o
sistema inteiro sem Terminal, e ela gera deliberadamente os casos incômodos: CDS
ausente, ação não listada, histórico parcial, falha de busca, bonds subordinados
e longos, e um rating divergente com watch negativo.

Antes da próxima rodada real, o adaptador Bloomberg foi endurecido:

- Os três laços de requisição eram `while True` sem limite sobre `nextEvent`,
  então uma requisição que nunca recebesse RESPONSE giraria para sempre. Uma
  rodada de 125 nomes teria travado em silêncio, sem como saber qual requisição
  morreu. Agora desistem após quatro esperas silenciosas de 30 segundos.
- Uma sessão derrubada é reconectada, em até três tentativas, em vez de fazer
  todos os emissores restantes falharem com o mesmo erro e desperdiçar a rodada.
- Toda leitura de campo numérico é coagida, então um campo que retorne texto ou
  array custa um valor e não o emissor inteiro.
- Uma resposta de histórico com `securityError` não levanta mais exceção.
- `IOS_MAX_ISSUERS=3` roda um preflight nos primeiros nomes antes de assumir o
  universo completo. Recomendado antes de toda rodada longa.

= Apêndice A: constantes

#table(
  columns: (auto, auto, 1fr),
  stroke: 0.5pt + luma(200),
  inset: 6pt,
  [*Constante*], [*Valor*], [*Significado*],
  [Pesos dos blocos], [35/20/20/10/15], [Spread, qualidade, liquidez, equity, reconhecimento],
  [Cortes de tier], [70 / 50], [Limiares A / B no composto],
  [`VIABILITY_TOLERANCE_BPS`], [20], [Quanto abaixo do Brasil um nome mais forte pode negociar],
  [`SPLIT_RATING_NOTCHES`], [3], [Discordância entre provedores que conta como divergência],
  [`MIN_HISTORY_POINTS`], [12], [Pontos semanais necessários para um percentil],
  [`MIN_HISTORY_UNIQUE`], [6], [Fechamentos distintos abaixo dos quais a cotação é lida como parada],
  [`MIN_PEERS`], [3], [Pares na cesta necessários para uma mediana],
  [`LONG_TENOR_YEARS`], [7], [Prazo do bond além do qual é curva, não crédito],
  [`WIDE_SPREAD_BPS`], [450], [Largo o bastante para que perspectiva negativa seja alerta],
  [`MIN_ISSUE_SIZE_USD`], [500mm], [Tamanho de emissão necessário para um programa de notas],
  [`MOVE_THRESHOLD_BPS`], [15], [Movimento que conta como fechamento ou abertura],
  [`OWN_HISTORY_HIGH_PCT`], [90], [Percentil que dispara o callout de faixa própria],
)

= Apêndice B: variáveis de ambiente

`IOS_SOURCE` seleciona a rota de dados (`bloomberg`, `bquant`, `hermes`,
`fixture`). `IOS_MAX_ISSUERS` limita uma rodada de preflight. `IOS_LOG_LEVEL=trace`
imprime cada candidato e decisão de campo. `IOS_BOND_CURRENCIES` e
`IOS_TENOR_MIN_YEARS` / `IOS_TENOR_MAX_YEARS` definem a elegibilidade de bonds.
`IOS_HEDGE_COST_BPS` define o custo de hedge cambial. `IOS_HERMES_*` configuram a
rota da API interna. `IOS_AUTO_QUARANTINE` move nomes não pontuados para fora do
universo e está deliberadamente desligada enquanto o acesso a dados não é
liberado.
