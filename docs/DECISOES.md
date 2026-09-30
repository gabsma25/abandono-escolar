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

---

## 2026-09-15 — Organização dos arquivos de dados/bruto/brutos-inep/ (SUBSTITUÍDA pela entrada seguinte)

**Decisão:** os 83 `.zip` de indicadores do INEP são **copiados**, nunca
movidos, para `dados/interim/brutos_inep_organizado/{TIPO}/{ANO}/`, mantendo o
nome de arquivo original. Implementado em `src/organizar_brutos_inep.py`.

**Evidência:** `dados/bruto/` é somente leitura (regra 1) — o nome original é
procedência. Reorganizar a pasta original destruiria essa informação. Os 83
originais permanecem intactos após a execução; `git status` não mostra nenhum
arquivo de dados (toda a pasta `dados/` está fora do git, exceto `MANIFEST.csv`).

Duas gerações de nomenclatura foram detectadas e tratadas por regex, não por
lista fixa: `{TIPO}_{ANO}_{NIVEL}.zip` (ATU, HAD, IED, TDI) e
`tx_rend_{nivel}_{ano}.zip`. O nível (brasil_regioes_ufs / municipios /
escolas) fica no nome do arquivo, não na estrutura de pastas, porque a chave de
navegação da pesquisa é tipo de indicador × ano.

Duplicatas com sufixo ` (N)` são reconhecidas pelo nome-base e deduplicadas por
sha256: o arquivo sem sufixo é a cópia canônica, o duplicado é registrado no
manifesto mas não copiado de novo (ver P005).

**Destino em `interim/`:** a seção 4 do CLAUDE.md descreve `interim/` como
"recortes intermediários (Parquet)". A cópia organizada não é Parquet, mas é
material derivado e fora do git, que é a propriedade que importa aqui. A
alternativa `dados/bruto_organizado/` foi descartada por sugerir falsamente
que é fonte primária.

**Manifesto:** `dados/interim/brutos_inep_organizado/_manifesto.csv` registra
tipo, ano, nível, nome original, sha256, destino e duplicata. Não substitui
`dados/MANIFEST.csv`, que continua sendo o hash dos arquivos originais.

---

## 2026-09-15 — Extração dos .zip de indicadores (substitui a cópia organizada)

**Decisão:** os 83 `.zip` de `dados/bruto/brutos-inep/` são **extraídos** para
`dados/interim/brutos_inep_extraido/{tipo}/{ano}/` por
`src/extrair_brutos_inep.py`. De cada zip saem só o `.xlsx` e o `md5_*.txt`
do INEP; o `.ods` e o lixo de sistema (`Thumbs.db`, `.~lock.*#`) ficam dentro
do zip. O md5 de cada `.xlsx` extraído é conferido contra o `.txt`. A pasta
interna do zip é achatada (o nome do arquivo já carrega tipo, nível e ano). A
cópia organizada dos zips (`brutos_inep_organizado/`, 1,8 GB de duplicatas
bit-a-bit) foi removida; `src/organizar_brutos_inep.py` foi substituído.

**Evidência:** todos os 83 zips têm a mesma estrutura — uma pasta com o mesmo
arquivo em `.xlsx` e `.ods`, um `md5_*.txt` no formato do `md5sum` cobrindo os
dois, e em 5 zips lixo de sistema. Total descompactado: 1,9 GB; só `.xlsx`:
1,1 GB. 82 planilhas extraídas (1 zip é duplicata bit-a-bit, P005); md5
confere em 77, falha em 4 (P007), sem entrada em 1 (P008).

**Alternativa descartada:** extrair também o `.ods` — é a mesma tabela em
segundo formato; manter dois arquivos por indicador convida a ler o errado.
Se um `.xlsx` se mostrar corrompido, o `.ods` continua disponível no zip.
Copiar o zip para `interim/` antes de extrair — redundante com o original
imutável em `bruto/`.

---

## 2026-09-15 — Leitura das planilhas de indicadores: linha de nomes técnicos é detectada

**Decisão:** `src/indicadores_inep.py` localiza a linha de nomes técnicos
(1ª célula `NU_ANO_CENSO`/`Ano`/`ano`, seguida imediatamente por uma linha
cujo 1º valor é o ano numérico) em vez de fixar `skiprows`. Células vazias
no meio dessa linha viram `_SEM_NOME_{posição}` em vez de serem descartadas.

**Evidência:** a linha varia — 9 em tx_rend/TDI/ATU/HAD, 11 em IED — e os
nomes humanos das linhas 6–8 têm acentuação, espaços e notas de rodapé
(`esforço3`). Em `tx_rend_brasil_regioes_ufs_2019/2020` a coluna da unidade
geográfica não tem nome técnico (P010); descartar a célula vazia deslocaria
todas as colunas seguintes em uma posição.

**Alternativa descartada:** `pd.read_excel(header=8)` fixo — quebra no IED e
silencia o desalinhamento de 2019/2020.

---

## 2026-09-15 — Microdados 2019–2021 entram no dicionário ARQUIVOS

**Decisão:** `(2019|2020|2021, "escola")` apontam para
`microdados_ed_basica_{ano}.csv`; o de 2020 tem extensão `.CSV` em maiúsculas
e o nome é preservado assim (regra 1). Encoding `cp1252`, separador `;`,
como nos demais.

**Evidência:** `docs/inventario.csv` (gerado por `src/leitura.py`): nos três
arquivos o teste utf-8 falha na posição 6923 (byte `0xf4` = `ô`); 370 colunas
idênticas nos três anos; 228.521 / 224.229 / 221.140 linhas; RR = 915 / 919 /
941. `docs/presenca_colunas_escola.csv`: as 370 colunas de 2019–2021 são um
subconjunto estrito das 385 de 2022 — nenhuma coluna existe só em 2019–2021.

**Alternativa descartada:** renomear `2020.CSV` para `.csv` — viola a regra 1
e o Windows resolve o nome sem distinguir caixa, mas o `MANIFEST.csv` e o git
distinguiriam.

---

## 2026-09-15 — MANIFEST.csv passa a cobrir tudo em dados/bruto/

**Decisão:** `src/manifesto.py` regenera `dados/MANIFEST.csv` com sha256 de
todos os arquivos de `dados/bruto/` (10 microdados, 83 zips, 2 PDFs). A
coluna `arquivo` é o caminho relativo a `bruto/`; `tabela` dos zips é
`indicador_{tipo}_{nivel}`. Datas de download já registradas são preservadas;
para arquivo novo usa-se a data de modificação no disco.

**Evidência:** os 7 hashes de 2026-09-09 permanecem idênticos após a
regeneração. Antes o manifesto não cobria os zips (nem a duplicata P005).

---

## 2026-09-15 — Catálogo completo de variáveis (todas, não só as candidatas)

**Decisão:** a pesquisadora pediu para apresentar **todas** as variáveis de
cada tabela, para avaliar os dados e propor um novo projeto de predição
comparando métodos. `src/catalogo_microdados.py` gera
`docs/catalogo_variaveis_microdados.csv` (coluna × arquivo) e
`docs/catalogo_variaveis.csv` (coluna consolidada), com prefixo, bloco
temático inferido do nome, preenchimento Brasil/RR, distintos e exemplos em
RR. `src/relatorio_catalogo.py` monta `docs/catalogo_variaveis.html` a partir
dos CSVs. O teto de 10–20 preditores da seção 5 do CLAUDE.md passa a ser uma
diretriz do desenho anterior, não uma restrição do catálogo.

**Evidência:** 980 nomes de coluna distintos nos 10 arquivos; 3.284 pares
coluna × arquivo; 23 blocos temáticos, nenhuma coluna sem bloco.
Preenchimento = campo não vazio no CSV (DuckDB lê vazio como NULL).

**Alternativa descartada:** usar o dicionário oficial do INEP para as
descrições — não está na pasta (`Leia-me-2021.pdf` não é legível com as
bibliotecas da lista). A coluna `descricao` do catálogo fica vazia até que o
dicionário seja baixado (decisão da pesquisadora).

---

## 2026-09-15 — Cabeçalho humano das planilhas de indicadores vira descrição

**Decisão:** `src/indicadores_inep.py` passa a capturar o bloco de cabeçalho
humano (linhas entre 'Ano' e a linha técnica) e monta uma descrição por
coluna unindo os rótulos com ' › ', preenchendo células mescladas para a
direita sem atravessar a fronteira do grupo definido nas linhas de cima.
Planilha sem linha técnica (`tx_rend_municipios_2019`) recebe nomes
sintéticos `_SEM_NOME_n` e mantém a descrição.

**Evidência:** `tx_rend_municipios_2019.xlsx` tem cabeçalho humano nas linhas
6–8, linha 9 vazia e dados a partir da 10 — a regra anterior (linha técnica
obrigatória) abortava o inventário inteiro. A descrição expôs P014.

**Alternativa descartada:** ignorar o cabeçalho humano — perderia a única
fonte de significado das colunas e a evidência de P010/P014.

---

## 2026-09-30 — dados/ organizada por estágio do dado

**Decisão:** o estágio define a pasta: `origem/` (compactados como vieram da
fonte), `bruto/` (extraído, nome original do INEP), `interim/`, `processado/`
e `externo/` (dados de terceiros). Os zips de microdados, que estavam fora do
projeto (`~/Downloads`, OneDrive), foram movidos para `origem/censo/`; os de
indicadores de `bruto/brutos-inep/` para `origem/indicadores/`; as planilhas
extraídas de `interim/brutos_inep_extraido/` para `bruto/indicadores/`; a base
do orientador de `Processados/` para `externo/base_longitudinal_v1/`. Os 10
CSVs de microdados, que não estavam no disco, foram extraídos dos zips.
Migração por `src/migracao_estrutura.py`, log em
`dados/migracao_estrutura_log.csv`.

**Evidência:** sha256 conferido antes e depois de cada um dos 283 movimentos,
nenhuma divergência; os 10 CSVs extraídos conferem com o manifesto anterior e
com o md5 do INEP. As 94 linhas comuns aos dois manifestos mantêm sha256 e
data. 84 cópias idênticas (82 em `~/Downloads` e as duas
`TDI_2025_MUNICIPIOS (1).zip`, P005) foram para a Lixeira do Windows, não
apagadas.

**Alternativa descartada:** manter zips de indicadores em `bruto/` e
extraídos em `interim/` — o mesmo estágio teria tratamento diferente para
censo e indicadores, e `Processados/` continuaria colidindo com `processado/`.

---

## 2026-09-30 — Manifesto cobre origem, bruto e externo

**Decisão:** `dados/MANIFEST.csv` ganha as colunas `estagio` e `origem`
(`inep` / `orientador`); `arquivo` passa a ser relativo a `dados/`. Registra
também o sha256 dos zips — antes só havia o dos CSVs extraídos, o que impedia
validar um zip antes de extraí-lo — e dos `.xlsx`/`md5_*.txt` de
`bruto/indicadores/` (mesmo estágio, mesmo tratamento).

**Evidência:** 271 linhas após a migração (91 origem, 174 bruto, 6 externo);
334 após incluir HAD/IED (112, 216, 6).

**Alternativa descartada:** manifesto enxuto só com zips e CSVs — deixaria as
planilhas de indicadores, que são o insumo da fase 1, sem hash de referência.

---

## 2026-09-30 — Base longitudinal v1.0 como dependência externa documentada

**Decisão:** a v1.0 do orientador fica em `dados/externo/base_longitudinal_v1/`
com hash no manifesto (`estagio=externo`, `origem=orientador`); o bootstrap
verifica e avisa se faltar, sem falhar. Quando `src/base_longitudinal.py`
estiver pronto e a comparação do critério 2 (§8 do CLAUDE.md) registrada,
reavalia-se se ela continua necessária.

**Evidência:** a base não é obtenível do INEP e o script que a gerou não veio
junto; `manifesto_fontes_longitudinal.csv` do orientador não traz hash das
fontes.

**Alternativa descartada:** versionar a v1.0 no git (viola a regra 2) ou
depositá-la com DOI — as duas exigem consentimento do orientador, e a
pesquisadora prefere não abrir o assunto antes da comparação.

---

## 2026-09-30 — Regra 1: pastas imutáveis só recebem arquivo novo e conferido

**Decisão:** `origem/`, `bruto/` e `externo/` são somente leitura; a exceção
é descrita por comportamento, não por nome de módulo: criar o que não existe,
via temporário, com hash conferido. Arquivo presente que confere não é tocado
(nem o mtime); divergente é erro; o que não confere vai para
`cache_download/divergente/`. Regravar exige `--sobrescrever` (mesma flag em
`aquisicao`, `extrair_brutos_inep` e `indicadores_rr`). Implementado em
`src/integridade.py`. Referência de hash: sha256 do manifesto; para arquivo
fora dele, md5 do INEP; sem nenhum dos dois, CRC do zip.

**Evidência:** o extrator de indicadores regravava a cada execução todos os
arquivos de `bruto/indicadores/` (proposta de linha P021). Seis planilhas
nunca conferem com o md5 publicado pelo INEP (P007, P020) — com o md5 do INEP
como única referência, o extrator falharia para sempre em
`ATU_ESCOLAS_2022.xlsx`, que entra no painel. Teste: rodar o extrator duas
vezes não altera mtime em `bruto/indicadores/` (tests/test_extrair_brutos_inep.py).

**Alternativa descartada:** listar na regra os módulos autorizados — a regra
teria de ser emendada a cada módulo novo e não seria testável; e usar o md5 do
INEP como referência única.

---

## 2026-09-30 — Relação de extração sai de bruto/ para docs/

**Decisão:** o `_manifesto.csv` que o extrator gravava em
`bruto/indicadores/` passa a `docs/extracao_indicadores.csv` (caminhos
relativos a `dados/`). `docs/relacao_indicadores_extraidos.csv` foi removido:
era subconjunto dele (só `.xlsx`, mais tamanho) e estava desatualizado
(apontava para `interim/brutos_inep_extraido/`); o catálogo HTML monta essa
relação em memória.

**Evidência:** o arquivo era regravado a cada execução dentro de pasta
imutável, e o critério 8 do §8 ficava autocontraditório. Conteúdo conferido
antes da remoção: 319 linhas idênticas, exceto o prefixo `bruto/indicadores/`.

**Alternativa descartada:** manter em `bruto/` com prefixo `_` — exceção
nominal para o caso que incomoda; arquivo gerado em pasta imutável se move,
não se renomeia.

---

## 2026-09-30 — O que se obtém do INEP é exatamente o manifesto

**Decisão:** a aquisição (cópia local ou `--baixar`) só obtém arquivos
listados em `dados/MANIFEST.csv`; o que as páginas do INEP publicam além disso
fica fora por decisão, não por omissão. Um clone com `--baixar` chega, portanto,
aos mesmos 110 zips (7 de microdados + 103 de indicadores) que a máquina de
referência. Fora do projeto:

- microdados do Censo 1995–2018 (24 zips) — fora da janela 2019–2025 (D11,
  extensão para 2007–2018, em aberto);
- `ATU_2025_MUNICIPIOS.zip` e `tx_rend_brasil_regioes_ufs_2025.zip` — níveis
  município e Brasil/UF, não usados no painel por escola; não autorizados
  (P019);
- abas de indicadores anteriores a 2019 e os demais indicadores do índice
  (Adequação da Formação Docente, Complexidade de Gestão da Escola,
  Regularidade do Corpo Docente, Nível Socioeconômico, Taxas de Transição,
  entre outros) — fora do desenho da fase 1.

**Evidência:** descoberta sobre a captura de 2026-09-30 (`python -m
src.aquisicao --descobrir-do-cache 2026-09-30`, restrita a 2019–2025 nos cinco
indicadores): 136 links, 110 no manifesto, 26 fora (24 + 2 acima).
`src/fontes_inep.csv`, manifesto e disco têm os mesmos 110 nomes.

**Alternativa descartada:** baixar tudo o que a raspagem acha — o conjunto de
dados passaria a depender do dia da raspagem, e o manifesto deixaria de ser a
especificação.

---

## 2026-09-30 — Infraestrutura encerrada até a fase 1 entregar resultado

**Decisão:** nenhum módulo de apoio, teste ou refinamento de tooling novo até
`src/base_longitudinal.py` e a comparação com a v1.0 estarem prontos.
Melhorias identificadas entram aqui como "adiado deliberadamente".

**Adiado deliberadamente:** (nenhuma até esta data)

---

## 2026-09-30 — Regeração da base longitudinal e comparação com a v1.0

**Decisão:** `src/base_longitudinal.py` regera a base com as regras
verificadas contra a v1.0 antes de escrever código: universo = união das
chaves das quatro fontes; identidade = primeiro valor não nulo na ordem
tx_rend → TDI → ATU → IED; `DISP_*` sobre as colunas mantidas de cada fonte;
`ANO_ALVO = ANO + 1` se a escola existe em t+1; derivadas temporais por
junção explícita em `ANO ± 1` (não `shift()`), ausente em qualquer ponta dá
ausente. O mapeamento posicional de tx_rend 2019–2020 é conferido contra o
rótulo humano de cada uma das 63 posições (`docs/presenca_colunas_indicadores.csv`)
antes de ser usado.

Comparação (`docs/comparacao_base_v1.csv`, com o sha256 da v1.0 usada): a
ausência é comparada antes dos valores (NaN ≠ NaN tornaria idênticas colunas
divergentes e vice-versa). Tolerância **absoluta** de 1e-9 só nas colunas que
passaram por aritmética (`IED_*_ALTO`, `*_DELTA1`) — as grandezas são
limitadas (0–100), então tolerância relativa seria frouxa perto de 100 e
rígida perto de 0. Diferença dentro da tolerância é contada e reportada
(`max_diferenca_abs`), não omitida. A mesma tolerância vale no limite
[0, 100] das colunas calculadas: 76,9 + 15,4 + 7,7 = 100.00000000000001.

**Evidência:** 50 colunas idênticas e 8 idênticas na tolerância (máx.
1,4e-14); nenhuma divergência de ausência, de valor ou de universo. A
comparação acusou todas as diferenças plantadas num teste manual (linha a
menos, ausência trocada, +0,1 em taxa copiada, +1e-12 e +1e-6 em colunas
calculadas, nome trocado). Duas execuções geram os mesmos bytes.

**Alternativa descartada:** arredondar as somas para bater com a v1.0 —
mudaria o cálculo para igualar a referência em vez de explicar a diferença.

---

## 2026-09-30 — Papel das variáveis da fase 1 (Tabela B)

**Decisão:** vocabulário de papéis `chave`, `descrição`, `filtro`, `estrato`,
`controle de ausência`, `preditor`, `desfecho`, `peso`; exatamente um por
variável; "derivada" deixa de ser papel e fica na origem; limite de uso em
coluna própria (`restricao`). `DEPENDENCIA` é **estrato** (o filtro do
universo, D3, é `REDE_PUBLICA`; assim as redes públicas podem ser
comparadas). `DISP_*` são **controle de ausência**. O papel é escrito nas
tabelas do §4 da metodologia (colunas Papel e Restrição em 4.1–4.7 e tabela
nova em 4.6 com as 12 derivadas temporais), de onde
`python -m src.tabelas_metodologia` gera `docs/dicionario_anotado.csv`.
Decisões da pesquisadora em 2026-09-30.

**Evidência:** antes, só 4.1 e 4.7 tinham papel em tabela; 32 variáveis
(4.2–4.5) tinham papel só no texto ou em lugar nenhum (ATU), as 12 derivadas
temporais não tinham tabela, e havia "filtro + estrato" em `DEPENDENCIA`.
Resultado: 59 variáveis vigentes = as 59 colunas da base regerada; 7
propostas (`ATU_MULTI`, `IN_MULTISSERIADA` e as cinco da D8).

**Alternativa descartada:** lista de papéis no código — o papel é decisão de
método e mora no documento de método.
