"""Gera dados/MANIFEST.csv: procedência de tudo que está em dados/origem/,
dados/bruto/ e dados/externo/, com sha256 e data de download.

Uma linha por arquivo, com o estágio (origem / bruto / externo) e quem o
fornece (inep / orientador). Registrar os zips de origem/ permite validar um
zip antes de extraí-lo; registrar o extraído em bruto/ permite validar a
extração. `arquivo` é o caminho relativo a dados/.

A data de download de um arquivo já presente no manifesto anterior é
preservada (casada pelo nome-base, que sobrevive à migração de pastas de
2026-09-30); para arquivo novo usa-se a data de modificação no disco, que é a
data em que foi salvo na pasta. O manifesto é o único item de dados/ versionado
no git (CLAUDE.md §3, regra 2).
"""
from __future__ import annotations

import csv
import datetime as dt
import logging
import pathlib

from src.aquisicao import DOCUMENTACAO, MICRODADOS_ZIP, sha256_arquivo
from src.config import (
    ARQUIVOS,
    BASE_LONGITUDINAL_V1,
    DADOS,
    INDICADORES,
    MANIFEST,
    ORIGEM_CENSO,
    ORIGEM_DOC,
    ORIGEM_INDICADORES,
)
from src.extrair_brutos_inep import parse_nome_zip

logger = logging.getLogger(__name__)

CAMPOS = ["estagio", "origem", "ano", "tabela", "arquivo", "sha256", "data_download"]

# (estagio, origem, ano, tabela, path)
Item = tuple[str, str, str, str, pathlib.Path]


def _itens_indicadores_extraidos() -> list[Item]:
    """.xlsx e md5_*.txt de bruto/indicadores/, rotulados pelo _manifesto.csv
    que src/extrair_brutos_inep.py grava junto (tipo, ano e nível do zip)."""
    rotulos = INDICADORES / "_manifesto.csv"
    if not rotulos.exists():
        raise FileNotFoundError(
            f"{rotulos} não existe. Rode `python -m src.extrair_brutos_inep` antes."
        )
    itens: list[Item] = []
    with rotulos.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["acao"] == "extraido":
                itens.append((
                    "bruto", "inep", r["ano"], f"indicador_{r['tipo']}_{r['nivel']}",
                    INDICADORES / r["arquivo_extraido"],
                ))
    return sorted(itens, key=lambda i: i[4])


def _itens() -> list[Item]:
    """Tudo que deve constar no manifesto, na ordem origem → bruto → externo."""
    itens: list[Item] = [
        ("origem", "inep", str(ano), "microdados", ORIGEM_CENSO / nome)
        for ano, nome in sorted(MICRODADOS_ZIP.items())
    ]
    for z in sorted(ORIGEM_INDICADORES.glob("*.zip")):
        parsed = parse_nome_zip(z.stem)
        tipo, ano, nivel = parsed if parsed else ("?", "", "?")
        itens.append(("origem", "inep", str(ano), f"indicador_{tipo}_{nivel}", z))
    itens += [
        ("origem", "inep", str(ano), "documentacao", ORIGEM_DOC / nome)
        for nome, (ano, _membro) in sorted(DOCUMENTACAO.items())
    ]
    itens += [
        ("bruto", "inep", str(ano), tabela, p) for (ano, tabela), p in sorted(ARQUIVOS.items())
    ]
    itens += _itens_indicadores_extraidos()
    itens += [
        ("externo", "orientador", "", "base_longitudinal_v1", p)
        for p in sorted(BASE_LONGITUDINAL_V1.glob("*")) if p.is_file()
    ]
    return itens


def gerar(caminho_manifest: pathlib.Path = MANIFEST) -> pathlib.Path:
    anteriores: dict[str, str] = {}
    if caminho_manifest.exists():
        with caminho_manifest.open(encoding="utf-8") as f:
            anteriores = {
                pathlib.PurePosixPath(r["arquivo"]).name: r["data_download"]
                for r in csv.DictReader(f)
            }

    linhas = []
    for estagio, origem, ano, tabela, p in _itens():
        if not p.exists():
            raise FileNotFoundError(f"Arquivo esperado em dados/{estagio}/ não existe: {p}")
        data = anteriores.get(p.name) or dt.datetime.fromtimestamp(
            p.stat().st_mtime, tz=dt.timezone.utc
        ).date().isoformat()
        rel = p.relative_to(DADOS).as_posix()
        logger.info("sha256 %s", rel)
        linhas.append([estagio, origem, ano, tabela, rel, sha256_arquivo(p), data])

    with caminho_manifest.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CAMPOS)
        w.writerows(linhas)
    return caminho_manifest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger.info("Gravado %s", gerar())
