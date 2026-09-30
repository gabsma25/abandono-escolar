"""Extrai as planilhas de indicadores do INEP dos .zip em dados/origem/indicadores/
para dados/bruto/indicadores/{tipo}/{ano}/, sem tocar nos originais
(CLAUDE.md §3, regra 1: dados/origem/ é somente leitura — aqui só lemos).

Em bruto/ só se cria o que falta (src/integridade.py): arquivo presente cujo
hash confere não é tocado (nem o mtime muda); presente e divergente é erro;
novo é escrito em temporário, conferido e renomeado. Regravar exige
--sobrescrever. A referência é o sha256 de dados/MANIFEST.csv e, para arquivo
ainda fora dele, o md5 do INEP.

Cada .zip do INEP contém uma pasta com a mesma tabela em dois formatos
(.xlsx e .ods), um arquivo md5_*.txt no formato do `md5sum` cobrindo os dois,
e às vezes lixo de sistema (Thumbs.db, .~lock.*#). Extraímos só o .xlsx e o
.txt de md5; o .ods é a mesma tabela em segundo formato e o lixo é ignorado.
O md5 do .xlsx extraído é comparado com o .txt do próprio INEP, ignorando a
caixa do nome (o INEP grafa '.xlsX' em HAD municípios 2019–2021, P020).

Duas gerações de nomenclatura dos .zip:
  Padrão A (ATU, HAD, IED, TDI): "{TIPO}_{ANO}_{NIVEL}.zip"
  Padrão B (tx_rend):            "tx_rend_{nivel}_{ano}.zip"
"""
from __future__ import annotations

import argparse
import csv
import io
import logging
import os
import pathlib
import re
import zipfile
from dataclasses import dataclass

from src.config import INDICADORES, ORIGEM_INDICADORES
from src.integridade import (
    SUFIXO_PARCIAL,
    Referencia,
    gravar_conferido,
    hashes_manifesto,
    md5_do_zip,
    sha256_arquivo,
)

logger = logging.getLogger(__name__)

_PADRAO_A = re.compile(r"^(?P<tipo>[A-Z]+)_(?P<ano>\d{4})_(?P<nivel>[A-Z_]+)$")
_PADRAO_B = re.compile(r"^tx_rend_(?P<nivel>[a-z_]+)_(?P<ano>\d{4})$")
_SUFIXO_DUPLICATA = re.compile(r"^(?P<base>.+) \(\d+\)$")

NIVEIS = ("brasil_regioes_ufs", "municipios", "escolas")

# Ação por extensão do membro do zip. Diretórios e o que não estiver aqui
# recebem "ignorado_lixo".
_ACAO_POR_EXTENSAO = {
    ".xlsx": "extraido",
    ".txt": "extraido",
    ".ods": "ignorado_ods",
}

_CAMPOS_MANIFESTO = [
    "tipo", "ano", "nivel", "zip_original", "zip_sha256", "membro", "acao",
    "arquivo_extraido", "tamanho_bytes", "md5_esperado", "md5_confere",
    "duplicata_de",
]


@dataclass
class MembroZip:
    tipo: str
    ano: int
    nivel: str
    zip_original: str
    zip_sha256: str
    membro: str
    acao: str
    arquivo_extraido: pathlib.Path | None
    tamanho_bytes: int
    md5_esperado: str | None
    md5_confere: bool | None
    duplicata_de: str | None


def parse_nome_zip(nome_sem_ext: str) -> tuple[str, int, str] | None:
    """'TDI_2025_ESCOLAS' → ('TDI', 2025, 'escolas');
    'tx_rend_escolas_2019' → ('tx_rend', 2019, 'escolas'); None se não casar."""
    m = _PADRAO_A.match(nome_sem_ext)
    if m:
        return m.group("tipo"), int(m.group("ano")), m.group("nivel").lower()
    m = _PADRAO_B.match(nome_sem_ext)
    if m:
        return "tx_rend", int(m.group("ano")), m.group("nivel").lower()
    return None


def extrair(
    origem: pathlib.Path = ORIGEM_INDICADORES, destino: pathlib.Path = INDICADORES,
    hashes: dict[str, str] | None = None, *, sobrescrever: bool = False,
) -> list[MembroZip]:
    """Extrai .xlsx e md5_*.txt de cada .zip de `origem` para `destino/tipo/ano/`.

    `hashes` ({nome-base: sha256}) vem de dados/MANIFEST.csv por padrão.
    Arquivos com sufixo " (N)" (download repetido) são reconhecidos pelo
    nome-base; se o sha256 do zip for idêntico a outro já processado, nada é
    extraído de novo — o zip só entra no manifesto como duplicata.
    """
    if not origem.is_dir():
        raise FileNotFoundError(
            f"Pasta de origem não encontrada: {origem}\n"
            f"Esperava dados/origem/indicadores/ com os .zip de indicadores do INEP."
        )

    zips = sorted(
        origem.glob("*.zip"),
        key=lambda p: (bool(_SUFIXO_DUPLICATA.match(p.stem)), p.name),
    )
    if not zips:
        raise FileNotFoundError(f"Nenhum .zip encontrado em {origem}")

    hashes = hashes if hashes is not None else hashes_manifesto()
    hashes_vistos: dict[str, pathlib.Path] = {}
    resultado: list[MembroZip] = []
    nao_reconhecidos: list[str] = []

    for arquivo_zip in zips:
        dup = _SUFIXO_DUPLICATA.match(arquivo_zip.stem)
        parsed = parse_nome_zip(dup.group("base") if dup else arquivo_zip.stem)
        if parsed is None:
            nao_reconhecidos.append(arquivo_zip.name)
            logger.warning("Nome fora dos padrões conhecidos, ignorado: %s", arquivo_zip.name)
            continue
        tipo, ano, nivel = parsed

        sha = sha256_arquivo(arquivo_zip)
        duplicata_de = hashes_vistos.get(sha)
        if duplicata_de is not None:
            logger.warning(
                "%s tem sha256 idêntico a %s — não extraído de novo.",
                arquivo_zip.name, duplicata_de.name,
            )
            resultado.append(MembroZip(
                tipo, ano, nivel, arquivo_zip.name, sha, "", "duplicata_zip",
                None, arquivo_zip.stat().st_size, None, None, duplicata_de.name,
            ))
            continue
        hashes_vistos[sha] = arquivo_zip

        pasta = destino / tipo / str(ano)
        resultado.extend(
            _extrair_membros(arquivo_zip, sha, tipo, ano, nivel, pasta, hashes, sobrescrever)
        )

    if nao_reconhecidos:
        logger.warning(
            "%d zip(s) não reconhecido(s): %s", len(nao_reconhecidos), nao_reconhecidos
        )
    return resultado


def _extrair_membros(
    arquivo_zip: pathlib.Path, sha: str, tipo: str, ano: int, nivel: str,
    pasta: pathlib.Path, hashes: dict[str, str], sobrescrever: bool,
) -> list[MembroZip]:
    itens: list[MembroZip] = []
    with zipfile.ZipFile(arquivo_zip) as zf:
        membros = [i for i in zf.infolist() if not i.is_dir()]
        md5_esperados = md5_do_zip(zf)  # chave em minúsculas

        for info in membros:
            nome = pathlib.PurePosixPath(info.filename).name
            acao = _ACAO_POR_EXTENSAO.get(pathlib.PurePosixPath(nome).suffix.lower(), "ignorado_lixo")
            if nome.startswith(".~lock"):
                acao = "ignorado_lixo"

            extraido: pathlib.Path | None = None
            md5_ok: bool | None = None
            md5_esp = md5_esperados.get(nome.lower())
            if acao == "extraido":
                extraido = pasta / nome   # achatado: a pasta interna do zip repete tipo/ano
                ref = Referencia(hashes.get(nome), md5_esp, info.CRC)
                with zf.open(info) as src:
                    r = gravar_conferido(src, extraido, ref, sobrescrever=sobrescrever,
                                         descricao=f"de {arquivo_zip.name}")
                if r.status != "ja_presente":
                    logger.info("%s: %s ← %s", r.status, nome, arquivo_zip.name)
                if md5_esp is not None:
                    md5_ok = r.digestos.md5 == md5_esp

            itens.append(MembroZip(
                tipo, ano, nivel, arquivo_zip.name, sha, info.filename, acao,
                extraido, info.file_size, md5_esp, md5_ok, None,
            ))
    return itens


def escrever_manifesto(
    itens: list[MembroZip], destino: pathlib.Path = INDICADORES
) -> pathlib.Path:
    """Grava destino/_manifesto.csv: um registro por membro de cada zip.
    Não substitui dados/MANIFEST.csv, que é o hash dos arquivos originais.
    Só regrava se o conteúdo mudou — rodar de novo não toca o arquivo."""
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / "_manifesto.csv"
    buf = io.StringIO(newline="")
    w = csv.writer(buf)
    w.writerow(_CAMPOS_MANIFESTO)
    for i in sorted(itens, key=lambda i: (i.tipo, i.ano, i.nivel, i.membro)):
        w.writerow([
            i.tipo, i.ano, i.nivel, i.zip_original, i.zip_sha256, i.membro,
            i.acao,
            i.arquivo_extraido.relative_to(destino).as_posix() if i.arquivo_extraido else "",
            i.tamanho_bytes, i.md5_esperado or "",
            "" if i.md5_confere is None else i.md5_confere,
            i.duplicata_de or "",
        ])
    novo = buf.getvalue().encode("utf-8")
    if caminho.exists() and caminho.read_bytes() == novo:
        logger.info("%s inalterado, não regravado.", caminho.name)
        return caminho
    parcial = caminho.with_name(caminho.name + SUFIXO_PARCIAL)
    parcial.write_bytes(novo)
    os.replace(parcial, caminho)
    return caminho


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description="Extrai as planilhas dos zips de indicadores.")
    ap.add_argument("--sobrescrever", action="store_true",
                    help="regrava arquivos já presentes em bruto/indicadores/ (CLAUDE.md §3, regra 1)")
    itens = extrair(sobrescrever=ap.parse_args().sobrescrever)
    manifesto = escrever_manifesto(itens)
    n_xlsx = sum(1 for i in itens if i.acao == "extraido" and i.membro.lower().endswith(".xlsx"))
    n_md5_ok = sum(1 for i in itens if i.md5_confere is True)
    n_md5_falha = sum(1 for i in itens if i.md5_confere is False)
    n_dup = sum(1 for i in itens if i.acao == "duplicata_zip")
    logger.info(
        "%d planilha(s) .xlsx em bruto/; md5 do INEP confere em %d, diverge em %d; "
        "%d zip(s) duplicado(s). Manifesto: %s",
        n_xlsx, n_md5_ok, n_md5_falha, n_dup, manifesto,
    )
