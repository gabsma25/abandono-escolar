"""Gera docs/desfechos.csv (Tabela C) e docs/dicionario_anotado.csv (Tabela B)
a partir das tabelas de docs/metodologia_variaveis.md (§5 e §4).

    python -m src.tabelas_metodologia

O documento de metodologia é a fonte: este módulo só lê as tabelas Markdown
dele e as achata em CSV — nenhum papel, fórmula ou significado é digitado
aqui (CLAUDE.md §3, regra 9). Uma célula com várias variáveis
("`CO_MUNICIPIO`, `NO_MUNICIPIO`") vira uma linha por variável; um intervalo
("`IED_FUN_N1`…`N6`") e um curinga ("`REPROVACAO_*`") são expandidos contra
as colunas da base regerada, e o que não casar com nenhuma é erro.
"""
from __future__ import annotations

import csv
import fnmatch
import logging
import pathlib
import re

from src.base_longitudinal import COLUNAS
from src.config import DOCS

logger = logging.getLogger(__name__)

METODOLOGIA = DOCS / "metodologia_variaveis.md"
DESFECHOS = DOCS / "desfechos.csv"
DICIONARIO = DOCS / "dicionario_anotado.csv"

_TITULO = re.compile(r"^(#{2,3})\s+(\d+(?:\.\d+)?)\.?\s+(.*)$")
_NOME = re.compile(r"`([A-Za-z0-9_*]+)`")
_INTERVALO = re.compile(r"`([A-Z0-9_]*?)(\d+)`\s*…\s*`[A-Z]*?(\d+)`")


def secoes(texto: str) -> dict[str, list[str]]:
    """{número da seção ('4.2', '5'): linhas até o próximo título}."""
    atual, blocos = None, {}
    for linha in texto.splitlines():
        m = _TITULO.match(linha)
        if m:
            atual = m.group(2)
            blocos[atual] = []
        elif atual is not None:
            blocos[atual].append(linha)
    return blocos


def tabelas(linhas: list[str]) -> list[list[dict[str, str]]]:
    """Tabelas Markdown de um bloco, cada uma como lista de {cabeçalho: célula}."""
    resultado, atual = [], []
    for linha in [*linhas, ""]:
        if linha.startswith("|"):
            atual.append([c.strip() for c in linha.strip().strip("|").split("|")])
        elif atual:
            cab, *resto = atual
            corpo = [r for r in resto if not all(set(c) <= set(":-") for c in r)]
            resultado.append([dict(zip(cab, r, strict=True)) for r in corpo])
            atual = []
    return resultado


def _limpar(celula: str) -> str:
    return re.sub(r"\*\*", "", celula).strip()


def nomes_da_celula(celula: str, colunas: list[str] = COLUNAS) -> list[str]:
    """Variáveis citadas na célula, com intervalos e curingas expandidos."""
    m = _INTERVALO.search(celula)
    if m:
        prefixo, ini, fim = m.group(1), int(m.group(2)), int(m.group(3))
        return [f"{prefixo}{i}" for i in range(ini, fim + 1)]
    nomes = []
    for n in _NOME.findall(celula):
        if "*" in n:
            casados = [c for c in colunas if fnmatch.fnmatchcase(c, n) and not c.endswith(("_LAG1", "_DELTA1", "_T1"))]
            if not casados:
                raise ValueError(f"Curinga {n!r} não casa com nenhuma coluna da base.")
            nomes += casados
        else:
            nomes.append(n)
    return nomes


def gerar_desfechos(texto: str, destino: pathlib.Path = DESFECHOS) -> list[dict]:
    """Tabela C = a tabela do §5, uma linha por desfecho.

    "idem" é resolvido pela ordem: numa linha com k variáveis (ex.:
    `OCORRE_AF_T1`, `OCORRE_EM_T1`), a k-ésima herda da k-ésima linha
    principal da tabela (as que não usam "idem": AF e depois EM)."""
    (tabela,) = tabelas(secoes(texto)["5"])
    principais = [r for r in tabela if "idem" not in r.values()]
    linhas = []
    for r in tabela:
        for k, nome in enumerate(nomes_da_celula(r["Desfecho"])):
            base = {c: (principais[k][c] if v == "idem" else v) for c, v in r.items()}
            linhas.append({
                "desfecho": nome, "formula": _limpar(base["Fórmula"]), "etapa": base["Etapa"],
                "anos_com_alvo": base["Anos com alvo"], "tipo": base["Tipo"], "uso": _limpar(base["Uso"]),
                "a_decidir": "sim" if "[DECIDIR]" in base["Uso"] else "não",
                "na_base_regerada": "sim" if nome in COLUNAS else "não",
            })
    _gravar(linhas, destino)
    return linhas


def _gravar(linhas: list[dict], destino: pathlib.Path) -> None:
    with destino.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(linhas)
    logger.info("Gravado %s (%d linhas)", destino, len(linhas))


def main() -> None:
    texto = METODOLOGIA.read_text(encoding="utf-8")
    gerar_desfechos(texto)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
