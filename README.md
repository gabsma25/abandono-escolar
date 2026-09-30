# Risco de abandono escolar em Roraima

Projeto de pesquisa de iniciação científica (PIBIC/UERR, Edital 35/2026) e
artigo da disciplina de mineração de dados, orientado pelo Prof. Bruno Cesar
Barreto Figueiredo.

**Pergunta:** com os indicadores educacionais de uma escola de Roraima no ano
`t`, é possível estimar a taxa de abandono esperada no ano `t+1` — nos anos
finais do ensino fundamental e no ensino médio — para apoiar ações preventivas
de gestão? A unidade de análise é a escola-ano; o projeto **não prevê nada
sobre alunos individuais**, e o resultado se destina a priorizar escolas para
diagnóstico, nunca a ranqueá-las ou puni-las.

Este repositório contém o código que obtém os dados públicos do INEP, confere
sua integridade, extrai o recorte de Roraima e gera as tabelas descritivas. O
método está em [`docs/metodologia_variaveis.md`](docs/metodologia_variaveis.md);
as regras de trabalho, em [`CLAUDE.md`](CLAUDE.md).

## Pré-requisitos

- **Python 3.11 ou mais recente** (desenvolvido com 3.12).
- **~6 GB livres** para `dados/` (2,9 GB de zips do INEP e 3,0 GB extraídos).
- **Tempo:** ~40 min num notebook com SSD (36 min medidos num clone limpo em
  30/09/2026), a maior parte no inventário e no recorte das planilhas de
  indicadores; mais o download de 2,9 GB, se os zips não estiverem no disco.
- Git.

## Passo a passo

```bash
git clone <url-deste-repositorio> abandono-escolar
cd abandono-escolar
python -m venv .venv
.venv\Scripts\activate            # Windows (no Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
```

O que o git traz de `dados/` é só `dados/MANIFEST.csv`: a lista, com sha256,
de todo arquivo de dados que o projeto usa. O bootstrap obtém esses arquivos e
recria o resto:

```bash
# Se você já tem os zips do INEP em alguma pasta (ela não é alterada):
python -m src.bootstrap --origem-local C:\caminho\para\os\zips

# Se não tem, baixe do INEP o que faltar (só o que está no manifesto):
python -m src.bootstrap --baixar

# Só obter, extrair e conferir, sem os inventários (~3 min + download):
python -m src.bootstrap --baixar --so-aquisicao
```

Antes de começar, o bootstrap imprime a estimativa de espaço e tempo. Sem
`--baixar`, ele não faz nenhuma requisição de rede. Rodar de novo é seguro:
o que já existe e confere não é refeito nem tocado.

Ordem das etapas: aquisição dos zips → extração → conferência de cada arquivo
contra o sha256 do manifesto → inventários e catálogo de variáveis (`docs/`) →
recorte de Roraima (`dados/interim/`) → análise da base do orientador (se
presente, ver [Limitações](#limitações-conhecidas)). No fim ele confere que
`git status docs/` está limpo: os CSVs de `docs/` são versionados, e qualquer
diferença significa que o clone não reproduziu o estado registrado.

Se um arquivo baixado não conferir com o manifesto — o INEP revisa arquivos
depois de publicá-los —, ele vai para `dados/cache_download/divergente/` e o
bootstrap para com uma mensagem dizendo qual arquivo, o hash esperado e o
obtido. Nada divergente entra nas pastas de dados.

Testes (sem rede, sem tocar em `dados/`): `python -m pytest`.

## O que cada pasta contém

```
dados/                       fora do git, exceto MANIFEST.csv
  origem/                    zips como vieram do INEP — somente leitura
    censo/                   microdados do Censo Escolar 2019–2025 (7 zips)
    indicadores/             indicadores educacionais (103 zips)
    doc/                     documentação que acompanha os microdados
  bruto/                     extraído dos zips, com o nome original — somente leitura
    censo/                   tabela de escolas por ano (+ turma/matrícula/docente 2025)
    indicadores/             planilhas .xlsx por indicador e ano
  interim/indicadores_rr/    recorte de Roraima das planilhas de escolas (Parquet)
  processado/                saída final deste projeto
  externo/                   dados de terceiros, não obteníveis do INEP — somente leitura
  cache_download/            downloads em andamento, divergentes, páginas capturadas
  MANIFEST.csv               estágio, origem, arquivo, sha256 e data de cada arquivo
docs/                        tabelas geradas por código, método, decisões e problemas
src/                         módulos Python (python -m src.<modulo>)
tests/                       testes e páginas do INEP capturadas para eles
```

`docs/DECISOES.md` registra cada decisão de método ou de dados, com evidência;
`docs/problemas.csv`, cada problema encontrado nos dados.

## Fontes

Os dados são públicos e foram obtidos do Instituto Nacional de Estudos e
Pesquisas Educacionais Anísio Teixeira (Inep). As datas de acesso de cada
arquivo estão em `dados/MANIFEST.csv` (coluna `data_download`).

> BRASIL. Instituto Nacional de Estudos e Pesquisas Educacionais Anísio
> Teixeira (Inep). **Microdados do Censo Escolar da Educação Básica
> 2019–2025.** Brasília: Inep. Disponível em:
> https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-escolar.
> Acesso em: 2 a 15 set. 2026.

> BRASIL. Instituto Nacional de Estudos e Pesquisas Educacionais Anísio
> Teixeira (Inep). **Indicadores Educacionais: Taxas de Rendimento, Taxas de
> Distorção Idade-série, Média de Alunos por Turma, Esforço Docente e Média de
> Horas-aula diária, 2019–2025.** Brasília: Inep. Disponível em:
> https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/indicadores-educacionais.
> Acesso em: 9 a 17 set. 2026.

A base longitudinal v1.0 (`dados/externo/base_longitudinal_v1/`) foi montada
e entregue pelo orientador em 17/09/2026 a partir desses indicadores.

## Limitações conhecidas

- **Defasagem do desfecho.** A taxa de abandono de um ano depende da situação
  final de cada aluno, informada na segunda etapa do Censo Escolar, coletada
  no ano seguinte. Por isso o abandono de `t+1` só é conhecido bem depois do
  fim de `t+1`, e o modelo sempre trabalha com o último ano já publicado.
- **Abandono ≠ evasão.** Abandono é o aluno que deixa de frequentar a escola
  durante o ano letivo e existe por escola. Evasão é o aluno que não se
  matricula no ano seguinte e só é publicada de forma agregada. Este projeto
  trata de abandono.
- **O INEP revisa arquivos depois da publicação, nem sempre com aviso.** O zip
  de microdados de 2024 disponível em setembro de 2026 é uma versão revisada
  em julho de 2026, sem nota na página; o de 2025 é a "v2". Em seis planilhas
  de indicadores, o md5 publicado pelo próprio INEP não confere com o arquivo
  do zip (`docs/problemas.csv`, P007 e P020). Por isso a referência é o sha256
  do `dados/MANIFEST.csv`, que registra exatamente o que a pesquisa usou:
  rebaixar pode trazer outra versão, e o bootstrap acusa isso em vez de
  aceitá-la em silêncio.
- **A base do orientador não é reproduzível a partir deste repositório — ainda.**
  `dados/externo/base_longitudinal_v1/` foi entregue pronta, e o script que a
  gerou não veio junto. Ela não pode ser obtida do INEP; quem clona precisa
  pedi-la ao orientador (o sha256 esperado de cada um dos seis arquivos está
  no manifesto, com `estagio=externo`). Sem ela, o bootstrap roda tudo o mais
  e só pula a análise descritiva dela, com aviso. Reproduzi-la em código
  (`src/base_longitudinal.py`) é a tarefa da fase atual; quando a comparação
  com a v1.0 estiver registrada, reavalia-se se ela continua necessária.
- **Dois arquivos publicados pelo INEP não estão no projeto:**
  `ATU_2025_MUNICIPIOS.zip` e `tx_rend_brasil_regioes_ufs_2025.zip`. São de
  nível município e Brasil/UF e não afetam o painel por escola; a ausência é
  deliberada, não um erro.
- **Os indicadores de horas-aula (HAD) e de esforço docente (IED) de 2019–2020
  estão nos dados mas ainda não no desenho** — incluí-los é decisão pendente
  com o orientador (P019).
