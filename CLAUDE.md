# CLAUDE.md — Projeto de pesquisa: risco de abandono escolar em Roraima

Este arquivo é a fonte de verdade do projeto. Leia inteiro antes da primeira
alteração e releia a seção "Regras invioláveis" antes de qualquer commit.
Última revisão: 2026-09-29.

---

## 1. Contexto científico

Projeto PIBIC/UERR (Edital 35/2026) + artigo da disciplina de mineração de
dados. Orientador: Prof. Bruno Cesar Barreto Figueiredo.

**Pergunta de pesquisa (vigente desde 17/09/2026):** com os indicadores
educacionais consolidados de uma escola no ano `t`, é possível estimar a
intensidade esperada de abandono no ano `t+1`, por etapa, de modo a apoiar
ações preventivas de gestão? A comparação de métodos de mineração de dados
(baselines, lineares regularizados, GAM/EBM, florestas, boosting) substitui a
comparação de famílias do desenho anterior.

O plano metodológico completo — variáveis, fórmulas, fontes, desenho temporal,
matriz de experimentos — está em **`docs/metodologia_variaveis.md`** (v0.1,
2026-09-20), escrito a partir da proposta do orientador (`docs/README.md` e
`docs/Proposta_Detalhada_Analise_Preditiva_Abandono_Escolar_Roraima.pdf`,
17/09/2026). Este CLAUDE.md dá as regras; aquele documento dá o método. Se
divergirem em número, vale o CSV gerado por código (regra 9).

**Desenho anterior (arquivado, não apagado):** comparar três famílias de
modelos — treinado só com Roraima, nacional aplicado direto, nacional adaptado
por aprendizado por transferência — e usar a distorção idade-série como segundo
desfecho. Continua registrado porque parte do inventário e das regras nasceu
dele; nada dele volta sem decisão explícita.

**Desfechos (fase 1):** taxa de abandono da etapa no ano seguinte —
`ABANDONO_FUN_AF_T1` (anos finais do EF) e `ABANDONO_MED_T1` (ensino médio),
contínuos em 0–100. Binários auxiliares para triagem: `OCORRE_*_T1`
(abandono > 0) e `ALTO_*_T1` (acima de um quantil ainda a decidir). A **TDI
deixou de ser desfecho e passou a preditor** (D5 da metodologia).

**Dois painéis separados, AF e EM** (D2): distribuições, redes e amostras
diferentes — EM é só estadual e federal. Por ano, ~235 escolas públicas com AF
e ~165 com EM (`docs/desfechos_cobertura.csv`).

**Unidade de análise:** escola-ano. Chave composta: `CO_ENTIDADE` + ano
(`NU_ANO_CENSO` nos microdados, `ANO` na base longitudinal).

**Produto final:** observatório analítico com mapa, fatores associados,
incerteza e priorização de escolas para diagnóstico — nunca para
ranqueamento ou punição. A base é agregada por escola: **não prediz aluno**.

**Avaliação de equidade:** desempenho comparado entre capital, interior
urbano, interior rural não indígena e escolas indígenas (estratificação de
Almeida & Mussato, 2023). Depende de `IN_EDUCACAO_INDIGENA` e
`TP_LOCALIZACAO_DIFERENCIADA` do Censo, que a base v1.0 não tem (D8, em aberto).

### Vocabulário que não pode escorregar

- **Abandono ≠ evasão.** Abandono existe por escola; evasão só existe agregada
  até UF. Se a palavra "evasão" aparecer em código, nome de variável, docstring
  ou commit referindo-se ao desfecho por escola, está errado.
- **Ausente estrutural ≠ ausente por falta de resposta.** Escola fora de
  atividade, sem prédio escolar ou que não oferta a etapa tem blocos inteiros
  vazios por definição. Isso é "não se aplica", não é dado faltante.
- **Explicabilidade é sinal analítico, não causalidade.** Nenhum texto gerado
  deve afirmar que uma variável "causa" abandono.

---

## 2. Estado atual dos dados

Tudo em `dados/bruto/` está inventariado com sha256 em `dados/MANIFEST.csv`
(gerado por `python -m src.manifesto`). As contagens abaixo vêm de
`docs/inventario.csv` e `docs/inventario_indicadores.csv` — se divergirem,
os CSVs mandam.

### 2.1 Microdados do Censo Escolar (fase 2 — enriquecimento)

Todos `cp1252`, separador `;`, uma linha por escola. Nomes originais do INEP
preservados — inclusive a extensão `.CSV` em maiúsculas de 2020.

| Ano  | Arquivo(s) em `dados/bruto/` | Colunas | Linhas (RR) |
|------|------------------------------|---------|-------------|
| 2019 | `microdados_ed_basica_2019.csv` | 370 | 228.521 (915) |
| 2020 | `microdados_ed_basica_2020.CSV` | 370 | 224.229 (919) |
| 2021 | `microdados_ed_basica_2021.csv` | 370 | 221.140 (941) |
| 2022 | `microdados_ed_basica_2022.csv` | 385 | 224.649 (950) |
| 2023 | `microdados_ed_basica_2023.csv` | 408 | 217.625 (941) |
| 2024 | `microdados_ed_basica_2024.csv` | 426 | 215.545 (958) |
| 2025 | `Tabela_Escola_2025_V2.csv` | 290 | 214.192 (969) |
| 2025 | `Tabela_Turma_2025_V2.csv`, `Tabela_Matricula_2025_V2.csv`, `Tabela_Docente_2025_V2.csv` | 218 / 263 / 184 | 178.772 / 178.766 / 178.772 (908) |

Duas gerações de nomenclatura de arquivo e **quatro gerações de esquema**
(ver `docs/presenca_colunas_escola.csv`, coluna × ano, valor = posição da
coluna no arquivo):

- 2019–2021: 370 colunas idênticas, subconjunto estrito de 2022.
- 2022: +15 (parcerias com poder público, `IN_FORMA_CONT_*`,
  `IN_ESCOLARIZACAO`). 45 colunas de 2019–2022 somem em 2023
  (`QT_SALAS_EXISTENTES`, `QT_COMPUTADOR`, `QT_FUNCIONARIOS`, `IN_BANHEIRO_*`,
  `QT_EQUIP_*`…).
- 2023: +19; 2024: +16 (`IN_EDUC_AMB_*`, `NO_DISTRITO`…).
- 2025: as contagens `QT_MAT_*`, `QT_DOC_*`, `QT_TUR_*` e os indicadores de
  oferta `IN_MED`, `IN_NOTURNO`, `IN_PROF_*` saem da tabela Escola; contagens
  vão para Turma/Matrícula/Docente (já no nível escola, 1:1 — P003), oferta
  vira a família `IN_COMUM_*` / `IN_ESP_EXCLUSIVA_*` (P001). 33 colunas só
  existem em 2025.
- **210 colunas existem nos sete anos.** Preditores candidatos saem daí,
  salvo regra explícita registrada.

**Nunca monte caminho por concatenação com o ano** — use `caminho(ano,
tabela)` de `src/config.py`. Turma/Matrícula/Docente só existem para 2025;
nos anos anteriores as contagens estão dentro da própria tabela Escola.

`dados/bruto/doc-censo/` guarda documentação oficial que acompanhou os
microdados: `Leia-me-2021.pdf` e `Nota-2021.pdf` (nota do INEP de 01/11/2022
sobre correção de `QT_DOC_*` em 2007–2021 — P011).

Na fase 1 só entram do Censo as quatro colunas de D8 (§6), todas presentes nos
sete anos: `IN_EDUCACAO_INDIGENA`, `TP_LOCALIZACAO_DIFERENCIADA`,
`QT_MAT_FUND_AF`, `QT_MAT_MED`. O resto do Censo é a fase 2 (experimento E8).

### 2.2 Indicadores educacionais do INEP (fonte da fase 1)

`dados/bruto/brutos-inep/` tem 83 `.zip` (um é duplicata bit-a-bit, P005).
Cada zip traz a mesma tabela em `.xlsx` e `.ods` mais o `md5_*.txt` do INEP.
`python -m src.extrair_brutos_inep` extrai **só o `.xlsx` e o md5** para
`dados/interim/brutos_inep_extraido/{tipo}/{ano}/`, confere o md5 e grava
`_manifesto.csv` ali. Nunca leia o zip direto; nunca extraia para `bruto/`.

Cobertura por nível (U = Brasil/Regiões/UFs, M = municípios, E = escolas):

| Indicador | Significado | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|-----------|-------------|------|------|------|------|------|------|------|
| `tx_rend` | taxas de rendimento: aprovação, reprovação, **abandono** | UME | UME | UME | UME | UME | UME | ME |
| `TDI` | taxa de **distorção idade-série** | UME | UME | UME | UME | UME | UME | UME |
| `ATU` | média de alunos por turma | UME | UME | UME | UME | UME | UME | UE |
| `IED` | esforço docente (% docentes por nível 1–6) | U | UM | UME | UME | UME | UME | UME |
| `HAD` | horas-aula diárias | — | — | — | — | — | — | UME |

No nível escola, `tx_rend`, `TDI` e `ATU` cobrem 2019–2025; `IED` só 2021–2025
(P006), por isso "Core+IED" é um experimento à parte (E5). HAD não entra (P006).

`python -m src.indicadores_rr` faz o recorte de RR de cada planilha de escolas
e grava `dados/interim/indicadores_rr/{tipo}_{ano}.parquet` com os **nomes
técnicos originais** — a harmonização entre gerações vem depois.

Layout de toda planilha (uma aba por arquivo): linhas de título, cabeçalho
humano em 2–4 linhas, **uma linha de nomes técnicos** e então os dados. A
posição da linha técnica varia (9 em tx_rend/TDI/ATU/HAD, 11 em IED) — use
`src/indicadores_inep.py`, que a detecta, nunca `skiprows` fixo. Ausência é a
string `'--'` (em HAD, célula vazia — P015). `CO_ENTIDADE` e `CO_MUNICIPIO`
chegam como inteiros da planilha e devem virar `string` na leitura (regra 6).
Nos níveis municípios e UF há várias linhas por unidade (Localização ×
Dependência, P013); só o nível escola tem uma linha por escola —
`CO_ENTIDADE` único nos 40 arquivos de escolas (verificado em
`docs/inventario_indicadores.csv`).

**Ruptura de nomes em `tx_rend` (P009/P014, resolvida):** 2019–2020 usam
`tap_*` / `tre_*` / `tab_*` (aprovação / reprovação / abandono) com etapas
`FUN`, `F14`, `F04`, `F58`, `F00..F08`, `MED`, `M01..M04`, `MNS`; 2021+ usam
`1_CAT_*` / `2_CAT_*` / `3_CAT_*` com `FUN`, `FUN_AI`, `FUN_AF`,
`FUN_01..09`, `MED`, `MED_01..04`, `MED_NS`. Mapeamento **posicional** 1:1
(63 colunas). Armadilha verificada em 2026-09-20: em 2019–2020 o nome técnico
engana e o rótulo humano está certo — `F04` é Anos Finais (aprovação média
88,0% em RR 2019) e `F58` é 1º ano (97,1%). **Mapeie por posição e rótulo
humano, nunca pelo nome.** Colunas técnicas por indicador × nível × ano, com a
descrição montada do cabeçalho humano:
`docs/presenca_colunas_indicadores.csv`. `tx_rend_municipios_2019` não tem
linha técnica (nomes sintéticos `_SEM_NOME_n`).

### 2.3 Base longitudinal v1.0 (entregue pelo orientador)

`dados/Processados/` — entregue pronta em 17/09/2026, **não é gerada por este
repositório ainda**. Atenção: coexiste com `dados/processado/` (saída deste
projeto, ainda vazia); são pastas diferentes, não confunda.

- `base_longitudinal_abandono_rr_2019_2025.csv` — 6.054 linhas × 59 colunas,
  união de `tx_rend`, `TDI`, `ATU` e `IED` filtrados a RR, chave
  `ANO + CO_ENTIDADE` única (`validacao_base_longitudinal.json`). Encoding
  `utf-8-sig`. Traz lags (`*_LAG1`), variações (`*_DELTA1`) e os alvos
  (`*_T1`), já com a semântica t → t+1.
- `dicionario_base_longitudinal.csv`, `resumo_cobertura_longitudinal.csv`,
  `validacao_base_longitudinal.json`, `log_fontes_longitudinal.json`,
  `manifesto_fontes_longitudinal.csv`.

Conferida contra as planilhas originais de 2019 (tx_rend e ATU): cópias exatas.
Validações do orientador que passam: chave única, taxas em [0, 100], ATU > 0,
aprovação + reprovação + abandono = 100 ± 0,2, Σ IED = 100 ± 0,2, nenhuma
escola muda de município ou dependência (6 mudam de localização, 105 de nome).

`python -m src.analise_base_longitudinal` gera dela as tabelas descritivas em
`docs/`: `desfechos_distribuicao.csv`, `desfechos_persistencia.csv`,
`desfechos_cobertura.csv`, `ausencia_base_longitudinal.csv`,
`estrato_nome_indigena.csv`.

**Dois fatos dessa análise mandam no desenho:** (i) a distribuição do abandono
é assimétrica, com massa em zero e cauda longa — 2020 tem ~71% de zeros, outro
regime → modelo em duas partes e métricas robustas; (ii) a persistência ano a
ano é fraca (Spearman entre −0,01 e 0,46) e **em 9 das 12 transições prever a
média erra menos que repetir o ano anterior** (3 de 6 no AF, 6 de 6 no EM,
`docs/desfechos_persistencia.csv`) → todo modelo é comparado a B0 *e* B1.

O script que montou a base não veio junto; reproduzi-lo em `src/` é a tarefa
da fase atual (§8).

---

## 3. Regras invioláveis

1. **`dados/bruto/` é somente leitura.** Não renomeie, não mova, não
   sobrescreva, não normalize nomes de arquivo, não extraia zip dentro dela.
   O nome original é procedência. O mesmo vale para `dados/Processados/`, que
   é entrega do orientador: leia, não edite.
2. **Nenhum dado versionado.** `dados/` inteiro fora do git, exceto
   `dados/MANIFEST.csv`.
3. **Nunca selecione variável pela correlação com o desfecho.** Seleção é por
   pertinência conceitual, estabilidade temporal, preenchimento e redundância
   *entre preditores*. Correlação com o alvo é sobreajuste. Única exceção: a
   correlação do desfecho com ele mesmo no ano anterior, que define o
   baseline B1.
4. **Nada de vazamento temporal.** Preditores do ano `t` → desfecho do ano
   `t+1`. Nenhuma informação conhecida depois do desfecho entra como preditor.
   Toda transformação (padronização, imputação, quantis, limiares) é ajustada
   **só no treino** e aplicada ao resto.
5. **Nunca impute ausente estrutural como 0.** Se não souber distinguir, marque
   como desconhecido e registre em `docs/problemas.csv`. Nas planilhas de
   indicadores, `'--'` é ausente, não zero. Escola sem a etapa em t+1 sai do
   painel daquela etapa — é perda de acompanhamento, não abandono zero.
6. **Tipagem obrigatória:** `CO_ENTIDADE` e `CO_MUNICIPIO` como `string`
   (jamais numérico); `IN_*` e `TP_*` como `Int8` nullable; `QT_*` como `Int32`
   nullable; taxas e indicadores como `Float64` nullable. Nunca `int8`/`bool`
   minúsculos — eles não representam ausência.
7. **Nunca junte em granularidade fina.** Turma, Matrícula e Docente são
   agregadas a uma linha por `CO_ENTIDADE` *antes* de qualquer merge com
   Escola. Indicadores no nível municipal só entram filtrados a uma linha por
   município.
8. **Todo `merge` leva `validate=` explícito** (`"1:1"` no caso normal) e
   `how="left"` a partir da tabela base.
9. **Toda contagem publicada é gerada por código**, nunca digitada. Se um
   número aparece em `docs/` ou neste arquivo, existe uma linha de código que
   o produziu.
10. **Não invente nomes de coluna, códigos de categoria ou etapas de ensino.**
    Verifique lendo o arquivo (ou os CSVs de presença em `docs/`). Se não
    conseguir verificar, pare e pergunte.

---

## 4. Estrutura do projeto

```
abandono-escolar/
├── dados/                          # fora do git, exceto MANIFEST.csv
│   ├── bruto/                      # imutável
│   │   ├── microdados_ed_basica_{2019..2024}.csv, Tabela_*_2025_V2.csv
│   │   ├── brutos-inep/            # 83 .zip de indicadores (tx_rend, TDI, ATU, IED, HAD)
│   │   └── doc-censo/              # PDFs de documentação do INEP
│   ├── interim/
│   │   ├── brutos_inep_extraido/   # {tipo}/{ano}/*.xlsx + md5 + _manifesto.csv
│   │   └── indicadores_rr/         # {tipo}_{ano}.parquet, recorte RR, nomes originais
│   ├── Processados/                # base longitudinal v1.0 do orientador (somente leitura)
│   ├── processado/                 # saída deste projeto (painel regerado)
│   └── MANIFEST.csv                # ano, tabela, arquivo, sha256, data de download
├── docs/
│   ├── metodologia_variaveis.md          # método: variáveis, fórmulas, desenho, experimentos
│   ├── README.md                         # documentação da base v1.0 (orientador)
│   ├── Proposta_Detalhada_*.pdf          # plano metodológico do orientador
│   ├── inventario.csv                    # Tabela A: microdados por ano (gerado)
│   ├── presenca_colunas_escola.csv       # coluna × ano/tabela, valor = posição (gerado)
│   ├── inventario_indicadores.csv        # uma linha por planilha de indicador (gerado)
│   ├── presenca_colunas_indicadores.csv  # coluna × tipo/nível × ano + descrição (gerado)
│   ├── catalogo_variaveis_microdados.csv # coluna × arquivo: bloco, preenchimento, exemplos (gerado)
│   ├── catalogo_variaveis.csv            # coluna consolidada × 10 arquivos (gerado)
│   ├── catalogo_variaveis.html           # página navegável do catálogo (gerada)
│   ├── desfechos_distribuicao.csv        # etapa × ano: n, média, p90, % zeros (gerado)
│   ├── desfechos_persistencia.csv        # etapa × transição: Spearman, MAE B0/B1 (gerado)
│   ├── desfechos_cobertura.csv           # ano: públicas, com AF, com EM, com alvo (gerado)
│   ├── ausencia_base_longitudinal.csv    # % de ausência por variável (gerado)
│   ├── estrato_nome_indigena.csv         # proxy fraco de estrato indígena (gerado)
│   ├── dicionario_anotado.csv            # Tabela B: variável × papel (a fazer)
│   ├── desfechos.csv                     # Tabela C (a fazer; = §5 da metodologia)
│   ├── problemas.csv                     # Tabela D (P001–P018)
│   ├── funil_contagem.csv                # (a fazer)
│   └── DECISOES.md                       # log de decisões (ver seção 6)
├── notebooks/
│   └── 01_leitura_e_recorte.ipynb        # (a fazer)
├── src/
│   ├── config.py               # caminhos, ARQUIVOS, caminho(), listas de colunas
│   ├── manifesto.py            # gera dados/MANIFEST.csv
│   ├── extrair_brutos_inep.py  # zip → interim/brutos_inep_extraido, confere md5
│   ├── indicadores_inep.py     # caminho_indicador(), perfil e inventário das planilhas
│   ├── indicadores_rr.py       # recorte RR das planilhas de escolas → Parquet
│   ├── analise_base_longitudinal.py  # tabelas descritivas da base v1.0 do orientador
│   ├── leitura.py              # perfil dos CSV de microdados, inventário, presença
│   ├── catalogo_microdados.py  # catálogo de todas as variáveis, com estatísticas BR/RR
│   ├── relatorio_catalogo.py   # + relatorio_catalogo.html (molde) → docs/catalogo_variaveis.html
│   ├── base_longitudinal.py    # harmonização + união + derivadas + validações (a fazer)
│   ├── filtros.py              # funil de recorte com contagem (fase 2)
│   └── agregacao.py            # Turma/Matrícula/Docente → escola (fase 2)
├── requirements.txt
└── CLAUDE.md
```

Comandos que regeneram o que está em `docs/` e `dados/`:

```
python -m src.manifesto                  # dados/MANIFEST.csv
python -m src.extrair_brutos_inep        # dados/interim/brutos_inep_extraido/
python -m src.indicadores_inep           # docs/inventario_indicadores.csv, presenca_colunas_indicadores.csv
python -m src.indicadores_rr             # dados/interim/indicadores_rr/{tipo}_{ano}.parquet
python -m src.leitura                    # docs/inventario.csv, presenca_colunas_escola.csv
python -m src.catalogo_microdados        # docs/catalogo_variaveis_microdados.csv, catalogo_variaveis.csv
python -m src.relatorio_catalogo         # docs/catalogo_variaveis.html (publicado como artefato)
python -m src.analise_base_longitudinal  # docs/desfechos_*.csv, ausencia_*, estrato_nome_indigena.csv
```

O inventário das planilhas (`indicadores_inep`) leva ~30 min (openpyxl
`read_only`, ~1 min por planilha de escolas) — rode em segundo plano.
`indicadores_rr` pula o que já está gravado, salvo `sobrescrever=True`.

Sempre `python -m src.<modulo>` a partir da raiz (os módulos importam
`src.config`).

**Lógica mora em `src/`, notebook só orquestra.** Um notebook com mais de ~15
linhas de lógica numa célula deve virar função em `src/`. O notebook conta a
história; o módulo faz o trabalho e é testável.

---

## 5. Papel das variáveis

Cada variável recebe exatamente um papel em `docs/dicionario_anotado.csv`.
A definição por variável da fase 1 (origem, coluna técnica por geração,
fórmula, papel) está em `docs/metodologia_variaveis.md` §4.

**Fase 1 — indicadores do INEP.** Conjunto "Core": taxas de rendimento de `t`
(aprovação, reprovação, abandono da etapa), `TDI`, `ATU`, lags e variações
anuais; `IED` só a partir de 2021 (E5). Cenário **A** (pós-fechamento) usa o
rendimento de `t`; cenário **B** (alerta antecipado) exclui aprovação,
reprovação e abandono de `t` e fica com TDI, ATU, IED e lags de `t−1`.

**Fase 2 — Censo Escolar.** Papéis dos campos da tabela Escola:

- **chave** — `CO_ENTIDADE`, `NU_ANO_CENSO`, `CO_MUNICIPIO`.
- **filtro** — define a amostra e **sai da matriz de modelagem**
  (`TP_DEPENDENCIA`, `TP_SITUACAO_FUNCIONAMENTO`, `SG_UF`,
  `IN_COMUM_MEDIO_MEDIO`, `IN_REGULAR`, `IN_ESCOLARIZACAO`). Após o filtro
  viram constantes; se entrarem como preditor, criam diferença artificial de
  distribuição entre subamostras. Atenção: `IN_ESCOLARIZACAO` só existe a
  partir de 2022 e `IN_MED` só até 2024 (P001, P012).
- **estratificacao** — `TP_LOCALIZACAO`, `TP_LOCALIZACAO_DIFERENCIADA`,
  `IN_EDUCACAO_INDIGENA`, `CO_ORGAO_REGIONAL`; derivam `ESTRATO_RR` de 4
  níveis. Usadas na avaliação de equidade. Presentes nos sete anos.
- **preditor_candidato** — organizadas em blocos conceituais: infraestrutura
  básica, dependências administrativas, dependências pedagógicas, equipamentos,
  porte, recursos humanos não docentes, gestão e participação, oferta,
  acessibilidade, contexto territorial.
- **derivada** — `DUR_ANO_LETIVO`, `ESTRATO_RR`, razões normalizadas por porte.
- **descarte** — com motivo registrado, em bloco quando possível (setor privado
  inteiro, `IN_FORMA_CONT_*`, educação infantil, `IN_EDUC_AMB_*`,
  quase-constantes).

**Teto de preditores.** O teto de 10–20 era do desenho anterior (~165 escolas
no modelo local). A fase 1 tem ~1.419 linhas com alvo no painel AF e ~980 no
EM (`docs/desfechos_cobertura.csv`), o que continua pedindo modelos tabulares
regularizados, não redes profundas. A regra permanece: **toda contagem `QT_*`
vira razão (por matrícula ou por sala) ou binária de presença** — senão mede
porte disfarçado de recurso. Exceção declarada: `QT_MAT_*` entra como *peso* e
denominador aproximado, não como preditor de recurso (D8, P018).

**Catálogo completo:** `docs/catalogo_variaveis.csv` tem as 980 variáveis
distintas dos 10 arquivos com bloco temático inferido do nome (23 blocos:
identificação, geografia, situação, dependência administrativa, localização,
local de funcionamento, infraestrutura básica, dependências físicas,
acessibilidade, equipamentos e tecnologia, profissionais não docentes,
alimentação, materiais pedagógicos, educação ambiental, organização do ensino,
educação indígena, oferta, tipo de atendimento, transporte, matrículas,
docentes, turmas), presença por arquivo e preenchimento BR/RR. O bloco é
navegação, não classificação final — esta continua sendo
`docs/dicionario_anotado.csv`. A coluna `descricao` está vazia porque o
dicionário oficial do INEP não está na pasta.

---

## 6. Espaço de decisão

Você tem acesso aos dados brutos. **Prefira verificar a perguntar** — decida
sozinho e registre em `docs/DECISOES.md` (data, decisão, evidência, alternativa
descartada) quando o assunto for:

- Encoding e separador de cada arquivo (teste utf-8 **antes** de latin-1:
  latin-1 nunca levanta erro e mascara arquivo utf-8 mal lido).
- Nomes reais das colunas, e o mapeamento entre gerações de esquema (2019–21,
  2022, 2023–24, 2025 nos microdados; 2019–20 vs 2021+ em `tx_rend`).
- Códigos de categoria efetivamente presentes em cada ano
  (`TP_DEPENDENCIA`, `TP_LOCALIZACAO_DIFERENCIADA`, etapas de ensino) e se
  mudaram ao longo do painel.
- Percentual de ausentes por coluna, calculado separadamente para RR, para o
  Brasil e por estrato.
- Quais colunas têm variância zero ou quase zero após o recorte.
- Se a Turma 2025 traz contagem de matrículas utilizável como porte.
- Estratégia de leitura conforme o tamanho do arquivo (pandas direto, `chunksize`
  ou DuckDB; openpyxl `read_only` para as planilhas).
- Nomes de funções, organização interna dos módulos, formato das mensagens de
  erro.

**Pare e pergunte** — não decida sozinho — quando o assunto for:

- Alterar a definição de qualquer desfecho, ou fixar o limiar de "alto risco".
- Incluir ou não o estrato territorial como preditor (decisão de equidade, não
  de desempenho).
- Descartar um bloco conceitual inteiro de preditores.
- Baixar arquivo novo da internet.
- Restringir o escopo a uma etapa ou rede além do que já está decidido.
- Qualquer coisa que mude o que a pesquisa afirma.

Quando encontrar algo estranho nos dados que não bloqueie o trabalho, **não
conserte em silêncio**: registre uma linha em `docs/problemas.csv` com
`id, tipo, objeto_afetado, descricao, evidencia, impacto, decisao, status`.
Tipos: `acesso`, `versionamento`, `ruptura_de_esquema`,
`ambiguidade_semantica`, `cobertura`, `qualidade_do_rotulo`, `granularidade`,
`defasagem_temporal`.

### Já decididas pelo orientador (17/09/2026) — não reabrir sem ele

Unidade escola-ano (D1); dois painéis AF e EM (D2); universo = escolas
públicas, privadas fora do modelo (D3); desfecho = taxa de abandono da etapa
em t+1 (D4); TDI vira preditor (D5); **2020–2021 ficam na base** e são
tratados por análise de sensibilidade, não excluídos (D6); partição temporal
treino 2019–22 → 2020–23, validação 2023 → 24, teste 2024 → 25 bloqueado
(D7); baselines B0–B4 obrigatórios antes de qualquer modelo (D10).

### Decisões em aberto

Bloqueiam `src/base_longitudinal.py`:

- **D8** — trazer `IN_EDUCACAO_INDIGENA`, `TP_LOCALIZACAO_DIFERENCIADA`,
  `QT_MAT_FUND_AF` e `QT_MAT_MED` do Censo já na fase 1 (estrato + peso).
  Sem as duas primeiras a avaliação de equidade do §1 é impossível; sem as
  duas últimas P018 fica sem tratamento. Precisa do OK da pesquisadora e do
  orientador.
- **D9** — usar `ATU_FUN_TOTAL` em vez de `ATU_FUN_AF` e derivar
  `IN_MULTISSERIADA` (P016): a ausência de ATU por etapa é estrutural e
  concentrada em escolas rurais e indígenas.
- **P017** — tirar do universo as escolas só de educação infantil (o ATU as
  inclui: 176 em 2019), que nunca terão desfecho de abandono.
- Limiar `p` de "alto risco" para `ALTO_*_T1` (quantil 75, 80, ou um limite
  operacional).
- **D11** — estender a série para 2007–2018 (muda o desenho de validação e
  exige baixar arquivos novos).

Bloqueiam a fase 2 (`filtros.py`):

- Definição de "oferta de EM" em 2025: (a) só `IN_COMUM_MEDIO_MEDIO` (162
  escolas) ou (b) união das `IN_COMUM_MEDIO_*` (173); referência 2024 com
  `IN_MED`: 168. Ver DECISOES.md 2026-09-09 e P001.
- Substituto de `IN_ESCOLARIZACAO` para 2019–2021 (P012) e de `IN_NOTURNO`
  para 2025 (P002).

---

## 7. Convenções de código

- Python 3.11+, ambiente virtual em `.venv`, dependências em
  `requirements.txt`. Não instale pacote fora da lista sem avisar (não há
  leitor de PDF na lista — os PDFs de `doc-censo/` são lidos à mão).
- Bibliotecas em uso: pandas, numpy, pyarrow, openpyxl, odfpy, duckdb, tqdm,
  matplotlib, pandera, ruff. scikit-learn e scipy só a partir da fase de
  modelagem.
- Caminhos com `pathlib`, nunca string concatenada. Em SQL do DuckDB use
  `.as_posix()` — barra invertida do Windows vira escape e o arquivo não é
  encontrado. DuckDB não aceita `encoding='cp1252'`; use `'latin-1'` só para
  contagens (difere apenas em 0x80–0x9F).
- Mensagem de erro diz o que falta e o que existe. `caminho(2023, "turma")`
  responde que a tabela não foi baixada e lista as disponíveis;
  `caminho_indicador("HAD", 2023, "escolas")` lista os arquivos de HAD que
  existem — nunca `FileNotFoundError` cru.
- Escrita em Parquet como formato canônico (preserva tipos nullable), com cópia
  CSV `sep=";"` para conferência humana.
- Sem `print` solto em `src/`; use `logging`. `print` só em notebook.
- `ruff` limpo antes do commit.

**Commits:** Conventional Commits com descrição em português, verbo no presente
da 3ª pessoa, sem ponto final, até ~72 caracteres.
Ex.: `feat: Adiciona funil de recorte com contagem por ano`.
Um commit por alteração coerente — se a descrição precisa de "e", são dois.

---

## 8. Critérios de aceite da fase atual (fase 1 — regerar a base longitudinal)

Feito em 2026-09-15: `docs/inventario.csv`, `docs/presenca_colunas_escola.csv`,
`docs/inventario_indicadores.csv`, `docs/presenca_colunas_indicadores.csv`,
`dados/MANIFEST.csv` completo, indicadores extraídos e conferidos,
`docs/catalogo_variaveis*`.

Feito em 2026-09-20: `src/indicadores_rr.py` (recorte RR em Parquet),
`src/analise_base_longitudinal.py` com `docs/desfechos_*.csv`,
`docs/metodologia_variaveis.md`, P014 resolvido, P016–P018 registrados.

A fase atual se considera pronta quando:

1. `src/base_longitudinal.py` regera a base a partir de
   `dados/interim/indicadores_rr/`: harmonização de nomes por geração
   (posicional, §2.2), união com `validate="1:1"`, derivadas `*_LAG1`,
   `*_DELTA1` e `*_T1`.
2. A base regerada bate com `dados/Processados/base_longitudinal_...csv`
   coluna a coluna nas 59 variáveis comuns — toda diferença registrada em
   `docs/problemas.csv`.
3. As validações de `validacao_base_longitudinal.json` (§2.3) rodam por código
   e passam, por `assert`.
4. Existe `dados/processado/base_longitudinal_rr_2019_2025.parquet` (+ CSV
   `sep=";"`), chave `ANO + CO_ENTIDADE` única, com hash em
   `dados/MANIFEST.csv`.
5. `docs/desfechos.csv` (Tabela C) e `docs/dicionario_anotado.csv` (Tabela B)
   são gerados a partir de `docs/metodologia_variaveis.md` §5 e §4.
6. `docs/DECISOES.md` tem entradas datadas para D1–D7 (orientador, 17/09/2026)
   e para o que for aprovado de D8–D9.
7. `notebooks/01_leitura_e_recorte.ipynb` roda de ponta a ponta, sem erro, com
   o kernel reiniciado.
8. Nenhum arquivo de `dados/bruto/` ou `dados/Processados/` foi modificado;
   `git status` não mostra nenhum CSV de microdado, zip ou planilha.
