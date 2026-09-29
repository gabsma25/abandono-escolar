# Metodologia: variáveis, fontes, fórmulas e métodos

Projeto: predição preventiva do abandono escolar em Roraima (PIBIC/UERR + artigo
de mineração de dados). Versão 0.1 — 2026-09-20. Escrito a partir de:

- `docs/README.md` e `docs/Proposta_Detalhada_Analise_Preditiva_Abandono_Escolar_Roraima.pdf`
  (orientador, 17/09/2026);
- `dados/Processados/base_longitudinal_abandono_rr_2019_2025.csv` + dicionário +
  `validacao_base_longitudinal.json` (orientador);
- as planilhas originais do INEP em `dados/interim/brutos_inep_extraido/` e o
  catálogo dos microdados do Censo em `docs/catalogo_variaveis.csv`;
- tabelas geradas por `python -m src.analise_base_longitudinal`
  (`docs/desfechos_*.csv`, `docs/ausencia_base_longitudinal.csv`).

Todo número deste documento veio de um desses arquivos ou daquele módulo
(CLAUDE.md, regra 9). Onde eu proponho algo que o orientador não decidiu, está
marcado **[PROPOSTA]**; onde a decisão é sua ou dele, **[DECIDIR]**.

---

## 0. Resumo das decisões

| # | Assunto | Situação | Onde está explicado |
|---|---------|----------|---------------------|
| D1 | Unidade de análise: escola-ano; chave `ANO + CO_ENTIDADE` | **Adotada** (orientador) | §1, §3 |
| D2 | Dois painéis separados: Anos Finais do EF (AF) e Ensino Médio (EM) | **Adotada** (orientador) | §3.2 |
| D3 | Universo: escolas **públicas** com taxa de rendimento na etapa; privadas fora do modelo | **Adotada** (orientador); **[PROPOSTA]** tirar do universo as escolas só de educação infantil (P017) | §3.1 |
| D4 | Desfecho principal: taxa de abandono da etapa em t+1 (regressão); desfechos binários auxiliares | **Adotada** (orientador); definição do limiar de "alto risco" **[DECIDIR]** | §5 |
| D5 | TDI deixa de ser desfecho e vira preditor | **Adotada** (orientador; substitui o desenho anterior do CLAUDE.md) | §5.3 |
| D6 | Pandemia (2020–2021): manter e testar sensibilidade S1–S4 | **Adotada** (orientador) | §7.6 |
| D7 | Partição temporal: treino 2019–22→2020–23, validação 2023→24, teste 2024→25 bloqueado | **Adotada** (orientador) | §7.1 |
| D8 | Trazer do Censo já na fase 1: `IN_EDUCACAO_INDIGENA`, `TP_LOCALIZACAO_DIFERENCIADA` (estrato) e `QT_MAT_FUND_AF`, `QT_MAT_MED` (porte/peso) | **[PROPOSTA]** — precisa do seu OK e do orientador | §4.7, §6.5 |
| D9 | Usar `ATU_FUN_TOTAL` em vez de `ATU_FUN_AF` e criar `IN_MULTISSERIADA` (P016) | **[PROPOSTA]** | §4.4 |
| D10 | Baselines obrigatórios B0–B4 antes de qualquer modelo | **Adotada** (orientador) | §7.2 |
| D11 | Extensão da série para 2007–2018 quando os arquivos forem baixados | **[DECIDIR]** com o orientador (muda o desenho de validação) | §10 |

---

## 1. Glossário

Termos na ordem em que aparecem no raciocínio, não alfabética.

**Escola-ano.** A linha da tabela. Uma escola observada em um ano. A escola
`14000016` em 2019 e a mesma escola em 2020 são duas linhas. A chave é o par
(`ANO`, `CO_ENTIDADE`) e ela é única: 6.054 linhas, 6.054 chaves
(`validacao_base_longitudinal.json`).

**Painel (dados longitudinais).** Tabela em que as mesmas unidades (escolas) são
observadas repetidamente no tempo. Painel *desbalanceado*: nem toda escola
aparece em todos os anos (abre, fecha, deixa de ofertar a etapa).

**`CO_ENTIDADE`.** Código INEP da escola, 8 dígitos, estável ao longo dos anos
(nenhuma escola muda de município ou de dependência na série; 105 mudam de nome
— renomeações). É tratado como **texto**, nunca como número (CLAUDE.md, regra 6):
não se soma código de escola, e um zero à esquerda perdido quebraria a chave.

**Ano t / ano t+1.** `t` é o ano dos preditores (a linha); `t+1` é o ano do
desfecho. A linha de 2023 tem preditores de 2023 e desfecho de 2024. Isso é o
*horizonte de previsão* de um ano.

**Defasagem (lag).** Valor de uma variável em ano anterior, trazido para a linha
atual. `ABANDONO_MED_LAG1` na linha de 2023 é o abandono de 2022.

**Vazamento temporal (leakage).** Qualquer informação que só existiria depois do
momento em que a previsão seria feita e que entra como preditor. Ex.: usar
`ABANDONO_MED_T1` (o próprio alvo) ou uma média que inclua 2025 para prever
2025. Toda transformação (padronização, imputação, percentis) é ajustada **só no
treino** e aplicada ao resto.

**Ausente estrutural ("não se aplica") × ausente por falta de resposta.** Uma
escola sem Ensino Médio tem `ABANDONO_MED` vazio por definição; isso não é dado
faltante e **não pode virar 0**. Nas planilhas do INEP o vazio é a string `'--'`.
Ver §6.4.

**Taxas de rendimento.** Ao final do ano letivo, cada matrícula do Ensino
Fundamental e Médio recebe uma *situação*: aprovado, reprovado, abandono (ou
transferido/falecido, que saem da conta). O INEP publica, por escola e etapa:

$$\text{Aprovação} = \frac{A}{A+R+B}\times 100,\qquad
\text{Reprovação} = \frac{R}{A+R+B}\times 100,\qquad
\text{Abandono} = \frac{B}{A+R+B}\times 100$$

com $A$ = aprovados, $R$ = reprovados, $B$ = abandonos. As três somam 100
(verificado pelo orientador em 100% das combinações completas, tolerância 0,2
p.p.). O denominador $A+R+B$ (a "matrícula final") **não é publicado** na
planilha por escola — ver P018.

**Abandono ≠ evasão.** *Abandono* (INEP): o aluno deixou de frequentar antes do
fim do ano letivo, sem transferência formal; é uma situação **dentro do ano**,
existe por escola. *Evasão* (INEP, indicadores de fluxo): o aluno estava
matriculado em t e não aparece em t+1 em nenhuma escola; é **entre anos**, exige
seguir o aluno e só é publicado agregado até UF. Este projeto mede abandono. A
palavra evasão não entra em código, variável ou texto que se refira ao desfecho.

**Taxa de distorção idade-série (TDI).** Percentual de alunos de uma série com
idade **dois anos ou mais** acima da idade recomendada para aquela série
(6 anos no 1º ano do EF, 15 no 1º ano do EM, etc.):

$$\text{TDI}_{s} = \frac{\#\{\text{alunos da série } s \text{ com idade} \ge \text{idade recomendada}_s + 2\}}{\#\{\text{alunos da série } s\}}\times 100$$

É uma medida de trajetória acumulada: reprovações e abandonos passados deixam o
aluno atrasado. O detalhe da data de referência da idade está na nota técnica do
INEP (a planilha não a reproduz).

**Média de alunos por turma (ATU).** Matrículas da etapa divididas pelo número
de turmas da etapa na escola. Turmas *multietapa*, *multisseriadas* e de
*correção de fluxo* (uma turma com alunos de várias séries — comum na zona rural
e indígena) não entram no cálculo por série: o INEP as computa numa coluna
própria (`MULT_ETA_CAT_0`, nota 2 da planilha). Consequência em Roraima: §4.4.

**Indicador de esforço docente (IED).** O INEP classifica cada docente em um
nível de 1 a 6 conforme o esforço para exercer a profissão, combinando quatro
características: número de escolas em que atua, número de turnos, número de
alunos atendidos e número de etapas em que leciona (nota 1 da planilha; nota
técnica INEP 2014, link no rodapé da planilha). Níveis altos = mais esforço. A
planilha traz, por escola e etapa, o **percentual de docentes em cada nível**;
os seis percentuais somam 100. As faixas de cada nível estão na nota técnica e
devem ser transcritas dela antes de ir para o artigo (não as reproduzo aqui para
não citar de memória).

**Baseline (modelo de referência).** Previsão trivial que qualquer modelo
precisa superar para ter valor: prever a média, ou repetir o valor do ano
anterior (*persistência*). Sem baseline, um R² ou AUC não diz nada.

**Validação temporal.** Separar treino e teste **pelo tempo**, nunca ao acaso:
treinar no passado, testar no futuro. Validação aleatória (k-fold) em painel
deixa o modelo ver o futuro da mesma escola e superestima o desempenho.

**Walk-forward (origem móvel).** Repetir a validação temporal em janelas
crescentes: treina até 2020 → testa 2021; treina até 2021 → testa 2022; …
Mede se o desempenho é estável ou dependeu de um ano.

**Calibração.** Um modelo é calibrado se, entre as escolas às quais ele atribui
30% de risco, cerca de 30% de fato têm o evento. Medida por curva de calibração
e Brier score (§7.7).

**Top-K.** Cenário operacional: a gestão consegue acompanhar K escolas. Mede-se
quantas das K escolas com maior abandono observado em t+1 estavam entre as K
com maior previsão.

**Estrato.** Subgrupo em que o desempenho é avaliado separadamente para checar
equidade (urbana/rural, dependência, indígena/não indígena). Estratificação
serve à **avaliação**, não à seleção do modelo.

---

## 2. Fontes de dados

### 2.1 Indicadores educacionais do INEP (fase 1 — a base do orientador)

Publicados pelo INEP a partir do Censo Escolar, uma planilha por indicador ×
nível × ano. Neste projeto: `dados/bruto/brutos-inep/*.zip` → extraídos por
`python -m src.extrair_brutos_inep` para `dados/interim/brutos_inep_extraido/{tipo}/{ano}/`
com conferência de md5. Só o nível **escola** é usado na base.

| Tipo | Arquivo (exemplo) | Anos com nível escola | O que traz | Linhas RR (2024) |
|------|-------------------|-----------------------|------------|------------------|
| `tx_rend` | `tx_rend_escolas_2024.xlsx` | 2019–2025 | aprovação, reprovação, **abandono** por etapa/série | 696 |
| `TDI` | `TDI_ESCOLAS_2024.xlsx` | 2019–2025 | distorção idade-série por etapa/série | 695 |
| `ATU` | `ATU_ESCOLAS_2024.xlsx` | 2019–2025 | média de alunos por turma por etapa/série (inclui ed. infantil) | 897 |
| `IED` | `IED_ESCOLAS_2024.xlsx` | **2021–2025** (2019 só Brasil/UF, 2020 sem escola — P006) | % docentes por nível de esforço 1–6, por etapa | 697 |
| `HAD` | — | só 2025 | horas-aula diárias | não usado (P006) |

Layout: linhas de título, cabeçalho humano em 2–4 linhas, **uma linha de nomes
técnicos**, dados, rodapé com fonte e notas. A posição da linha técnica varia e é
detectada por `src/indicadores_inep.py`. Ausência = `'--'`.

**Ruptura de nomes em `tx_rend` (P009/P014, resolvida).** 2019–2020 usam
`tap_*`/`tre_*`/`tab_*` (aprovação/reprovação/abandono) com sufixos `FUN`, `F14`,
`F04`, `F58`, `F00`…`F08`, `MED`, `M01`…`M04`, `MNS`; 2021+ usam
`1_CAT_*`/`2_CAT_*`/`3_CAT_*` com `FUN`, `FUN_AI`, `FUN_AF`, `FUN_01`…`FUN_09`,
`MED`, `MED_01`…`MED_04`, `MED_NS`. O mapeamento é **posicional** (63 colunas,
mesma ordem). Armadilha: em 2019–2020 a coluna chamada `F58` está sob o rótulo
"1º Ano" e a `F04` sob "Anos Finais". Verifiquei com os dados de RR 2019: a
aprovação média em `tap_F58` é 97,1% (perfil de 1º ano, onde não há retenção) e em
`tap_F04` é 88,0% (perfil de anos finais). **O rótulo humano está certo; o nome
técnico engana.** A base do orientador usou `F04` para anos finais (251/251
valores iguais à planilha). Regra: mapear por posição/rótulo, nunca pelo nome.

### 2.2 Microdados do Censo Escolar (fase 2 — enriquecimento; fase 1 só para D8)

`dados/bruto/microdados_ed_basica_{2019..2024}.csv` e `Tabela_*_2025_V2.csv`,
uma linha por escola, 290–426 colunas, `cp1252`, `;`. Catálogo completo (980
variáveis, presença por ano, preenchimento BR/RR) em `docs/catalogo_variaveis.csv`
e `docs/catalogo_variaveis.html`. Quatro gerações de esquema (CLAUDE.md §2.1).
Só entram na fase 1 as quatro colunas de D8 — todas existem nos sete anos
(`docs/presenca_colunas_escola.csv`); em 2025 as contagens de matrícula estão em
`Tabela_Matricula_2025_V2.csv` (1 linha por escola, P003).

### 2.3 Base longitudinal v1.0 do orientador

`dados/Processados/base_longitudinal_abandono_rr_2019_2025.csv` — 6.054 × 59,
união das quatro fontes filtradas a `SG_UF == 'RR'`, chave `ANO + CO_ENTIDADE`.
Conferi contra as planilhas originais de 2019 (tx_rend e ATU): todas as colunas
comparadas são cópias exatas (§2.1 e P016). O script que a gerou **não está no
repositório**; para reprodutibilidade (regra 9, e §19 da proposta) ela deve ser
regerada por `src/` — `src/indicadores_rr.py` (extração RR para Parquet) já
existe; a montagem/harmonização é o próximo módulo.

---

## 3. Universo, filtros e painéis

### 3.1 Quem entra

1. `SG_UF == 'RR'` (feito na extração).
2. Rede pública: `NO_DEPENDENCIA ∈ {Estadual, Municipal, Federal}` →
   `REDE_PUBLICA = 1`. Privadas ficam na base para descrição, mas **fora do
   modelo** (54 escolas; regras e público distintos).
3. **[PROPOSTA, P017]** Só escolas com **pelo menos uma taxa de rendimento** em
   algum ano. A união das fontes usa o ATU como universo (843 escolas em 2019),
   e o ATU inclui 176 escolas só de educação infantil que nunca terão abandono.
   Elas inflam contagens de "escolas" e percentuais de ausência sem contribuir.

### 3.2 Dois painéis

Uma escola entra no **painel AF** no ano t se `ABANDONO_FUN_AF` (t) não é nulo, e
no **painel EM** se `ABANDONO_MED` (t) não é nulo. Motivos para separar
(orientador §10; confirmado nos dados):

- distribuições diferentes: média AF 2,5–5,4 p.p.; EM 5,7–12,1 p.p.
  (`desfechos_distribuicao.csv`);
- redes diferentes: EM é só estadual e federal (municipais com EM = 0);
- amostras diferentes e pequenas: por ano, ~235 escolas com AF, ~165 com EM,
  ~140 com ambas (`desfechos_cobertura.csv`).

| Ano t | públicas | com AF | com EM | AF ou EM | AF e EM | alvo AF t+1 | alvo EM t+1 |
|------:|---------:|-------:|-------:|---------:|--------:|------------:|------------:|
| 2019 | 798 | 239 | 158 | 261 | 136 | 237 | 157 |
| 2020 | 800 | 237 | 157 | 256 | 138 | 233 | 158 |
| 2021 | 796 | 234 | 159 | 254 | 139 | 235 | 160 |
| 2022 | 823 | 235 | 162 | 257 | 140 | 232 | 166 |
| 2023 | 836 | 233 | 167 | 255 | 145 | 239 | 168 |
| 2024 | 853 | 240 | 168 | 258 | 150 | 243 | 171 |
| 2025 | 854 | 244 | 173 | 262 | 155 | 0 | 0 |

Tamanho efetivo para modelar: **AF ≈ 1.419 linhas com alvo (2019–2024), EM ≈ 980**
(soma das duas últimas colunas). Isso limita a complexidade: modelos tabulares
regularizados, não redes profundas.

---

## 4. Variáveis: origem, definição, fórmula

Convenção de nomes: a da base do orientador (`ABANDONO_MED`, `TDI_FUN_AF`…).
"Origem" cita a planilha e a coluna técnica **por geração**. "Papel" segue o
CLAUDE.md §5: chave, filtro, estrato, preditor, derivada, desfecho.

### 4.1 Identificação e contexto

| Variável | Origem | Significado | Papel |
|---|---|---|---|
| `ANO` | `NU_ANO_CENSO` (2021+) / `Ano` (tx_rend 2019–20) | ano do Censo = ano dos preditores (t) | chave |
| `ANO_ALVO` | derivada: `ANO + 1` se a escola existe em t+1, senão nulo | ano do desfecho | chave |
| `CO_ENTIDADE` | `CO_ENTIDADE` (todas) | código INEP da escola, texto | chave |
| `NO_ENTIDADE` | `NO_ENTIDADE` | nome (varia em 105 escolas; não é chave) | descrição |
| `CO_MUNICIPIO`, `NO_MUNICIPIO` | idem | 15 municípios de RR | estrato |
| `LOCALIZACAO` | `NO_CATEGORIA` (2021+) / `TIPOLOCA` (tx_rend 2019–20) | Urbana / Rural (6 escolas mudam na série) | estrato |
| `DEPENDENCIA` | `NO_DEPENDENCIA` / `Dependad` | Federal, Estadual, Municipal, Privada | filtro + estrato |
| `REDE_PUBLICA` | derivada: `DEPENDENCIA != 'Privada'` | 1/0 | filtro |
| `DISP_ATU`, `DISP_TDI`, `DISP_IED`, `DISP_REND` | derivadas: 1 se a escola tem ≥1 valor daquela fonte no ano | disponibilidade da fonte | controle de ausência |

Fórmula das `DISP_*`: para a fonte $F$ com colunas $c_1..c_k$,
$\text{DISP}_F = 1[\exists j: c_j \ne \text{nulo}]$.

### 4.2 Taxas de rendimento (`tx_rend`)

Todas em **pontos percentuais (0–100)**, uma casa decimal. Nulo (`'--'`) quando
a escola não tem matrícula na etapa/série (ausente estrutural).

| Variável | 2019–2020 | 2021+ | Significado |
|---|---|---|---|
| `APROVACAO_FUN` | `tap_FUN` | `1_CAT_FUN` | aprovação, EF total |
| `APROVACAO_FUN_AI` | `tap_F14` | `1_CAT_FUN_AI` | aprovação, anos iniciais (1º–5º) |
| `APROVACAO_FUN_AF` | `tap_F04` (rótulo "Anos Finais") | `1_CAT_FUN_AF` | aprovação, anos finais (6º–9º) |
| `APROVACAO_MED` | `tap_MED` | `1_CAT_MED` | aprovação, EM total |
| `REPROVACAO_*` | `tre_*` (mesmos sufixos) | `2_CAT_*` | reprovação |
| `ABANDONO_FUN` | `tab_FUN` | `3_CAT_FUN` | abandono, EF total |
| `ABANDONO_FUN_AI` | `tab_F14` | `3_CAT_FUN_AI` | abandono, anos iniciais |
| **`ABANDONO_FUN_AF`** | `tab_F04` | `3_CAT_FUN_AF` | **abandono, anos finais — base do desfecho AF** |
| **`ABANDONO_MED`** | `tab_MED` | `3_CAT_MED` | **abandono, EM total — base do desfecho EM** |

Fórmulas: §1 ("Taxas de rendimento"). Identidade de checagem por linha:
$\text{APROVACAO} + \text{REPROVACAO} + \text{ABANDONO} = 100 \pm 0{,}2$.

As colunas por série (`3_CAT_FUN_06`…`09`, `3_CAT_MED_01`…`04`, `MED_NS`) existem
nas planilhas mas **não estão na base v1.0**. Podem entrar na fase 2 (ex.:
abandono na 1ª série do EM, historicamente o ponto crítico) — não proponho agora
para não multiplicar variáveis com n pequeno.

**Papel em t:** `ABANDONO_*`, `REPROVACAO_*` e `APROVACAO_*` do ano t são
preditores no **Cenário A** (planejamento após o fechamento do ano) e ficam
**fora** no **Cenário B** (alerta antes do fechamento — §7.1). Aprovação é
redundante com as outras duas (somam 100) → usar só reprovação e abandono como
preditores; aprovação fica para descrição.

### 4.3 Distorção idade-série (`TDI`)

Percentual (0–100). Coluna técnica idêntica nos 7 anos.

| Variável | Coluna | Significado |
|---|---|---|
| `TDI_FUN_TOTAL` | `FUN_CAT_0` | TDI no EF total |
| `TDI_FUN_AI` | `FUN_AI_CAT_0` | TDI anos iniciais |
| `TDI_FUN_AF` | `FUN_AF_CAT_0` | TDI anos finais |
| `TDI_MED_TOTAL` | `MED_CAT_0` | TDI no EM |

Papel: **preditor** (era desfecho no desenho anterior — D5). Hipótese H2 do
orientador: TDI alta em t associa-se a abandono maior em t+1. Fórmula: §1.

### 4.4 Média de alunos por turma (`ATU`)

Número de alunos (razão), coluna técnica idêntica nos 7 anos.

| Variável | Coluna | Significado |
|---|---|---|
| `ATU_FUN_TOTAL` | `FUN_CAT_0` | alunos por turma, EF total |
| `ATU_FUN_AI` | `FUN_AI_CAT_0` | anos iniciais |
| `ATU_FUN_AF` | `FUN_AF_CAT_0` | anos finais |
| `ATU_MED_TOTAL` | `MED_CAT_0` | EM |
| **[PROPOSTA] `ATU_MULTI`** | `MULT_ETA_CAT_0` | alunos por turma nas turmas multietapa/multisseriadas/correção de fluxo |
| **[PROPOSTA] `IN_MULTISSERIADA`** | derivada: `MULT_ETA_CAT_0` não nulo | escola tem turmas multisseriadas (1/0) |

**Problema P016.** Em RR 2019, `FUN_AI_CAT_0` só existe para 251 escolas
enquanto `FUN_CAT_0` existe para 643 e `MULT_ETA_CAT_0` para **375**. Nas escolas
multisseriadas a média por série não é definida; o INEP só calcula o total e a
coluna `MULT_ETA`. Entre públicas, `ATU_FUN_AI` fica 71% ausente e `ATU_FUN_AF`
71%, contra 39% do `TDI_FUN_AI` (`ausencia_base_longitudinal.csv`). Essa ausência
é estrutural e **correlacionada com rural/indígena**. Por isso D9: usar
`ATU_FUN_TOTAL` como medida de tamanho de turma no painel AF, com
`IN_MULTISSERIADA` como contexto, e manter `ATU_FUN_AF` só acompanhado de
indicador de ausência.

### 4.5 Esforço docente (`IED`) — 2021+

Percentuais (0–100) que somam 100 por etapa. Ausente em 2019–2020 por falta do
arquivo (não é zero; H6 do orientador).

| Variável | Coluna | Significado |
|---|---|---|
| `IED_FUN_N1`…`N6` | `FUN_CAT_1`…`FUN_CAT_6` | % docentes do EF no nível 1…6 |
| `IED_MED_N1`…`N6` | `MED_CAT_1`…`MED_CAT_6` | % docentes do EM no nível 1…6 |
| `IED_FUN_ALTO` | derivada | $\text{N4}+\text{N5}+\text{N6}$ (EF) |
| `IED_MED_ALTO` | derivada | $\text{N4}+\text{N5}+\text{N6}$ (EM) |

Uso: conjunto **Core+IED** (janela 2021–2024) para medir o ganho incremental;
nunca imputar 2019–2020. As planilhas também trazem `FUN_AI_CAT_*` e
`FUN_AF_CAT_*` (por subetapa), que não estão na v1.0 — `IED_FUN_AF_ALTO` seria
o mais coerente com o painel AF **[PROPOSTA para a regeração da base]**.

### 4.6 Derivadas temporais

Para uma variável $X$ da escola $i$ no ano $t$:

$$X^{\text{LAG1}}_{i,t} = X_{i,t-1}\qquad
X^{\text{DELTA1}}_{i,t} = X_{i,t} - X_{i,t-1}\qquad
X^{\text{T1}}_{i,t} = X_{i,t+1}$$

Nulo quando a escola não tem a variável no ano de referência (primeiro ano da
série, escola nova, etapa não ofertada). Na v1.0: `ABANDONO_{FUN,FUN_AF,MED}_LAG1`;
`{TDI,ATU,ABANDONO}_{FUN_AF,MED_TOTAL/MED}_DELTA1`; `ABANDONO_{FUN,FUN_AF,MED}_T1`.

Regras: (a) `*_T1` é **só desfecho**; (b) `LAG1`/`DELTA1` usam apenas $t-1$,
sem vazamento; (c) derivadas de grupo propostas pelo orientador §11.2 (média
móvel, inclinação, "anos consecutivos com abandono > 0", diferença para a
mediana do município) são calculadas com dados $\le t$ e, quando dependem de
estatística de grupo, ajustadas só no treino.

### 4.7 [PROPOSTA D8] Quatro colunas do Censo já na fase 1

| Variável | Origem (Censo, coluna presente nos 7 anos) | Significado | Papel |
|---|---|---|---|
| `IN_EDUCACAO_INDIGENA` | tabela Escola, `IN_EDUCACAO_INDIGENA` | escola oferta educação escolar indígena (1/0); em RR 2025: 436 escolas = 1 | estrato |
| `TP_LOCALIZACAO_DIFERENCIADA` | tabela Escola | 0 = não diferenciada (417 em RR 2025), 1 = assentamento (48), 2 = terra indígena (436), 8 = ? (7 — código a confirmar no dicionário oficial antes de usar) | estrato |
| `QT_MAT_FUND_AF` | Escola 2019–24 / `Tabela_Matricula_2025` | matrículas nos anos finais | porte / **peso** |
| `QT_MAT_MED` | idem | matrículas no EM | porte / **peso** |
| `ESTRATO_RR` | derivada | capital (Boa Vista) / interior urbano / interior rural não indígena / indígena — estratificação de Almeida & Mussato (2023), já prevista no CLAUDE.md | estrato |

Por que já na fase 1:

- **Equidade.** Metade das escolas públicas de RR tem "INDÍGENA" no nome (442
  de 880 escolas distintas) e o abandono médio nelas é maior (AF 3,99 vs 2,72;
  EM 8,27 vs 6,22 — nome é só proxy; a coluna do Censo é a fonte correta). A
  proposta do orientador (§14.2) reconhece o contexto indígena mas só tem
  urbano/rural na base. Sem `IN_EDUCACAO_INDIGENA` a avaliação de equidade
  central do projeto não é possível.
- **Ruído das taxas (P018).** As taxas são publicadas sem denominador. Uma escola
  com 20 alunos no EM só pode ter abandono 0, 5, 10… p.p.; uma com 400, qualquer
  valor. Com `QT_MAT_*` dá para (i) ponderar cada linha pela matrícula
  ($w_i = \text{QT\_MAT}$) e (ii) reconstruir a contagem aproximada
  $B_i \approx \text{round}(\text{ABANDONO}_i \times \text{QT\_MAT}_i / 100)$ e
  modelar como binomial. O denominador do INEP é a matrícula *final* ($A+R+B$),
  não a inicial do Censo (que inclui transferidos); a aproximação deve ser
  declarada como tal.

Ponto de atenção: a tabela Escola do Censo é um arquivo por ano, com esquema
diferente em 2025 (P003) — a junção é um `merge` 1:1 por (`ANO`, `CO_ENTIDADE`),
`how="left"` a partir da base, `validate="1:1"` (regra 8).

---

## 5. Desfechos (Tabela C)

| Desfecho | Fórmula | Etapa | Anos com alvo | Tipo | Uso |
|---|---|---|---|---|---|
| `ABANDONO_FUN_AF_T1` | $\text{ABANDONO\_FUN\_AF}_{i,t+1}$ | anos finais EF | t = 2019–2024 | contínuo (0–100) | regressão — principal |
| `ABANDONO_MED_T1` | $\text{ABANDONO\_MED}_{i,t+1}$ | ensino médio | t = 2019–2024 | contínuo (0–100) | regressão — principal |
| `OCORRE_AF_T1`, `OCORRE_EM_T1` | $1[\text{ABANDONO}_{t+1} > 0]$ | idem | idem | binário | triagem (a) |
| `ALTO_AF_T1`, `ALTO_EM_T1` | $1[\text{ABANDONO}_{t+1} \ge q_{p}(\text{etapa},t+1)]$ | idem | idem | binário | triagem (b) — **[DECIDIR]** $p$ (ex.: quantil 75 ou 80) ou limite operacional |

Tratamento de `'--'`: nulo; a linha sai do painel daquela etapa (a escola não
ofertou a etapa em t+1 → não há o que prever). Uma escola com abandono em t mas
sem a etapa em t+1 é perda de acompanhamento, não abandono.

### 5.1 O que os desfechos mostram (`desfechos_distribuicao.csv`, públicas)

| Ano | AF n | AF média | AF mediana | AF p90 | AF % zero | EM n | EM média | EM mediana | EM p90 | EM % zero |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 239 | 5,42 | 3,7 | 12,8 | 22,2 | 158 | 10,71 | 7,15 | 25,9 | 17,7 |
| 2020 | 237 | 1,04 | 0,0 | 3,5 | **71,7** | 157 | 1,67 | 0,00 | 4,8 | **70,7** |
| 2021 | 234 | 3,13 | 1,3 | 9,7 | 41,9 | 159 | 5,83 | 2,30 | 16,0 | 35,8 |
| 2022 | 235 | 5,22 | 3,5 | 12,2 | 24,3 | 162 | 12,05 | 10,55 | 25,6 | 11,1 |
| 2023 | 233 | 3,16 | 1,5 | 8,1 | 31,8 | 167 | 7,58 | 6,00 | 17,1 | 14,4 |
| 2024 | 240 | 2,76 | 1,4 | 7,9 | 35,0 | 168 | 5,74 | 3,65 | 13,2 | 25,0 |
| 2025 | 244 | 2,53 | 0,8 | 7,8 | 43,0 | 173 | 6,20 | 4,50 | 14,3 | 19,1 |

Leitura: (1) distribuição assimétrica, com massa em zero e cauda longa (máximo
AF 42,9; EM 50,0) → modelo em duas partes e métricas robustas; (2) 2020 é outro
regime (70% de zeros: regras excepcionais de aprovação/frequência na pandemia) e
2022 é o "rebote"; (3) tendência de queda pós-2022, o que muda a base rate e
exige efeito de ano.

### 5.2 Persistência é fraca (`desfechos_persistencia.csv`)

| Etapa | Transição | n | Spearman(t, t+1) | MAE B1 (repetir t) | MAE B0 (média) |
|---|---|---:|---:|---:|---:|
| AF | 2019→2020 | 233 | 0,23 | 4,86 | 1,55 |
| AF | 2020→2021 | 231 | 0,14 | 3,16 | 3,39 |
| AF | 2021→2022 | 232 | 0,30 | 4,66 | 4,42 |
| AF | 2022→2023 | 229 | 0,38 | 3,89 | 2,97 |
| AF | 2023→2024 | 232 | 0,41 | 2,61 | 2,72 |
| AF | 2024→2025 | 238 | 0,42 | 2,43 | 2,86 |
| EM | 2019→2020 | 156 | 0,10 | 9,79 | 2,57 |
| EM | 2020→2021 | 157 | −0,01 | 6,41 | 6,12 |
| EM | 2021→2022 | 159 | 0,40 | 8,42 | 8,13 |
| EM | 2022→2023 | 162 | 0,46 | 7,62 | 5,50 |
| EM | 2023→2024 | 165 | 0,37 | 5,78 | 4,94 |
| EM | 2024→2025 | 166 | 0,43 | 4,87 | 4,85 |

Em 4 das 6 transições, **prever a média erra menos que repetir o ano anterior**.
A hipótese H1 (persistência relevante) é, no máximo, moderada (ρ ≈ 0,4 fora da
pandemia). Consequências: o problema é difícil; o ganho dos modelos deve ser
medido contra B0 *e* B1; e a variância entre anos (efeito de período) é grande —
um preditor de nível do ano (dummy de ano ou base rate do ano anterior) é
obrigatório. Também reforça P018: parte da não-persistência é ruído de escolas
pequenas.

---

## 6. Preparação dos dados

### 6.1 Leitura e tipos

`src/indicadores_rr.py`: lê cada planilha em `read_only`, detecta a linha de
nomes técnicos, filtra `SG_UF == 'RR'`, converte `'--'` → nulo, `CO_ENTIDADE`/
`CO_MUNICIPIO` → string, indicadores → `Float64` nullable; grava
`dados/interim/indicadores_rr/{tipo}_{ano}.parquet`. Depois, harmonização de
nomes (§4) e união por (`ANO`, `CO_ENTIDADE`) com `validate="1:1"`.

### 6.2 Validações automáticas (as do orientador, a repetir na regeração)

chave única; taxas em [0, 100]; ATU > 0; aprov + reprov + aband = 100 ± 0,2;
Σ IED níveis = 100 ± 0,2; escola não muda de município nem dependência;
contagem de mudanças de localização e de nome.

### 6.3 Escala e transformação

Taxas ficam em p.p. (interpretável para gestor). Para modelos lineares,
padronização $z = (x - \bar{x}_{\text{treino}})/s_{\text{treino}}$ ajustada no
treino. Para o alvo, testar também $\log(1 + y)$ na parte contínua do modelo em
duas partes (cauda longa); reportar sempre na escala original.

### 6.4 Ausência

Três tipos, tratados diferente:

| Tipo | Exemplo | Tratamento |
|---|---|---|
| estrutural (não se aplica) | `ABANDONO_MED` em escola sem EM; `ATU_FUN_AF` em multisseriada | a linha sai do painel da etapa, ou a variável recebe indicador de ausência (`IN_MULTISSERIADA`) — **nunca 0** |
| estrutural da coleção | IED 2019–2020 | conjunto Core sem IED; Core+IED só 2021+ |
| eventual | escola com TDI mas sem ATU num ano | (i) modelos que aceitam nulo (árvores com tratamento nativo); (ii) imputação por mediana estratificada por ano × etapa **ajustada no treino** + indicador `NA_x`; (iii) análise completa como sensibilidade |

Antes de imputar: percentual ausente por variável × ano × estrato (já em
`ausencia_base_longitudinal.csv` para o total) e teste se a ausência se associa
ao desfecho (se sim, o indicador de ausência é informativo e fica).

### 6.5 Pesos [PROPOSTA D8]

$w_{i,t} = \text{QT\_MAT}_{i,t}$ da etapa, opcionalmente truncado no percentil
95 para uma escola grande não dominar. Toda métrica é reportada **com e sem
peso**; a versão ponderada responde "quantos alunos" e a não ponderada "quantas
escolas".

---

## 7. Métodos

### 7.1 Desenho temporal

| Conjunto | Preditores (t) | Desfecho (t+1) | Uso |
|---|---|---|---|
| Treino | 2019–2022 | 2020–2023 | ajuste |
| Validação | 2023 | 2024 | escolha de variáveis, hiperparâmetros, limiar |
| Teste | 2024 | 2025 | **uma única avaliação, após congelar tudo** |

Mais walk-forward: treino ≤ 2020 → 2021; ≤ 2021 → 2022; ≤ 2022 → 2023;
≤ 2023 → 2024. Dois cenários de preditores: **A** (pós-fechamento: inclui
rendimento de t) e **B** (alerta antecipado: exclui abandono/reprovação/aprovação
de t; mantém TDI, ATU, IED, lags de t−1). A mesma escola aparece em treino e
teste em anos diferentes — isso é o cenário real de uso; a generalização para
escolas novas é medida à parte com *group k-fold* por escola (só como robustez).

### 7.2 Baselines (obrigatórios; todos os modelos são comparados a eles)

| Código | Previsão $\hat{y}_{i,t+1}$ | O que testa |
|---|---|---|
| B0 | $\bar{y}$ do treino, por etapa | nível médio |
| B1 | $y_{i,t}$ (persistência) | "o passado repete" |
| B2 | mediana do treino por etapa × localização × dependência | estrato explica? |
| B3 | Ridge / Elastic Net com Core padronizado | linear regularizado |
| B4 | logística regularizada (para os binários) | idem, triagem |

### 7.3 Modelos estatísticos interpretáveis

**Elastic Net** (regressão linear penalizada). Minimiza

$$\frac{1}{2n}\sum_i (y_i - \mathbf{x}_i^\top\beta)^2 + \lambda\Big[\alpha\|\beta\|_1 + \tfrac{1-\alpha}{2}\|\beta\|_2^2\Big]$$

$\lambda$ controla a força da penalização (encolhe coeficientes → menos
sobreajuste), $\alpha \in [0,1]$ mistura L1 (zera coeficientes → seleção) e L2
(estabiliza com preditores correlacionados). Ambos escolhidos na validação
temporal, nunca no teste. Coeficientes padronizados são a explicação global.

**Modelo em duas partes (hurdle).** Para um alvo com muitos zeros:

$$E[y \mid \mathbf{x}] = \underbrace{P(y>0 \mid \mathbf{x})}_{\text{logística}} \times \underbrace{E[y \mid y>0, \mathbf{x}]}_{\text{regressão nos positivos}}$$

A primeira parte responde "vai haver abandono?"; a segunda, "quanto, se
houver?". A segunda pode ser linear em $\log(y)$ ou Gama. Dá as duas saídas que
o gestor precisa (probabilidade e magnitude) com um só modelo.

**Modelo misto (intercepto aleatório por escola).**

$$y_{i,t+1} = \mathbf{x}_{i,t}^\top\beta + u_i + \varepsilon_{i,t},\quad u_i \sim N(0,\sigma_u^2)$$

$u_i$ captura o que é persistente da escola e não está nos preditores; a razão
$\sigma_u^2/(\sigma_u^2+\sigma_\varepsilon^2)$ (correlação intraclasse) diz quanto
do abandono é "da escola" versus "do ano". Dada a persistência fraca (§5.2),
esperar ICC baixo; ainda assim é o teste direto de H1.

**GAM (modelo aditivo generalizado).** $g(E[y]) = \beta_0 + \sum_j f_j(x_j)$ com
$f_j$ curvas suaves (splines) — permite ver, por exemplo, se o efeito de TDI é
linear ou tem limiar, mantendo cada efeito num gráfico.

### 7.4 Modelos de aprendizado de máquina

- **Random Forest.** Média de centenas de árvores de decisão, cada uma treinada
  em amostra bootstrap e com subconjunto aleatório de variáveis por divisão.
  Captura interações e não linearidades sem ajuste fino; referência não linear.
- **Gradient Boosting (LightGBM / XGBoost).** Árvores pequenas ajustadas em
  sequência, cada uma corrigindo o erro residual da anterior, com taxa de
  aprendizado e regularização. Costuma ser o melhor em tabular pequeno/médio, mas
  exige busca restrita de hiperparâmetros na validação temporal para não
  sobreajustar ~1.000 linhas. Trata nulo nativamente.
- **CatBoost.** Boosting com tratamento embutido de categóricas (município,
  dependência, estrato) e de ausentes; robusto a hiperparâmetros.
- **EBM (Explainable Boosting Machine).** GAM treinado por boosting: um termo por
  variável (mais poucas interações pareadas), cada um plotável. Aproxima o
  desempenho de boosting mantendo a explicação do GAM.
- Ensemble só se ganhar de forma consistente no walk-forward. Redes neurais
  fora desta fase (n pequeno).

### 7.5 Seleção de variáveis (regra 3 do CLAUDE.md)

Conjunto **Core** pré-especificado por pertinência conceitual (§4), não por
correlação com o alvo: nível e tendência de abandono/reprovação (Cenário A),
TDI, ATU total, `IN_MULTISSERIADA`, localização, dependência, estrato, município
(como categórica ou efeito aleatório), ano. **Core+IED** adiciona `IED_*_ALTO`.
Redundância *entre preditores* (ex.: aprovação vs reprovação+abandono) é
removida. A regularização (Elastic Net) e a importância por permutação
**dentro da validação** são os únicos mecanismos data-driven, e nunca olham o
teste.

### 7.6 Ruptura 2020–2021

| Análise | Amostra | Pergunta |
|---|---|---|
| S1 | todas as transições 2019→20 … 2024→25 | desempenho com todo o histórico |
| S2 | preditores 2021–2024 | regime pós-pandemia |
| S3 | exclui transições com desfecho em 2020 ou 2021 | efeito direto do período excepcional |
| S4 | tudo, com dummies de ano | ajuste explícito de nível |

Conclusões só valem se estáveis entre S1–S4. Nota: com S3 o treino cai para
2021→22 e 2022→23 (duas transições) — o custo em n deve ser reportado.

### 7.7 Métricas

Regressão (em p.p.), com $e_i = y_i - \hat{y}_i$:

- $\text{MAE} = \frac{1}{n}\sum |e_i|$ — principal; $\text{MAE}_w = \sum w_i|e_i| / \sum w_i$ ponderada.
- $\text{RMSE} = \sqrt{\frac{1}{n}\sum e_i^2}$ — pune erros grandes (escolas de alto abandono).
- $\text{MedAE} = \text{mediana}(|e_i|)$ — robusta a extremos.
- $R^2 = 1 - \sum e_i^2 / \sum (y_i-\bar{y})^2$ — só complementar (pode ser negativo no teste temporal).
- Spearman $\rho$ entre $\hat{y}$ e $y$ = Pearson entre os postos — qualidade de ordenação.
- **Recall@K** $= |\text{Top}_K(\hat{y}) \cap \text{Top}_K(y)| / K$; com conjuntos do mesmo tamanho, Precision@K = Recall@K. Reportar para K = 10, 20, 30 (capacidade realista) e a *captura de alunos*: fração dos abandonos (em alunos, com `QT_MAT`) que está nas K escolas escolhidas.

Classificação (probabilidade $p_i$, evento $y_i \in \{0,1\}$):

- **PR-AUC** — área sob precisão × recall; principal quando o positivo é raro ou é o que importa.
- ROC-AUC — complementar; $P(p_{\text{pos}} > p_{\text{neg}})$.
- Recall, precisão e $F_\beta$ com $\beta > 1$ (perder uma escola de risco custa mais que um alerta a mais) no limiar escolhido na validação.
- **Brier** $= \frac{1}{n}\sum (p_i - y_i)^2$ e curva de calibração (decis de $p$ vs frequência observada).

Tudo reportado **por transição** (walk-forward) e não só na média; intervalos
por bootstrap de escolas (reamostrar escolas, não linhas, para respeitar o
painel).

### 7.8 Explicabilidade (associação, não causa)

Global: coeficientes padronizados (lineares); importância por permutação na
validação; SHAP para árvores (cuidado com preditores correlacionados); PDP/ALE
para forma do efeito; estabilidade da importância entre anos. Por escola:
risco previsto, intervalo, 3–5 contribuições (SHAP local) em linguagem simples,
histórico. Texto padrão: "fatores associados ao risco no modelo", nunca "causa".
Sem contrafactuais automáticos ("reduza TDI em X").

### 7.9 Equidade

Todas as métricas por estrato: `ESTRATO_RR` (4 níveis), urbano/rural,
dependência, município (agrupado quando n < 30). Diferença substancial de MAE,
recall ou calibração entre estratos é reportada como limitação e investigada
antes de uso operacional. O estrato **não** entra como preditor sem decisão
explícita (CLAUDE.md §6 — é decisão de equidade, **[DECIDIR]**).

---

## 8. Matriz de experimentos

| Exp | Etapa | Atributos | Modelo | Pergunta |
|---|---|---|---|---|
| E0 | AF, EM | — | B0, B1, B2 | é possível superar o trivial? |
| E1 | AF, EM | Core | Elastic Net (B3) / logística (B4) | quanto explica o linear? |
| E2 | AF, EM | Core | GAM / EBM | não linearidade interpretável ajuda? |
| E3 | AF, EM | Core | Random Forest | interações? |
| E4 | AF, EM | Core | LightGBM / CatBoost | ganho robusto no walk-forward? |
| E5 | AF, EM | Core+IED (2021+) | melhor de E1–E4 | IED agrega? |
| E6 | AF, EM | Cenário B | melhor | quanto se perde ao antecipar o alerta? |
| E7 | AF, EM | Core, S2/S3/S4 | melhor | resiste à pandemia? |
| E8 | AF, EM | Core + Censo harmonizado (fase 2) | melhor | quanto a estrutura da escola agrega? |
| **E9 [PROPOSTA]** | AF, EM | Core, com/sem peso `QT_MAT` | melhor | ponderar muda quem é priorizado? |

Seleção final (orientador §15.1): melhora sobre B0/B1 + estabilidade entre
transições + MAE/PR-AUC + calibração + Top-K + subgrupos + simplicidade. Ganho
pequeno com perda de transparência não justifica adoção.

---

## 9. O que muda no repositório

1. `CLAUDE.md` §1: pergunta e desfechos passam a ser os deste documento;
   transferência nacional→RR e TDI-como-desfecho viram "desenho anterior".
2. `DECISOES.md`: entradas datadas para D1–D7 (decisão do orientador,
   17/09/2026) e para o que você aprovar de D8–D9.
3. `docs/desfechos.csv` (Tabela C) = §5; `docs/dicionario_anotado.csv`
   (Tabela B) = §4 em CSV — ambos gerados a partir deste documento.
4. `src/base_longitudinal.py`: harmonização §4 + união + derivadas §4.6 +
   validações §6.2 + (se D8) merge com o Censo. Saída em
   `dados/processado/` como Parquet + CSV, com hash em `MANIFEST`.
5. `filtros.py`/`agregacao.py` sobre o Censo ficam para a fase 2 (E8).

---

## 10. Extensão para 2007–2018 [DECIDIR]

Você vai baixar os indicadores anteriores a 2019. O que muda:

- **Nomes.** Espere o padrão de 2019–2020 (`tap_/tre_/tab_`, `F14/F04/F58`) ou
  anterior; o mapeamento posicional e o teste do §2.1 (média de aprovação por
  coluna) devem ser repetidos ano a ano — nunca confiar no nome.
- **EF de 8 anos.** Até o início dos anos 2010 coexistem EF de 8 e de 9 anos; as
  planilhas já dizem "Ensino Fundamental de 8 e 9 anos" e agregam, mas a
  definição de "anos finais" muda de 5ª–8ª para 6º–9º. Registrar como
  `ruptura_de_esquema`.
- **IED** existe desde 2007 no site do INEP (a confirmar ao baixar) — fecharia o
  buraco de 2019–2020 (P006).
- **Desenho de validação.** Com 2007–2025 há 18 transições: o treino cresce, o
  walk-forward ganha poder, e a pandemia vira um choque no meio da série em vez
  de um terço dela. A partição §7.1 seria refeita (ex.: treino ≤ 2018, validação
  2019–2023, teste 2024→25) — decisão a tomar **antes** de olhar resultados.
- **Censo** anterior a 2019 tem outro esquema (nomes `*_ESC` etc.); afeta só D8
  e a fase 2.
- Todos os arquivos novos entram em `dados/bruto/`, com `MANIFEST.csv`
  regenerado, e em `src/config.py`/`indicadores_inep.ANOS`.

---

## Referências

- INEP. Taxas de rendimento escolar; Taxa de distorção idade-série; Média de
  alunos por turma; Esforço docente (notas técnicas e planilhas; rodapés das
  planilhas em `dados/interim/brutos_inep_extraido/`).
- INEP. Nota técnica do indicador de esforço docente (2014), link no rodapé de
  `IED_ESCOLAS_2024.xlsx`.
- Almeida & Mussato (2023) — estratificação territorial de Roraima (CLAUDE.md §1).
- Proposta detalhada do orientador (17/09/2026), §§ 4, 7–15 — base das seções
  5, 7 e 8 deste documento.
- Zou & Hastie (2005), Elastic Net; Breiman (2001), Random Forest; Friedman
  (2001), Gradient Boosting; Saito & Rehmsmeier (2015), PR-AUC; Lundberg & Lee
  (2017), SHAP; Molnar (2022), Interpretable ML.
