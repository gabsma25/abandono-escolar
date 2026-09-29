# Base Longitudinal - Abandono Escolar em Roraima

**Versão:** 1.0  
**Data de consolidação:** 17/09/2026  
**Unidade de observação:** escola-ano  
**Período:** 2019-2025  
**Chave longitudinal principal:** `CO_ENTIDADE` (código INEP da escola)

## 1. Objetivo

Esta pasta contém a base longitudinal construída para apoiar estudos de **predição e prevenção do abandono escolar em Roraima**. A base organiza, em uma única estrutura temporal, indicadores educacionais publicados pelo INEP em nível de escola e cria variáveis defasadas e de ano seguinte para permitir experimentos preditivos sem mistura indevida entre passado e futuro.

A versão atual foi desenhada principalmente para responder à pergunta:

> Com informações consolidadas de uma escola no ano **t**, é possível estimar seu risco ou a intensidade esperada de abandono no ano **t+1**, de modo a apoiar ações preventivas de gestão educacional?

A base é **agregada por escola**. Portanto, ela não identifica nem prediz o abandono de um estudante individual. O uso adequado é a priorização de escolas, etapas de ensino e contextos que mereçam atenção preventiva.

## 2. Arquivos principais

### Pasta `Processados`

- `base_longitudinal_abandono_rr_2019_2025.csv` - base analítica principal, com uma linha por escola e ano.
- `dicionario_base_longitudinal.csv` - descrição de todas as variáveis da base.
- `resumo_cobertura_longitudinal.csv` - cobertura anual das fontes e dos desfechos.
- `validacao_base_longitudinal.json` - resultados das verificações automáticas de integridade e consistência.
- `log_fontes_longitudinal.json` - registro das fontes processadas por indicador e ano.
- `manifesto_fontes_longitudinal.csv` - relação dos arquivos esperados/utilizados e sua organização de origem.

### Pasta `Documentacao`

- `README.md` - este documento.
- `Proposta_Detalhada_Analise_Preditiva_Abandono_Escolar_Roraima.pdf` - plano metodológico detalhado para a análise estatística e preditiva.

## 3. Fontes consolidadas

A base utiliza arquivos de indicadores educacionais do INEP existentes na pasta de dados do projeto:

1. **ATU - Média de Alunos por Turma**: 2019-2025.
2. **TDI - Taxa de Distorção Idade-Série**: 2019-2025.
3. **IED - Indicador de Esforço Docente**: arquivos escolares disponíveis nesta coleção para 2021-2025.
4. **Rendimento Escolar**: aprovação, reprovação e abandono, 2019-2025.

Os dados são filtrados para a UF **RR** e integrados pela combinação `ANO + CO_ENTIDADE`.

Além desses indicadores, a pasta geral `Dados/censo` contém microdados do Censo Escolar de 2019-2024 e tabelas de 2025. Esses arquivos **não foram incorporados nesta primeira versão da base longitudinal**. Eles formam uma camada de enriquecimento recomendada para a segunda etapa do estudo, após o estabelecimento do modelo-base e da metodologia de validação temporal.

## 4. Dimensão da base

A versão 1.0 contém:

- **6.054 observações escola-ano**;
- **59 variáveis**;
- **934 escolas distintas** ao longo do período;
- **880 escolas públicas distintas** e **54 privadas**;
- **zero duplicidade** na chave composta `ANO + CO_ENTIDADE`.

A quantidade total de escolas presentes na união das fontes varia de **835 a 897 escolas por ano**. A base usa a **união das fontes**, e não apenas a interseção, para evitar a exclusão desnecessária de escolas que não possuem determinado indicador em um ano específico.

## 5. Cobertura anual

| Ano | Escolas | Públicas | ATU | TDI | IED | Rendimento | Públicas c/ abandono AF | Públicas c/ abandono EM | Alvo AF t+1 | Alvo EM t+1 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 843 | 798 | 667 | 666 | 0 | 666 | 239 | 158 | 237 | 157 |
| 2020 | 841 | 800 | 662 | 661 | 0 | 660 | 237 | 157 | 233 | 158 |
| 2021 | 835 | 796 | 651 | 650 | 651 | 650 | 234 | 159 | 235 | 160 |
| 2022 | 864 | 823 | 682 | 681 | 682 | 679 | 235 | 162 | 232 | 166 |
| 2023 | 880 | 836 | 690 | 689 | 690 | 689 | 233 | 167 | 239 | 168 |
| 2024 | 897 | 853 | 697 | 695 | 697 | 695 | 240 | 168 | 243 | 171 |
| 2025 | 894 | 854 | 687 | 687 | 689 | 687 | 244 | 173 | 0 | 0 |

**AF = Ensino Fundamental - Anos Finais; EM = Ensino Médio.**

O ano de 2025 não possui alvo `t+1`, pois a base termina em 2025. Assim, 2025 serve como desfecho para as observações de 2024 e como conjunto descritivo para futuras atualizações.

## 6. Estrutura das variáveis

### 6.1 Identificação e contexto

- `ANO`: ano de referência dos preditores.
- `ANO_ALVO`: ano seguinte associado ao desfecho `*_T1`.
- `CO_ENTIDADE`: código INEP da escola.
- `NO_ENTIDADE`: nome da escola.
- `CO_MUNICIPIO`, `NO_MUNICIPIO`: identificação do município.
- `LOCALIZACAO`: urbana ou rural.
- `DEPENDENCIA`: Federal, Estadual, Municipal ou Privada.
- `REDE_PUBLICA`: 1 para escola pública; 0 para privada.

### 6.2 Indicadores de disponibilidade

- `DISP_ATU`, `DISP_TDI`, `DISP_IED`, `DISP_REND` indicam se há pelo menos um valor daquele grupo de indicadores na observação.

Essas colunas são importantes porque a ausência de informação pode ser estrutural e não deve ser confundida automaticamente com valor zero.

### 6.3 ATU - Média de Alunos por Turma

A base mantém medidas para o Ensino Fundamental total, anos iniciais, anos finais e Ensino Médio. Para o estudo de abandono, as variáveis de maior interesse inicial são `ATU_FUN_AF` e `ATU_MED_TOTAL`.

### 6.4 TDI - Distorção Idade-Série

Inclui TDI do Ensino Fundamental total, anos iniciais, anos finais e Ensino Médio. TDI é especialmente relevante como medida de trajetória escolar acumulada e possível fator de risco contextual.

### 6.5 IED - Esforço Docente

São mantidas as proporções de docentes nos níveis 1 a 6, separadas para Ensino Fundamental e Ensino Médio. Também foram criadas:

- `IED_FUN_ALTO` = níveis 4 + 5 + 6 no Ensino Fundamental;
- `IED_MED_ALTO` = níveis 4 + 5 + 6 no Ensino Médio.

Na coleção escolar utilizada, os arquivos de IED estão disponíveis para 2021-2025. Os anos anteriores são mantidos como ausentes (`null`), sem imputação artificial.

### 6.6 Rendimento Escolar

Para Ensino Fundamental, anos iniciais, anos finais e Ensino Médio, foram integradas:

- taxa de aprovação;
- taxa de reprovação;
- taxa de abandono.

As taxas de aprovação, reprovação e abandono fecham em 100% para todas as observações em que as três medidas estão presentes, conforme verificação automática.

### 6.7 Variáveis temporais

A base contém variáveis construídas para explorar persistência e tendência:

- `*_LAG1`: valor do abandono no ano anterior `t-1`;
- `*_DELTA1`: diferença entre o valor atual e o do ano anterior;
- `*_T1`: valor do abandono no ano seguinte `t+1`, criado como **desfecho preditivo**.

Exemplos:

- `ABANDONO_FUN_AF_LAG1` - abandono dos anos finais no ano anterior;
- `TDI_FUN_AF_DELTA1` - variação anual da TDI dos anos finais;
- `ABANDONO_MED_T1` - abandono do Ensino Médio no ano seguinte.

## 7. Semântica temporal e prevenção de vazamento de informação

A estrutura foi construída para que os preditores de uma linha pertençam ao ano `t` e os principais desfechos pertençam ao ano `t+1`.

Exemplo:

- linha de 2023: ATU, TDI, IED e rendimento de 2023 são informações de entrada;
- `ABANDONO_MED_T1` nessa mesma linha contém a taxa observada em 2024.

As colunas `*_T1` **não podem ser usadas como preditores** do mesmo horizonte. Elas existem exclusivamente para treinamento, validação e avaliação dos modelos.

Também é necessário definir o momento operacional da previsão. Nesta versão, o cenário mais coerente é a **predição anual para planejamento do ano seguinte**, usando indicadores consolidados de `t` para priorizar escolas em `t+1`. Uma previsão intra-anual exigiria dados mais frequentes, como presença/frequência mensal, notas periódicas e movimentação de matrícula, que não estão representados nesta base anual.

## 8. Tratamento de valores ausentes

Ausência de dado não foi transformada em zero. Valores não disponíveis permanecem nulos.

Recomendação para modelagem:

1. quantificar a ausência por variável e ano;
2. distinguir ausência estrutural de ausência eventual;
3. comparar modelos que tratam nulos nativamente com estratégias de imputação simples;
4. não imputar IED em 2019-2020 como se o indicador tivesse sido observado;
5. criar versões de modelo com e sem IED para avaliar o ganho incremental desse grupo de variáveis.

## 9. Validação de integridade executada

A versão 1.0 foi submetida às seguintes verificações:

- `ANO + CO_ENTIDADE`: **0 duplicidades**;
- taxas educacionais: **0 valores fora do intervalo 0-100**;
- ATU: **0 valores não positivos** entre os valores observados;
- aprovação + reprovação + abandono: **100% das combinações completas fecham em 100**, com tolerância de 0,2 ponto percentual;
- soma dos níveis 1-6 do IED: **100% das combinações completas fecham em 100**;
- código INEP associado a mais de um município: **0 casos**;
- mudança de dependência administrativa para o mesmo código INEP: **0 casos**;
- mudança de localização urbana/rural ao longo dos anos: **6 escolas**;
- variação do nome da escola para o mesmo código INEP: **105 escolas**, o que pode refletir renomeações, ajustes cadastrais ou pequenas alterações de grafia. A chave longitudinal continua sendo o código INEP.

## 10. Estratégia recomendada de modelagem

A análise deve ser feita separadamente para **Anos Finais do Ensino Fundamental** e **Ensino Médio**, pois as distribuições de abandono, a quantidade de escolas e os fatores associados são diferentes.

A estratégia metodológica principal está detalhada no PDF da pasta `Documentacao`. Em resumo:

1. definir o horizonte como `t -> t+1`;
2. restringir o modelo operacional principal às escolas públicas;
3. estabelecer modelos de referência simples, incluindo persistência do abandono e regressão regularizada;
4. testar modelos interpretáveis e de machine learning;
5. fazer validação estritamente temporal;
6. utilizar 2023 -> 2024 como validação e 2024 -> 2025 como teste final;
7. executar análises de sensibilidade para 2020-2021 devido à ruptura causada pela pandemia e pelas regras excepcionais do período;
8. avaliar erro de previsão, capacidade de ranqueamento/priorização, calibração e estabilidade por município, localização e dependência administrativa;
9. produzir explicações globais e por escola;
10. transformar a saída em uma lista de priorização para intervenção humana, e não em decisão automatizada.

## 11. Observações sobre os anos 2020-2021

Os dados mostram mudança forte no padrão de abandono no período da pandemia. Por exemplo, nas escolas públicas com informação de anos finais, a taxa média de abandono passa de aproximadamente 5,4% em 2019 para 1,0% em 2020; no Ensino Médio, de aproximadamente 10,7% para 1,7%.

Esses anos não devem ser simplesmente eliminados nem tratados como períodos comuns. A proposta metodológica prevê:

- modelo com todos os anos;
- modelo/sensibilidade excluindo transições diretamente afetadas pelo período excepcional;
- variável de período/ano;
- avaliação da estabilidade das conclusões.

## 12. Limitações atuais

1. A base é agregada no nível da escola; não há identificação individual de estudantes.
2. O desfecho é a taxa de abandono reportada pelo INEP, e não uma medida individual de evasão longitudinal.
3. A periodicidade é anual; portanto, o uso mais natural é para planejamento do ano seguinte.
4. IED escolar está disponível nesta coleção apenas a partir de 2021.
5. Variáveis socioeconômicas, infraestrutura, composição de matrícula, docentes e turmas ainda não foram integradas nesta versão.
6. Mudanças de política, calendário, critérios de aprovação e choques externos podem gerar quebra de conceito ao longo da série.
7. Um modelo preditivo identifica padrões associados ao risco; não demonstra causalidade.

## 13. Próxima camada de enriquecimento

Após estabelecer um modelo-base reproduzível com esta versão, recomenda-se enriquecer a base com dados do Censo Escolar existentes em `Dados/censo`:

- porte da escola e total de matrículas;
- composição por etapa/modalidade;
- percentual de tempo integral;
- EJA e educação especial;
- características de infraestrutura;
- zona e contexto territorial;
- indicadores de corpo docente;
- características de turmas;
- variáveis de mobilidade/movimento quando comparáveis entre anos.

A inclusão deve obedecer a um dicionário de harmonização, porque os nomes e a estrutura das variáveis podem mudar entre edições do Censo.

## 14. Regras para atualização futura

Quando os indicadores de 2026 forem disponibilizados:

1. incluir 2026 como novo ano de indicadores;
2. gerar o desfecho `t+1` para as linhas de 2025;
3. manter os dados de 2026 como observações sem alvo futuro até a chegada de 2027;
4. repetir todas as verificações de integridade;
5. não sobrescrever silenciosamente versões anteriores da base;
6. registrar data, fontes e alterações do dicionário.

## 15. Reprodutibilidade e governança

A versão publicada deve ser considerada uma **base derivada**. Os arquivos brutos permanecem nas pastas originais e não devem ser alterados.

Qualquer alteração na lógica de construção deve gerar:

- nova versão da base;
- atualização do README;
- atualização do dicionário;
- novo relatório de validação;
- registro das variáveis incluídas/excluídas.

Para produção científica, recomenda-se congelar a versão usada em cada experimento e registrar o hash dos arquivos finais.

---

**Responsabilidade analítica:** a base deve apoiar investigação científica e priorização preventiva por gestores. Resultados preditivos não devem ser usados isoladamente para classificar qualidade escolar, responsabilizar profissionais ou determinar medidas automáticas sem análise contextual e validação humana.
