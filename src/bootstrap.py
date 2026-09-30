"""Leva um clone limpo ao estado de trabalho do projeto, na ordem certa.

    python -m src.bootstrap --origem-local ~/Downloads     # zips já baixados
    python -m src.bootstrap --baixar                       # baixa do INEP o que faltar
    python -m src.bootstrap --baixar --so-aquisicao        # só obtém, extrai e confere

Etapas: aquisição dos zips (cópia local e/ou download) -> extração dos
microdados e dos indicadores -> conferência de tudo contra dados/MANIFEST.csv
-> inventários e catálogo (docs/) -> recorte de RR (interim/) -> análise da base
v1.0 do orientador, se ela estiver em dados/externo/ (dado de terceiro, não
obtenível do INEP: sem ela a etapa é pulada com aviso, sem falhar).

Tudo é idempotente: o que já existe e confere não é refeito nem tocado. No
fim, `git status docs/` deve estar limpo — os CSVs de docs/ são versionados,
e diferença ali significa que o clone não reproduziu o estado registrado.
"""
from __future__ import annotations

import argparse
import logging
import pathlib
import shutil
import subprocess
import time
from collections.abc import Callable

from src import (
    analise_base_longitudinal,
    aquisicao,
    catalogo_microdados,
    extrair_brutos_inep,
    indicadores_inep,
    indicadores_rr,
    leitura,
    relatorio_catalogo,
)
from src.config import BASE_LONGITUDINAL_V1, DADOS, RAIZ

logger = logging.getLogger(__name__)

# Medido em 2026-09-30 nesta estrutura (du -sb por pasta).
ESPACO_MB = {
    "origem/ (zips, download)": 2904,
    "bruto/ (extraído)": 3046,
    "interim/, docs/catalogo_variaveis.html": 4,
}
# Tempo por etapa, arredondado para cima, do bootstrap num clone limpo em
# 2026-09-30 (notebook com SSD, zips por --origem-local; total medido: 36 min).
# O download depende da conexão: 2,9 GB a 10 Mbit/s ≈ 40 min.
MINUTOS = {
    "aquisicao": 1,
    "extracao": 1,
    "conferencia": 1,
    "inventario_microdados": 1,
    "catalogo_microdados": 1,
    "inventario_indicadores": 23,
    "recorte_rr": 13,
    "analise_base_v1": 1,
    "catalogo_html": 1,
}


def imprimir_estimativa(so_aquisicao: bool, baixar: bool) -> None:
    total_mb = sum(ESPACO_MB.values())
    livre_mb = shutil.disk_usage(DADOS.parent).free // 10**6
    etapas = ["aquisicao", "extracao", "conferencia"] if so_aquisicao else list(MINUTOS)
    minutos = sum(MINUTOS[e] for e in etapas)
    linhas = [f"  {k:42s} {v / 1000:5.1f} GB" for k, v in ESPACO_MB.items()]
    logger.info(
        "Estimativa (medida em 2026-09-30):\n%s\n  %-42s %5.1f GB (livre: %.1f GB)\n"
        "  tempo: ~%d min%s",
        "\n".join(linhas), "total em dados/ num clone limpo", total_mb / 1000, livre_mb / 1000,
        minutos, " + download (2,9 GB)" if baixar else "",
    )
    if livre_mb < total_mb:
        logger.warning("Espaço livre (%.1f GB) menor que o estimado (%.1f GB).", livre_mb / 1000, total_mb / 1000)


def _etapa(nome: str, funcao: Callable[[], object]) -> object:
    logger.info("== %s (estimativa ~%d min)", nome, MINUTOS.get(nome, 0))
    inicio = time.monotonic()
    resultado = funcao()
    logger.info("== %s concluída em %.1f min", nome, (time.monotonic() - inicio) / 60)
    return resultado


def _extrair_indicadores() -> None:
    extrair_brutos_inep.escrever_extracao(extrair_brutos_inep.extrair())


def _conferir() -> None:
    erros, _avisos = aquisicao.verificar_manifesto()
    if erros:
        raise SystemExit(f"{len(erros)} arquivo(s) não conferem com dados/MANIFEST.csv; ver log acima.")


def _analise_base_v1() -> None:
    base = BASE_LONGITUDINAL_V1 / "base_longitudinal_abandono_rr_2019_2025.csv"
    if not base.exists():
        logger.warning(
            "Base v1.0 do orientador ausente em %s — etapa pulada. Ela é dado externo "
            "(CLAUDE.md §2.3): peça os 6 arquivos ao orientador; o sha256 esperado está em "
            "dados/MANIFEST.csv (estagio=externo).", BASE_LONGITUDINAL_V1)
        return
    analise_base_longitudinal.gerar()


def conferir_docs_no_git(raiz: pathlib.Path = RAIZ) -> list[str]:
    """Arquivos de docs/ que diferem do versionado (vazio = estado reproduzido)."""
    try:
        r = subprocess.run(["git", "status", "--porcelain", "--", "docs"], cwd=raiz,
                           capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        logger.warning("Não foi possível rodar git status (%s); confira docs/ à mão.", e)
        return []
    alterados = [linha[3:] for linha in r.stdout.splitlines() if linha.strip()]
    if alterados:
        logger.warning("docs/ difere do versionado — o clone não reproduziu o estado registrado: %s", alterados)
    else:
        logger.info("git status docs/: limpo — estado reproduzido.")
    return alterados


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--origem-local", type=pathlib.Path, action="append", default=[], metavar="DIR",
                    help="pasta com zips do INEP já baixados (repetível); nunca é alterada")
    ap.add_argument("--baixar", action="store_true",
                    help="baixa do INEP o que faltar (sem isso, nenhuma requisição de rede)")
    ap.add_argument("--so-aquisicao", action="store_true",
                    help="para depois de obter, extrair e conferir os dados")
    args = ap.parse_args()

    imprimir_estimativa(args.so_aquisicao, args.baixar)
    origens = [d.expanduser() for d in args.origem_local]
    resultado = _etapa("aquisicao", lambda: aquisicao.adquirir(origens, baixar_da_rede=args.baixar))
    if resultado["faltando"]:  # type: ignore[index]
        raise SystemExit("Aquisição incompleta; nada mais foi feito. Ver log acima.")
    _etapa("extracao", lambda: (aquisicao.extrair_microdados(), _extrair_indicadores()))
    _etapa("conferencia", _conferir)
    if args.so_aquisicao:
        logger.info("--so-aquisicao: dados obtidos e conferidos; inventários não rodados.")
        return

    _etapa("inventario_microdados", leitura.inventariar_microdados)
    _etapa("catalogo_microdados", catalogo_microdados.catalogar)
    _etapa("inventario_indicadores", indicadores_inep.inventariar)
    _etapa("recorte_rr", indicadores_rr.gravar_todos)
    _etapa("analise_base_v1", _analise_base_v1)
    _etapa("catalogo_html", relatorio_catalogo.gerar)
    conferir_docs_no_git()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    main()
