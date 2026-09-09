# Log de decisões

Formato: `## YYYY-MM-DD — Título`
Campos: Decisão · Evidência · Alternativa descartada

---

## 2026-09-09 — Encoding de todos os arquivos brutos

**Decisão:** `cp1252` para todos os 7 arquivos.

**Evidência:** Byte `0xf4` na posição 7303 de `microdados_ed_basica_2022.csv`
(e posição 6267 de `Tabela_Escola_2025_V2.csv`) corresponde a `ô` em latin-1/cp1252.
Teste de decodificação como UTF-8 levanta `UnicodeDecodeError` na mesma posição.
chardet retornou confiança 0,00 (arquivo quase todo ASCII, não discriminável).

**Alternativa descartada:** `latin-1` — decodifica os mesmos bytes, mas não
trata corretamente a faixa 0x80–0x9F (caracteres de controle Windows);
`cp1252` é o superconjunto correto para arquivos gerados em Windows.

---

## 2026-09-09 — Separador dos arquivos brutos

**Decisão:** ponto-e-vírgula (`;`) para todos os 7 arquivos.

**Evidência:** Cabeçalho de cada arquivo contém `;` como delimitador;
contagem de `;` no primeiro registro supera contagem de `,` em todos.

**Alternativa descartada:** vírgula — aparece dentro de campos (nomes de
escola), não como delimitador.

---

## 2026-09-09 — Granularidade das tabelas Turma/Matrícula/Docente 2025

**Decisão:** `agregacao.py` fará **merge** (seleção de colunas + join),
não GROUP BY.

**Evidência:** `COUNT(*) = COUNT(DISTINCT CO_ENTIDADE)` nas três tabelas
(turma: 178.772; matrícula: 178.766; docente: 178.772). Nenhuma coluna de
identificador individual de aluno, docente ou turma encontrada.

**Alternativa descartada:** GROUP BY — desnecessário pois os arquivos já
estão agregados ao nível escola pelo INEP.

---

## 2026-09-09 — Proxy para IN_NOTURNO em 2025

**Decisão:** PENDENTE — registrado para decisão futura.

**Evidência:** `IN_NOTURNO` foi removido da tabela Escola em 2025.
`QT_TUR_BAS_N > 0` em `Tabela_Turma_2025_V2` captura 63 escolas
RR/estadual/EM vs. 64 com `IN_NOTURNO = 1` em 2024 (diferença de 1 escola).
`QT_TUR_MED_N > 0` captura apenas 36 (subestima escolas mistas).

**Alternativa descartada (provisória):** `QT_TUR_MED_N > 0` — captura só
turmas de EM noturnas, perde escolas com turmas noturnas de outras
modalidades que também oferecem EM.

**Status:** aguarda confirmação de qual coluna proxy usar (ver problemas.csv).

---

## 2026-09-09 — Definição de "oferta de ensino médio" entre gerações

**Decisão:** AGUARDANDO ESCOLHA DO PESQUISADOR.

**Evidência (2025/RR/ativa/pública):**
- Base total: 864 escolas
- (a) `IN_COMUM_MEDIO_MEDIO = 1` apenas: **162 escolas**
- (b) união `IN_COMUM_MEDIO_MEDIO OR IN_COMUM_MEDIO_INTEGRADO
  OR IN_COMUM_MEDIO_NORMAL OR IN_COMUM_MEDIO_FIC`: **173 escolas**
- Referência 2024 com `IN_MED = 1`: **168 escolas**

As 11 escolas em (b)–(a): 4× IFRR (técnico integrado), 1× UFRR
Agrotécnica, 1× Escola de Formação de Professores (magistério/normal),
4× estaduais com só FIC, 1× estadual integrado+FIC.

**Implicação:** opção (a) exclui EM integrado e magistério; opção (b)
inclui. Afeta comparabilidade com 2022–2024 (IN_MED não discriminava
modalidade).

**Alternativa descartada:** não registrada até decisão do pesquisador.
