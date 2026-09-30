"""Migração única (2026-09-30) de dados/ para a estrutura por estágio.

    antes                                      depois
    ~/Downloads, OneDrive/.../TCC  *.zip   →   dados/origem/censo/
    dados/bruto/brutos-inep/*.zip          →   dados/origem/indicadores/
    dados/bruto/doc-censo/*.pdf            →   dados/origem/doc/
    dados/interim/brutos_inep_extraido/    →   dados/bruto/indicadores/
    dados/Processados/                     →   dados/externo/base_longitudinal_v1/
    (extraídos dos zips de censo)          →   dados/bruto/censo/

Cada movimento confere o sha256 antes e depois; se o arquivo consta do
manifesto, confere também contra ele. Qualquer divergência interrompe a
migração. Se o destino já existe com o mesmo sha256, a origem é uma cópia
redundante (ex.: o mesmo zip em Downloads/ e em bruto/brutos-inep/, ou
`TDI_2025_MUNICIPIOS (1).zip`, P005) e vai para a Lixeira do Windows — não é
apagada. Destino existente com hash diferente é erro.

Tudo é registrado em dados/migracao_estrutura_log.csv. O script é idempotente:
rodar de novo só faz o que ainda falta.

    python -m src.migracao_estrutura --censo-de ~/Downloads --anos 2023
    python -m src.migracao_estrutura --censo-de DIR [--censo-de DIR] \\
        --indicadores-de ~/Downloads --tudo
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
import pathlib
import shutil

import send2trash

from src.aquisicao import (
    DOCUMENTACAO,
    MICRODADOS_ZIP,
    ErroIntegridade,
    extrair_censo,
    hashes_manifesto,
    sha256_arquivo,
)
from src.config import (
    BASE_LONGITUDINAL_V1,
    BRUTO,
    DADOS,
    INDICADORES,
    INTERIM,
    ORIGEM_CENSO,
    ORIGEM_DOC,
    ORIGEM_INDICADORES,
)

logger = logging.getLogger(__name__)

ANTIGO_ZIPS_INDICADORES = BRUTO / "brutos-inep"
ANTIGO_DOC = BRUTO / "doc-censo"
ANTIGO_EXTRAIDO = INTERIM / "brutos_inep_extraido"
ANTIGO_PROCESSADOS = DADOS / "Processados"

LOG = DADOS / "migracao_estrutura_log.csv"
_CAMPOS_LOG = ["data_hora", "acao", "origem", "destino", "sha256_antes", "sha256_depois", "observacao"]


class ErroMigracao(RuntimeError):
    pass


def _registrar(acao: str, origem: pathlib.Path | None, destino: pathlib.Path | None,
               antes: str = "", depois: str = "", obs: str = "") -> None:
    novo = not LOG.exists()
    with LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(_CAMPOS_LOG)
        w.writerow([
            dt.datetime.now().astimezone().isoformat(timespec="seconds"), acao,
            origem or "", destino or "", antes, depois, obs,
        ])
    logger.info("%-22s %s → %s %s", acao, origem or "", destino or "", obs)


def mover(origem: pathlib.Path, destino: pathlib.Path, sha_esperado: str | None = None) -> str:
    """Move `origem` → `destino` conferindo sha256 antes e depois.

    Retorna "movido", "duplicata_para_lixeira" ou "ausente" (origem não
    existe; nada a fazer). Levanta ErroMigracao em qualquer divergência.
    """
    if not origem.exists():
        return "ausente"
    antes = sha256_arquivo(origem)
    if sha_esperado is not None and antes != sha_esperado:
        _registrar("ERRO_hash_manifesto", origem, destino, antes, "", f"esperado {sha_esperado}")
        raise ErroMigracao(
            f"{origem} não confere com o manifesto antes de mover.\n"
            f"sha256 esperado: {sha_esperado}\nsha256 obtido:   {antes}"
        )
    if destino.exists():
        no_destino = sha256_arquivo(destino)
        if no_destino != antes:
            _registrar("ERRO_destino_diverge", origem, destino, antes, no_destino)
            raise ErroMigracao(
                f"Destino {destino} já existe com conteúdo diferente de {origem}.\n"
                f"sha256 da origem:  {antes}\nsha256 do destino: {no_destino}"
            )
        send2trash.send2trash(str(origem))
        _registrar("duplicata_para_lixeira", origem, destino, antes, no_destino,
                   "cópia idêntica do que já está no destino")
        return "duplicata_para_lixeira"

    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(origem), str(destino))
    depois = sha256_arquivo(destino)
    if depois != antes:
        _registrar("ERRO_hash_apos_mover", origem, destino, antes, depois)
        raise ErroMigracao(
            f"sha256 mudou ao mover {origem} → {destino}.\nantes:  {antes}\ndepois: {depois}"
        )
    _registrar("movido", origem, destino, antes, depois)
    return "movido"


def _remover_se_vazia(pasta: pathlib.Path) -> None:
    """Remove `pasta` e subpastas só se não sobrar nenhum arquivo."""
    if not pasta.is_dir():
        return
    if any(p.is_file() for p in pasta.rglob("*")):
        restantes = sorted(str(p.relative_to(pasta)) for p in pasta.rglob("*") if p.is_file())
        logger.warning("%s não ficou vazia, mantida. Restam: %s", pasta, restantes)
        return
    shutil.rmtree(pasta)
    _registrar("pasta_removida_vazia", pasta, None)


def migrar_censo(anos: list[int], fontes: list[pathlib.Path], hashes: dict[str, str]) -> None:
    """Move o zip de cada ano para origem/censo/ e extrai as tabelas para bruto/censo/."""
    for ano in anos:
        nome = MICRODADOS_ZIP[ano]
        destino = ORIGEM_CENSO / nome
        candidatos = [f / nome for f in fontes if (f / nome).exists()]
        if not candidatos and not destino.exists():
            raise ErroMigracao(
                f"Zip de {ano} ({nome}) não encontrado em {[str(f) for f in fontes]} "
                f"nem em {ORIGEM_CENSO}."
            )
        for c in candidatos:
            mover(c, destino)
        status = extrair_censo(ano, hashes=hashes)
        for arquivo, st in status.items():
            obs = ("extraído do zip; confere com md5 do INEP e manifesto" if st == "extraido"
                   else "já estava em bruto/censo/ e confere com o manifesto")
            _registrar(f"censo_{st}", destino, BRUTO / "censo" / arquivo, "", hashes[arquivo], obs)


def migrar_indicadores(fontes_extras: list[pathlib.Path], hashes: dict[str, str]) -> None:
    """Zips de bruto/brutos-inep/ (e cópias em `fontes_extras`) → origem/indicadores/."""
    # Cópias " (1)" por último, para que o original seja o movido e a cópia a redundante.
    zips = sorted(
        ANTIGO_ZIPS_INDICADORES.glob("*.zip") if ANTIGO_ZIPS_INDICADORES.is_dir() else [],
        key=lambda p: (" (1)" in p.name, p.name),
    )
    for z in zips:
        base = z.name.replace(" (1)", "")  # P005: cópia do navegador
        if base != z.name:
            if hashes.get(z.name) != hashes.get(base):
                raise ErroMigracao(f"{z.name} não tem o mesmo hash de {base} no manifesto.")
            mover(z, ORIGEM_INDICADORES / base, hashes[base])
            continue
        mover(z, ORIGEM_INDICADORES / z.name, hashes.get(z.name))
    # Cópias fora do projeto: só as que constam do manifesto.
    for fonte in fontes_extras:
        for destino in sorted(ORIGEM_INDICADORES.glob("*.zip")):
            mover(fonte / destino.name, destino, hashes[destino.name])
    _remover_se_vazia(ANTIGO_ZIPS_INDICADORES)


def migrar_doc(hashes: dict[str, str]) -> None:
    for nome in DOCUMENTACAO:
        mover(ANTIGO_DOC / nome, ORIGEM_DOC / nome, hashes[nome])
    _remover_se_vazia(ANTIGO_DOC)


def migrar_extraidos() -> None:
    """interim/brutos_inep_extraido/** → bruto/indicadores/**, estrutura preservada."""
    if not ANTIGO_EXTRAIDO.is_dir():
        return
    for p in sorted(ANTIGO_EXTRAIDO.rglob("*")):
        if p.is_file():
            mover(p, INDICADORES / p.relative_to(ANTIGO_EXTRAIDO))
    _remover_se_vazia(ANTIGO_EXTRAIDO)


def migrar_externo() -> None:
    if not ANTIGO_PROCESSADOS.is_dir():
        return
    for p in sorted(ANTIGO_PROCESSADOS.rglob("*")):
        if p.is_file():
            mover(p, BASE_LONGITUDINAL_V1 / p.relative_to(ANTIGO_PROCESSADOS))
    _remover_se_vazia(ANTIGO_PROCESSADOS)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--censo-de", type=pathlib.Path, action="append", default=[],
                    help="pasta onde procurar os zips de microdados (repetível)")
    ap.add_argument("--indicadores-de", type=pathlib.Path, action="append", default=[],
                    help="pasta com cópias extras dos zips de indicadores (repetível)")
    ap.add_argument("--anos", type=int, nargs="+", default=sorted(MICRODADOS_ZIP),
                    help="anos de censo a migrar (padrão: todos)")
    ap.add_argument("--tudo", action="store_true",
                    help="além do censo, migra indicadores, extraídos, doc e externo")
    args = ap.parse_args()

    hashes = hashes_manifesto()
    try:
        migrar_censo(args.anos, [f.expanduser() for f in args.censo_de], hashes)
        if args.tudo:
            migrar_indicadores([f.expanduser() for f in args.indicadores_de], hashes)
            migrar_doc(hashes)
            migrar_extraidos()
            migrar_externo()
    except (ErroMigracao, ErroIntegridade) as e:
        logger.error("Migração interrompida: %s", e)
        raise SystemExit(1) from e
    logger.info("Log em %s", LOG)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    main()
