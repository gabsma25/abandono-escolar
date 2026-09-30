"""Gera docs/catalogo_variaveis.html — página navegável com todas as variáveis
de cada tabela (microdados por arquivo e planilhas de indicadores), a partir
dos CSVs gerados em docs/. Nada aqui é digitado: só embute os CSVs como JSON.
"""
from __future__ import annotations

import csv
import json
import logging
import pathlib

from src.config import DADOS, DOCS, EXTRACAO_INDICADORES

logger = logging.getLogger(__name__)

_MOLDE = pathlib.Path(__file__).with_name("relatorio_catalogo.html")


def _ler(nome: str) -> list[dict]:
    p = DOCS / nome
    if not p.exists():
        logger.warning("%s não existe; seção correspondente ficará vazia", p)
        return []
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def relacao_extraidos() -> list[dict]:
    """Planilhas de indicadores extraídas (linhas 'extraido' de
    docs/extracao_indicadores.csv que são .xlsx), com tamanho no disco."""
    manifesto = EXTRACAO_INDICADORES
    if not manifesto.exists():
        logger.warning("%s não existe; relação de extraídos ficará vazia", manifesto)
        return []
    linhas = []
    with manifesto.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["acao"] != "extraido" or not r["arquivo_extraido"].lower().endswith(".xlsx"):
                continue
            arq = DADOS / r["arquivo_extraido"]
            linhas.append({
                "tipo": r["tipo"], "ano": r["ano"], "nivel": r["nivel"],
                "arquivo": (DADOS.relative_to(DOCS.parent) / r["arquivo_extraido"]).as_posix(),
                "tamanho_mb": round(arq.stat().st_size / 1e6, 1) if arq.exists() else "",
                "md5_confere": r["md5_confere"], "zip_original": r["zip_original"],
            })
    linhas.sort(key=lambda r: (r["tipo"], r["nivel"], r["ano"]))
    return linhas


def gerar(destino: pathlib.Path = DOCS / "catalogo_variaveis.html") -> pathlib.Path:
    dados = {
        "extraidos": relacao_extraidos(),
        "inventario": _ler("inventario.csv"),
        "catalogo_longo": _ler("catalogo_variaveis_microdados.csv"),
        "catalogo": _ler("catalogo_variaveis.csv"),
        "inventario_ind": _ler("inventario_indicadores.csv"),
        "presenca_ind": _ler("presenca_colunas_indicadores.csv"),
        "problemas": _ler("problemas.csv"),
    }
    molde = _MOLDE.read_text(encoding="utf-8")
    html = molde.replace("/*__DADOS__*/null", json.dumps(dados, ensure_ascii=False).replace("</", r"<\/"))
    destino.write_text(html, encoding="utf-8")
    return destino


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger.info("Gravado %s", gerar())
