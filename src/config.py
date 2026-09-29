"""Caminhos, constantes e dicionário central de arquivos de dados brutos."""
import pathlib

RAIZ = pathlib.Path(__file__).parent.parent
BRUTO = RAIZ / "dados" / "bruto"
INTERIM = RAIZ / "dados" / "interim"
PROCESSADO = RAIZ / "dados" / "processado"
DOCS = RAIZ / "docs"

ENCODING = "cp1252"
SEP = ";"

# Chave: (ano: int, tabela: str)  →  Path
# Tabelas disponíveis por ano:
#   2019–2024 : "escola"  (microdados_ed_basica_{ano}; 2020 tem extensão .CSV
#                          em maiúsculas — nome original preservado, regra 1)
#   2025      : "escola", "turma", "matricula", "docente"
# Nunca monte o caminho por concatenação com o ano: use caminho(ano, tabela).
ARQUIVOS: dict[tuple[int, str], pathlib.Path] = {
    (2019, "escola"):    BRUTO / "microdados_ed_basica_2019.csv",
    (2020, "escola"):    BRUTO / "microdados_ed_basica_2020.CSV",
    (2021, "escola"):    BRUTO / "microdados_ed_basica_2021.csv",
    (2022, "escola"):    BRUTO / "microdados_ed_basica_2022.csv",
    (2023, "escola"):    BRUTO / "microdados_ed_basica_2023.csv",
    (2024, "escola"):    BRUTO / "microdados_ed_basica_2024.csv",
    (2025, "escola"):    BRUTO / "Tabela_Escola_2025_V2.csv",
    (2025, "turma"):     BRUTO / "Tabela_Turma_2025_V2.csv",
    (2025, "matricula"): BRUTO / "Tabela_Matricula_2025_V2.csv",
    (2025, "docente"):   BRUTO / "Tabela_Docente_2025_V2.csv",
}

# Indicadores educacionais do INEP (desfechos e contexto), baixados como .zip
# em dados/bruto/brutos-inep/ e extraídos por src/extrair_brutos_inep.py para
# INDICADORES/{tipo}/{ano}/. Ver src/indicadores_inep.py para localizar um
# arquivo por (tipo, ano, nivel).
BRUTOS_INEP = BRUTO / "brutos-inep"
INDICADORES = INTERIM / "brutos_inep_extraido"

# Documentação oficial que acompanha os microdados (não é dado).
DOC_CENSO = BRUTO / "doc-censo"

_ANOS_DISPONIVEIS = sorted({ano for ano, _ in ARQUIVOS})
_TABELAS_POR_ANO: dict[int, list[str]] = {}
for _ano, _tab in ARQUIVOS:
    _TABELAS_POR_ANO.setdefault(_ano, []).append(_tab)


def caminho(ano: int, tabela: str) -> pathlib.Path:
    """Retorna o Path para (ano, tabela); levanta ValueError com mensagem útil."""
    chave = (ano, tabela)
    if chave in ARQUIVOS:
        p = ARQUIVOS[chave]
        if not p.exists():
            raise FileNotFoundError(
                f"Arquivo mapeado para ({ano!r}, {tabela!r}) não foi encontrado: {p}\n"
                f"Baixe o arquivo e coloque em dados/bruto/ sem renomear."
            )
        return p

    if ano not in _ANOS_DISPONIVEIS:
        raise ValueError(
            f"Ano {ano!r} não está no dicionário ARQUIVOS.\n"
            f"Anos disponíveis: {_ANOS_DISPONIVEIS}\n"
            f"Se o arquivo foi baixado, adicione a entrada em src/config.py."
        )

    tabs_do_ano = _TABELAS_POR_ANO[ano]
    raise ValueError(
        f"Tabela {tabela!r} não existe para o ano {ano}.\n"
        f"Tabelas disponíveis em {ano}: {tabs_do_ano}\n"
        f"Tabelas Turma/Matrícula/Docente só foram separadas a partir de 2025."
    )


# ── Tipagem obrigatória (CLAUDE.md §3, regra 6) ──────────────────────────
# CO_ENTIDADE e CO_MUNICIPIO → str
# IN_* e TP_* → pd.Int8Dtype()
# QT_* → pd.Int32Dtype()

DTYPE_STR = ["CO_ENTIDADE", "CO_MUNICIPIO", "CO_UF", "CO_REDE",
             "CO_DISTRITO", "CO_SUBDISTRITO"]

# Colunas de chave que não devem entrar como preditores
COLS_CHAVE = ["CO_ENTIDADE", "NU_ANO_CENSO", "CO_MUNICIPIO"]

# Colunas de filtro (definem a amostra; descartadas após o recorte)
COLS_FILTRO = [
    "SG_UF", "TP_DEPENDENCIA", "TP_SITUACAO_FUNCIONAMENTO",
    "IN_REGULAR", "IN_ESCOLARIZACAO",
    # oferta de EM — varia por geração; resolvido em filtros.py
    "IN_MED",                    # 2022-2024
    "IN_COMUM_MEDIO_MEDIO",      # 2025 (definição a escolher)
    "IN_COMUM_MEDIO_INTEGRADO",  # 2025
    "IN_COMUM_MEDIO_NORMAL",     # 2025
    "IN_COMUM_MEDIO_FIC",        # 2025
]

# Colunas de estratificação (usadas na avaliação de equidade)
COLS_ESTRATIFICACAO = [
    "TP_LOCALIZACAO",
    "TP_LOCALIZACAO_DIFERENCIADA",
    "IN_EDUCACAO_INDIGENA",
    "CO_ORGAO_REGIONAL",
]
