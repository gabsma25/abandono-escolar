"""Recorte de Roraima das planilhas de indicadores do INEP no nível escola.

Lê cada planilha extraída (dados/interim/brutos_inep_extraido/{tipo}/{ano}/)
em modo read_only, detecta a linha de nomes técnicos do mesmo modo que
src/indicadores_inep.py, mantém só as linhas com SG_UF == 'RR' e grava um
Parquet por (tipo, ano) em dados/interim/indicadores_rr/{tipo}_{ano}.parquet
com os nomes técnicos ORIGINAIS da planilha (a harmonização entre gerações é
feita depois, em src/base_longitudinal.py).

Regras aplicadas na leitura (CLAUDE.md §3):
- '--' (ou célula vazia) é ausente, nunca zero → pd.NA;
- CO_ENTIDADE e CO_MUNICIPIO viram string;
- as colunas de indicador viram Float64 nullable.
"""
from __future__ import annotations

import logging
import pathlib

import openpyxl
import pandas as pd

from src.config import INTERIM
from src.indicadores_inep import (
    MARCADOR_AUSENTE,
    _eh_inicio_cabecalho,
    _nomes_posicionais,
    caminho_indicador,
)

logger = logging.getLogger(__name__)

INDICADORES_RR = INTERIM / "indicadores_rr"

# Indicadores com série no nível escola (HAD só existe em 2025 — P006).
TIPOS_ESCOLA: dict[str, range] = {
    "tx_rend": range(2019, 2026),
    "TDI": range(2019, 2026),
    "ATU": range(2019, 2026),
    "IED": range(2021, 2026),
}

COLS_TEXTO = {
    "NU_ANO_CENSO", "Ano", "NO_REGIAO", "SG_UF", "CO_MUNICIPIO", "NO_MUNICIPIO",
    "CO_ENTIDADE", "NO_ENTIDADE", "NO_CATEGORIA", "TIPOLOCA", "NO_DEPENDENCIA",
    "Dependad",
}
COLS_STRING = {"CO_ENTIDADE", "CO_MUNICIPIO"}


def caminho_rr(tipo: str, ano: int) -> pathlib.Path:
    return INDICADORES_RR / f"{tipo}_{ano}.parquet"


def extrair_rr(tipo: str, ano: int) -> pd.DataFrame:
    """DataFrame com as linhas de RR da planilha de escolas de (tipo, ano)."""
    caminho = caminho_indicador(tipo, ano, "escolas")
    wb = openpyxl.load_workbook(caminho, read_only=True)
    try:
        ws = wb.worksheets[0]
        colunas: list[str] | None = None
        anterior: tuple | None = None
        pos_uf: int | None = None
        linhas: list[tuple] = []
        for row in ws.iter_rows(values_only=True):
            primeira = row[0] if row else None
            eh_ano = isinstance(primeira, (int, float)) and 1990 <= primeira <= 2100
            if colunas is None:
                if not eh_ano:
                    anterior = row
                    continue
                if anterior is None or not _eh_inicio_cabecalho(anterior[0]):
                    raise ValueError(
                        f"{caminho.name}: a linha anterior à 1ª linha de dados não é a "
                        f"linha de nomes técnicos (esperado 'Ano'/'NU_ANO_CENSO')."
                    )
                colunas = _nomes_posicionais(anterior)
                if "SG_UF" not in colunas:
                    raise ValueError(f"{caminho.name}: sem coluna SG_UF; colunas: {colunas}")
                pos_uf = colunas.index("SG_UF")
            if eh_ano and row[pos_uf] == "RR":
                linhas.append(row[: len(colunas)])
    finally:
        wb.close()

    df = pd.DataFrame(linhas, columns=colunas)
    for col in df.columns:
        if col in COLS_STRING:
            df[col] = df[col].astype("string")
        elif col in COLS_TEXTO:
            df[col] = df[col].astype("string") if col not in ("NU_ANO_CENSO", "Ano") else df[col].astype("Int16")
        else:
            serie = df[col].replace({MARCADOR_AUSENTE: pd.NA, "": pd.NA})
            df[col] = pd.to_numeric(serie, errors="raise").astype("Float64")
    logger.info("%s %s: %d linhas RR, %d colunas", tipo, ano, len(df), df.shape[1])
    return df


def gravar_todos(destino: pathlib.Path = INDICADORES_RR, sobrescrever: bool = False) -> list[pathlib.Path]:
    """Extrai e grava todos os (tipo, ano) de TIPOS_ESCOLA; pula os já gravados."""
    destino.mkdir(parents=True, exist_ok=True)
    gravados = []
    for tipo, anos in TIPOS_ESCOLA.items():
        for ano in anos:
            alvo = destino / f"{tipo}_{ano}.parquet"
            if alvo.exists() and not sobrescrever:
                logger.info("Já existe, pulando: %s", alvo.name)
                gravados.append(alvo)
                continue
            df = extrair_rr(tipo, ano)
            df.to_parquet(alvo, index=False)
            gravados.append(alvo)
    return gravados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    for p in gravar_todos():
        logger.info("Gravado %s", p)
