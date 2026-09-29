"""Gera dados/MANIFEST.csv: procedência de TUDO que está em dados/bruto/
(microdados, .zip de indicadores e documentação), com sha256 e data de download.

A data de download de um arquivo já presente no manifesto anterior é
preservada; para arquivo novo usa-se a data de modificação no disco, que é a
data em que foi salvo na pasta. O manifesto é o único item de dados/ versionado
no git (CLAUDE.md §3, regra 2).
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import logging
import pathlib

from src.config import ARQUIVOS, BRUTO, BRUTOS_INEP, DOC_CENSO
from src.extrair_brutos_inep import parse_nome_zip

logger = logging.getLogger(__name__)

MANIFEST = BRUTO.parent / "MANIFEST.csv"
CAMPOS = ["ano", "tabela", "arquivo", "sha256", "data_download"]


def _sha256(caminho: pathlib.Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _itens_bruto() -> list[tuple[str, str, pathlib.Path]]:
    """[(ano, tabela, path)] de tudo que deve constar no manifesto."""
    itens: list[tuple[str, str, pathlib.Path]] = [
        (str(ano), tabela, p) for (ano, tabela), p in sorted(ARQUIVOS.items())
    ]
    for z in sorted(BRUTOS_INEP.glob("*.zip")):
        parsed = parse_nome_zip(z.stem.split(" (")[0])
        tipo, ano, nivel = parsed if parsed else ("?", "", "?")
        itens.append((str(ano), f"indicador_{tipo}_{nivel}", z))
    for d in sorted(DOC_CENSO.glob("*")):
        if d.is_file():
            itens.append(("", "documentacao", d))
    return itens


def gerar(caminho_manifest: pathlib.Path = MANIFEST) -> pathlib.Path:
    anteriores: dict[str, str] = {}
    if caminho_manifest.exists():
        with caminho_manifest.open(encoding="utf-8") as f:
            anteriores = {r["arquivo"]: r["data_download"] for r in csv.DictReader(f)}

    linhas = []
    for ano, tabela, p in _itens_bruto():
        if not p.exists():
            raise FileNotFoundError(f"Arquivo esperado não existe em dados/bruto/: {p}")
        rel = p.relative_to(BRUTO).as_posix()
        data = anteriores.get(rel) or anteriores.get(p.name) or dt.datetime.fromtimestamp(p.stat().st_mtime, tz=dt.timezone.utc).date().isoformat()
        logger.info("sha256 %s", rel)
        linhas.append([ano, tabela, rel, _sha256(p), data])

    with caminho_manifest.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CAMPOS)
        w.writerows(linhas)
    return caminho_manifest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger.info("Gravado %s", gerar())
