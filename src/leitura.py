"""Perfil dos arquivos de microdados do Censo Escolar (dados/bruto/) e tabelas
de documentação derivadas deles: docs/inventario.csv (Tabela A) e
docs/presenca_colunas_escola.csv.

Só lê. Contagens usam DuckDB (arquivos de ~200 MB cada); a detecção de
encoding lê os primeiros bytes e testa utf-8 ANTES de cp1252, porque cp1252 e
latin-1 nunca levantam erro e mascarariam um arquivo utf-8 (CLAUDE.md §6).
"""
from __future__ import annotations

import csv
import logging
import pathlib
from dataclasses import dataclass, field

import duckdb

from src.config import ARQUIVOS, DOCS, caminho

logger = logging.getLogger(__name__)

_AMOSTRA_BYTES = 4 << 20
_SEPARADORES_CANDIDATOS = (";", ",", "|", "\t")


@dataclass
class PerfilCSV:
    ano: int
    tabela: str
    arquivo: str
    tamanho_bytes: int
    encoding: str
    evidencia_encoding: str
    separador: str
    colunas: list[str] = field(default_factory=list)
    n_linhas: int = 0
    n_linhas_rr: int | None = None   # None quando a tabela não tem SG_UF

    @property
    def n_colunas(self) -> int:
        return len(self.colunas)


def detectar_encoding(caminho_arquivo: pathlib.Path) -> tuple[str, str]:
    """('utf-8' | 'cp1252', evidência). Testa utf-8 primeiro na amostra inicial."""
    with caminho_arquivo.open("rb") as f:
        amostra = f.read(_AMOSTRA_BYTES)
    try:
        amostra.decode("utf-8")
    except UnicodeDecodeError as e:
        byte = amostra[e.start]
        return "cp1252", f"utf-8 falha na posição {e.start} (byte {byte:#04x} = {bytes([byte]).decode('cp1252')!r} em cp1252)"
    return "utf-8", f"primeiros {len(amostra)} bytes decodificam como utf-8 sem erro"


def detectar_separador(cabecalho: str) -> str:
    contagens = {sep: cabecalho.count(sep) for sep in _SEPARADORES_CANDIDATOS}
    sep, n = max(contagens.items(), key=lambda kv: kv[1])
    if n == 0:
        raise ValueError(f"Nenhum separador candidato {list(_SEPARADORES_CANDIDATOS)} no cabeçalho: {cabecalho[:120]!r}")
    return sep


def perfilar_csv(ano: int, tabela: str, contar_linhas: bool = True) -> PerfilCSV:
    """Perfil de um arquivo de ARQUIVOS: encoding, separador, colunas, contagens."""
    p = caminho(ano, tabela)
    encoding, evidencia = detectar_encoding(p)
    with p.open("r", encoding=encoding, newline="") as f:
        cabecalho = f.readline().rstrip("\r\n")
    sep = detectar_separador(cabecalho)
    colunas = [c.strip().strip('"') for c in cabecalho.split(sep)]
    perfil = PerfilCSV(ano, tabela, p.name, p.stat().st_size, encoding, evidencia, sep, colunas)

    if contar_linhas:
        # DuckDB não aceita 'cp1252'; 'latin-1' decodifica os mesmos bytes e só
        # difere em 0x80–0x9F, irrelevante para contar linhas e comparar SG_UF.
        enc_duck = "latin-1" if encoding == "cp1252" else encoding
        fonte = (
            f"read_csv('{p.as_posix()}', delim='{sep}', header=true, "
            f"encoding='{enc_duck}', all_varchar=true)"
        )
        con = duckdb.connect()
        try:
            perfil.n_linhas = con.execute(f"SELECT count(*) FROM {fonte}").fetchone()[0]
            if "SG_UF" in colunas:
                perfil.n_linhas_rr = con.execute(
                    f"SELECT count(*) FROM {fonte} WHERE SG_UF = 'RR'"
                ).fetchone()[0]
        finally:
            con.close()
    return perfil


def inventariar_microdados(destino_docs: pathlib.Path = DOCS) -> tuple[pathlib.Path, pathlib.Path]:
    """Perfila todos os arquivos de ARQUIVOS e grava docs/inventario.csv e
    docs/presenca_colunas_escola.csv (coluna × ano; a posição da coluna no
    arquivo é o valor, vazio = ausente; 2025 tem uma coluna por tabela)."""
    perfis = [perfilar_csv(ano, tab) for ano, tab in sorted(ARQUIVOS)]
    for p in perfis:
        logger.info("%s %s: %d colunas, %d linhas, RR=%s", p.ano, p.tabela, p.n_colunas, p.n_linhas, p.n_linhas_rr)

    destino_docs.mkdir(parents=True, exist_ok=True)
    inv = destino_docs / "inventario.csv"
    with inv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "ano", "tabela", "arquivo", "tamanho_mb", "encoding", "evidencia_encoding",
            "separador", "n_colunas", "n_linhas", "n_linhas_rr",
        ])
        for p in perfis:
            w.writerow([
                p.ano, p.tabela, p.arquivo, round(p.tamanho_bytes / 1e6, 1), p.encoding,
                p.evidencia_encoding, p.separador, p.n_colunas, p.n_linhas,
                "" if p.n_linhas_rr is None else p.n_linhas_rr,
            ])

    # Presença: chave de coluna = "{ano}" para escola, "{ano}_{tabela}" para as demais
    rotulos = [f"{p.ano}" if p.tabela == "escola" else f"{p.ano}_{p.tabela}" for p in perfis]
    presenca: dict[str, dict[str, int]] = {}
    ordem: dict[str, tuple[int, int]] = {}
    for rotulo, p in zip(rotulos, perfis):
        for pos, col in enumerate(p.colunas, start=1):
            presenca.setdefault(col, {})[rotulo] = pos
            ordem.setdefault(col, (0 if p.tabela == "escola" else 1, pos))
    pres = destino_docs / "presenca_colunas_escola.csv"
    with pres.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["coluna", *rotulos, "n_arquivos"])
        for col in sorted(presenca, key=lambda c: ordem[c]):
            w.writerow([col, *[presenca[col].get(r, "") for r in rotulos], len(presenca[col])])
    return inv, pres


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    inv, pres = inventariar_microdados()
    logger.info("Gravados %s e %s", inv, pres)
